#!/usr/bin/env python3
"""
Nginx Log Watcher - Stage 3 Observability
Monitors Nginx logs for failovers and error rates, sends alerts to Slack
"""

import os
import json
import time
import subprocess
from collections import deque
from datetime import datetime
import requests

# Configuration from environment variables
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
ACTIVE_POOL = os.getenv('ACTIVE_POOL', 'blue')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', '2'))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '200'))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
LOG_FILE = '/logs/access.log'

# State tracking
request_window = deque(maxlen=WINDOW_SIZE)
last_pool = ACTIVE_POOL
last_alert_time = {}

def send_slack_alert(message, alert_type='info'):
    """Send alert to Slack webhook with cooldown and deduplication"""
    if not SLACK_WEBHOOK_URL or SLACK_WEBHOOK_URL == 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL':
        print(f"[WARN] No valid Slack webhook configured. Alert: {message}")
        return False
    
    # Suppress failover alerts during maintenance
    if MAINTENANCE_MODE and alert_type == 'failover':
        print(f"[INFO] Maintenance mode: Suppressing failover alert")
        return False
    
    # Check cooldown to prevent spam
    now = time.time()
    if alert_type in last_alert_time:
        elapsed = now - last_alert_time[alert_type]
        if elapsed < ALERT_COOLDOWN_SEC:
            remaining = int(ALERT_COOLDOWN_SEC - elapsed)
            print(f"[INFO] Alert cooldown active for {alert_type} ({remaining}s remaining)")
            return False
    
    # Prepare Slack message with color coding
    color_map = {
        'failover': '#FFA500',  # Orange
        'error': '#FF0000',      # Red
        'recovery': '#00FF00',   # Green
        'info': '#0000FF'        # Blue
    }
    color = color_map.get(alert_type, '#808080')
    
    payload = {
        "attachments": [{
            "color": color,
            "title": f"🚨 Blue/Green Deployment Alert: {alert_type.upper()}",
            "text": message,
            "footer": "Nginx Log Watcher | Stage 3 Observability",
            "ts": int(now)
        }]
    }
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            last_alert_time[alert_type] = now
            print(f"[SUCCESS] Slack alert sent: {alert_type}")
            return True
        else:
            print(f"[ERROR] Slack webhook failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send Slack alert: {e}")
        return False

def parse_log_line(line):
    """Parse JSON log line from Nginx"""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def check_failover(current_pool):
    """Detect and alert on pool failover events"""
    global last_pool
    
    if not current_pool or current_pool == last_pool:
        return
    
    # Failover detected!
    message = (
        f"🔄 *Failover Detected*\n"
        f"• Pool switched: `{last_pool}` → `{current_pool}`\n"
        f"• Timestamp: `{datetime.now().isoformat()}`\n"
        f"• Previous pool: `{last_pool}` (likely unhealthy)\n"
        f"• Current pool: `{current_pool}` (now serving traffic)\n"
        f"\n*Operator Action Required:*\n"
        f"1. Check health of `{last_pool}` container\n"
        f"2. Review application logs for errors\n"
        f"3. Verify `{current_pool}` is stable\n"
        f"4. Investigate root cause"
    )
    
    send_slack_alert(message, alert_type='failover')
    last_pool = current_pool
    print(f"[ALERT] Failover: {last_pool} → {current_pool}")

def check_error_rate():
    """Check if error rate exceeds threshold over sliding window"""
    if len(request_window) < WINDOW_SIZE:
        return  # Not enough data yet
    
    error_count = sum(1 for req in request_window if req.get('is_error', False))
    total_requests = len(request_window)
    error_rate = (error_count / total_requests) * 100
    
    if error_rate > ERROR_RATE_THRESHOLD:
        message = (
            f"⚠️ *High Error Rate Alert*\n"
            f"• Error Rate: `{error_rate:.2f}%` (Threshold: `{ERROR_RATE_THRESHOLD}%`)\n"
            f"• Window: Last `{WINDOW_SIZE}` requests\n"
            f"• Errors: `{error_count}` / `{total_requests}` requests\n"
            f"• Timestamp: `{datetime.now().isoformat()}`\n"
            f"\n*Operator Action Required:*\n"
            f"1. Check application logs for upstream errors\n"
            f"2. Review Nginx error logs\n"
            f"3. Verify resource availability (CPU, memory)\n"
            f"4. Consider manual pool toggle if issue persists\n"
            f"5. Monitor for recovery"
        )
        
        send_slack_alert(message, alert_type='error')
        print(f"[ALERT] High error rate: {error_rate:.2f}% (threshold: {ERROR_RATE_THRESHOLD}%)")

def tail_logs():
    """Tail Nginx logs in real-time and process events"""
    print("=" * 60)
    print("🔍 NGINX LOG WATCHER - Stage 3 Observability")
    print("=" * 60)
    print(f"[INFO] Log file: {LOG_FILE}")
    print(f"[INFO] Active pool: {ACTIVE_POOL}")
    print(f"[INFO] Error threshold: {ERROR_RATE_THRESHOLD}%")
    print(f"[INFO] Window size: {WINDOW_SIZE} requests")
    print(f"[INFO] Alert cooldown: {ALERT_COOLDOWN_SEC}s")
    print(f"[INFO] Maintenance mode: {MAINTENANCE_MODE}")
    print(f"[INFO] Slack webhook configured: {bool(SLACK_WEBHOOK_URL and SLACK_WEBHOOK_URL != 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL')}")
    print("=" * 60)
    
    # Wait for log file to exist
    wait_count = 0
    while not os.path.exists(LOG_FILE):
        print(f"[INFO] Waiting for log file {LOG_FILE}... ({wait_count}s)")
        time.sleep(2)
        wait_count += 2
        if wait_count > 60:
            print(f"[ERROR] Log file not found after 60s. Exiting.")
            return
    
    print(f"[SUCCESS] Log file found! Starting monitoring...")
    print("-" * 60)
    
    # Use tail -F to follow log file (handles rotation)
    process = subprocess.Popen(
        ['tail', '-F', '-n', '0', LOG_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    
    line_count = 0
    
    try:
        for line in iter(process.stdout.readline, ''):
            if not line.strip():
                continue
            
            log_entry = parse_log_line(line.strip())
            if not log_entry:
                continue
            
            line_count += 1
            
            # Extract relevant fields
            status = log_entry.get('status', 0)
            pool = log_entry.get('pool', '')
            upstream_status = log_entry.get('upstream_status', '')
            request = log_entry.get('request', '')
            
            # Determine if this is an error
            is_error = False
            if status >= 500:
                is_error = True
            elif upstream_status and upstream_status.startswith('5'):
                is_error = True
            
            # Track request in sliding window
            request_window.append({
                'timestamp': log_entry.get('timestamp'),
                'status': status,
                'pool': pool,
                'is_error': is_error,
                'request': request
            })
            
            # Print log line summary
            status_icon = "❌" if is_error else "✅"
            print(f"{status_icon} [{line_count}] {status} | Pool: {pool or 'N/A'} | {request[:50]}")
            
            # Check for failover (pool change)
            if pool:
                check_failover(pool)
            
            # Check error rate periodically
            if line_count % 10 == 0:  # Check every 10 requests
                check_error_rate()
    
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("[INFO] Shutting down log watcher...")
        print("=" * 60)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
    finally:
        process.terminate()
        print("[INFO] Log watcher stopped")

if __name__ == '__main__':
    tail_logs()
