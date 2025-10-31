#!/usr/bin/env python3
"""
HNG Stage 3 - Observability & Alert System
Monitors NGINX access logs and sends Slack alerts for:
1. Failover events (Blue → Green)
2. Recovery events (Green → Blue)  
3. High error rates (>threshold)
"""

import json
import os
import time
import requests
from collections import deque
from datetime import datetime

# ===== CONFIGURATION FROM ENVIRONMENT =====
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', 200))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'

# ===== CONSTANTS =====
LOG_FILE = '/var/log/nginx/access.log'
EXPECTED_PRIMARY_POOL = 'blue'  # Blue should be primary
EXPECTED_BACKUP_POOL = 'green'   # Green should be backup

# ===== STATE TRACKING =====
last_seen_pool = None
request_window = deque(maxlen=WINDOW_SIZE)
last_alert_times = {
    'failover': None,
    'recovery': None,
    'error_rate': None
}

# ===== UTILITY FUNCTIONS =====

def send_slack_alert(message, alert_type='info', emoji='ℹ️'):
    """
    Send formatted alert to Slack
    
    Args:
        message: Alert message content
        alert_type: Type of alert for cooldown tracking
        emoji: Emoji to use in alert
    """
    if MAINTENANCE_MODE:
        print(f"[MAINTENANCE MODE] Suppressed {alert_type} alert")
        return
    
    if not SLACK_WEBHOOK_URL:
        print("[ERROR] SLACK_WEBHOOK_URL not configured!")
        return
    
    # Check cooldown
    if last_alert_times.get(alert_type):
        elapsed = (datetime.now() - last_alert_times[alert_type]).total_seconds()
        if elapsed < ALERT_COOLDOWN_SEC:
            print(f"[COOLDOWN] Skipping {alert_type} alert (sent {int(elapsed)}s ago)")
            return
    
    # Build Slack message payload
    payload = {
        "text": f"{emoji} HNG DevOps Alert - {alert_type.title()}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} HNG DevOps Alert"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Timestamp:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | *Alert Type:* `{alert_type}`"
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"[✓ ALERT SENT] {alert_type}: {message[:100]}...")
            last_alert_times[alert_type] = datetime.now()
        else:
            print(f"[✗ SLACK ERROR] Status {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"[✗ NETWORK ERROR] Failed to send Slack alert: {e}")

def calculate_error_rate():
    """Calculate percentage of errors in current window"""
    if len(request_window) == 0:
        return 0.0
    
    error_count = sum(1 for req in request_window if req.get('is_error', False))
    return (error_count / len(request_window)) * 100

def is_error_status(status):
    """Check if HTTP status is an error (5xx)"""
    try:
        status_int = int(status)
        return 500 <= status_int < 600
    except (ValueError, TypeError):
        return False

def parse_log_line(line):
    """
    Parse JSON log line from NGINX
    
    Returns:
        dict: Parsed log entry or None if invalid
    """
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        # Skip non-JSON lines (startup messages, etc.)
        return None

def process_log_entry(entry):
    """
    Process a single log entry and trigger alerts
    
    Detects:
    1. Failover: Primary (Blue) → Backup (Green)
    2. Recovery: Backup (Green) → Primary (Blue)
    3. High error rate
    """
    global last_seen_pool
    
    # Extract fields
    pool = entry.get('pool', '')
    release = entry.get('release', '')
    status = entry.get('status', 0)
    upstream_status = entry.get('upstream_status', '')
    timestamp = entry.get('timestamp', datetime.now().isoformat())
    upstream_addr = entry.get('upstream_addr', 'unknown')
    request_time = entry.get('request_time', 0)
    
    # Skip if pool info missing
    if not pool or pool == '-' or pool == 'null':
        return
    
    # Determine if request had errors
    is_error = is_error_status(status)
    
    # Check upstream status for errors (might have retried)
    if upstream_status:
        # upstream_status might be comma-separated if retried
        for us in str(upstream_status).split(','):
            if is_error_status(us.strip()):
                is_error = True
                break
    
    # Add to rolling window
    request_window.append({
        'pool': pool,
        'status': status,
        'is_error': is_error,
        'timestamp': timestamp
    })
    
    # ===== DETECTION 1: FAILOVER EVENT =====
    # Triggered when: Blue (primary) → Green (backup)
    if last_seen_pool and last_seen_pool != pool:
        
        if last_seen_pool == EXPECTED_PRIMARY_POOL and pool == EXPECTED_BACKUP_POOL:
            # PRIMARY DOWN: Blue → Green
            message = (
                f"*🚨 FAILOVER DETECTED: Primary Pool Down*\n\n"
                f"*Event Details:*\n"
                f"• *Previous Pool:* `{last_seen_pool.upper()}` (Primary)\n"
                f"• *Current Pool:* `{pool.upper()}` (Backup)\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Upstream:* `{upstream_addr}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What This Means:*\n"
                f"The primary pool (`{last_seen_pool}`) has failed health checks or is returning errors. "
                f"Traffic has automatically failed over to the backup pool (`{pool}`).\n\n"
                f"*Immediate Actions Required:*\n"
                f"1. Check `{last_seen_pool}` container health:\n"
                f"   ```docker logs app_{last_seen_pool}```\n"
                f"2. Verify container is running:\n"
                f"   ```docker ps | grep app_{last_seen_pool}```\n"
                f"3. Check application errors in logs\n"
                f"4. Investigate root cause (resource exhaustion, bugs, etc.)\n"
                f"5. Once fixed, traffic will automatically return to primary"
            )
            send_slack_alert(message, alert_type='failover', emoji='🚨')
        
        elif last_seen_pool == EXPECTED_BACKUP_POOL and pool == EXPECTED_PRIMARY_POOL:
            # PRIMARY RECOVERED: Green → Blue  
            message = (
                f"*✅ RECOVERY DETECTED: Primary Pool Restored*\n\n"
                f"*Event Details:*\n"
                f"• *Previous Pool:* `{last_seen_pool.upper()}` (Backup)\n"
                f"• *Current Pool:* `{pool.upper()}` (Primary)\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Upstream:* `{upstream_addr}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What This Means:*\n"
                f"The primary pool (`{pool}`) has recovered and is passing health checks. "
                f"Traffic has automatically returned to the primary pool.\n\n"
                f"*Post-Recovery Actions:*\n"
                f"1. Verify primary stability:\n"
                f"   ```docker logs app_{pool} --tail 50```\n"
                f"2. Monitor error rates for next 30 minutes\n"
                f"3. Document incident and root cause\n"
                f"4. Update runbook if needed\n\n"
                f"*Status:* System operating normally."
            )
            send_slack_alert(message, alert_type='recovery', emoji='✅')
    
    # Update last seen pool
    last_seen_pool = pool
    
    # ===== DETECTION 2: HIGH ERROR RATE =====
    # Only check when window is full
    if len(request_window) >= WINDOW_SIZE:
        error_rate = calculate_error_rate()
        
        if error_rate > ERROR_RATE_THRESHOLD:
            error_count = sum(1 for req in request_window if req.get('is_error', False))
            
            message = (
                f"*⚠️ HIGH ERROR RATE DETECTED*\n\n"
                f"*Metrics:*\n"
                f"• *Error Rate:* `{error_rate:.2f}%` (Threshold: `{ERROR_RATE_THRESHOLD}%`)\n"
                f"• *Errors:* `{error_count}` out of `{WINDOW_SIZE}` requests\n"
                f"• *Current Pool:* `{pool.upper()}`\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What This Means:*\n"
                f"The application is experiencing an elevated error rate. "
                f"This could indicate application bugs, resource constraints, or infrastructure issues.\n\n"
                f"*Immediate Actions Required:*\n"
                f"1. Check application logs:\n"
                f"   ```docker logs app_{pool} --tail 100```\n"
                f"2. Check resource usage:\n"
                f"   ```docker stats app_{pool}```\n"
                f"3. Review recent deployments or changes\n"
                f"4. Consider manual pool toggle if errors persist:\n"
                f"   ```curl -X POST http://localhost:808{1 if pool == 'blue' else 2}/chaos/stop```\n"
                f"5. Escalate to engineering if unresolved in 15 minutes"
            )
            send_slack_alert(message, alert_type='error_rate', emoji='⚠️')

def tail_log_file(filepath):
    """
    Tail log file in real-time (like 'tail -f')
    
    Args:
        filepath: Path to log file to monitor
    """
    print("=" * 70)
    print("HNG STAGE 3 - ALERT WATCHER")
    print("=" * 70)
    print(f"[CONFIG] Log File: {filepath}")
    print(f"[CONFIG] Error Rate Threshold: {ERROR_RATE_THRESHOLD}%")
    print(f"[CONFIG] Window Size: {WINDOW_SIZE} requests")
    print(f"[CONFIG] Alert Cooldown: {ALERT_COOLDOWN_SEC} seconds")
    print(f"[CONFIG] Maintenance Mode: {MAINTENANCE_MODE}")
    print(f"[CONFIG] Expected Primary: {EXPECTED_PRIMARY_POOL}")
    print(f"[CONFIG] Expected Backup: {EXPECTED_BACKUP_POOL}")
    print("=" * 70)
    
    # Wait for log file to exist
    while not os.path.exists(filepath):
        print(f"[WAITING] Log file not found: {filepath}")
        print("[WAITING] Waiting for NGINX to start and create log file...")
        time.sleep(2)
    
    print(f"[READY] Log file found!")
    print("[READY] Starting real-time monitoring...")
    print("=" * 70)
    
    # Send startup notification to Slack
    startup_message = (
        f"*🟢 Alert Watcher Started*\n\n"
        f"*Configuration:*\n"
        f"• Monitoring: `{filepath}`\n"
        f"• Error Threshold: `{ERROR_RATE_THRESHOLD}%`\n"
        f"• Window Size: `{WINDOW_SIZE}` requests\n"
        f"• Cooldown Period: `{ALERT_COOLDOWN_SEC}s`\n"
        f"• Primary Pool: `{EXPECTED_PRIMARY_POOL}`\n"
        f"• Backup Pool: `{EXPECTED_BACKUP_POOL}`\n\n"
        f"*Status:* Monitoring active. Ready to detect failovers and error spikes."
    )
    send_slack_alert(startup_message, alert_type='info', emoji='🟢')
    
    # Open file and start tailing
    with open(filepath, 'r') as file:
        # Seek to end of file (only monitor NEW logs)
        file.seek(0, 2)
        
        print("[MONITORING] Watching for new log entries...")
        
        while True:
            line = file.readline()
            
            if line:
                # Process new log line
                entry = parse_log_line(line)
                if entry:
                    process_log_entry(entry)
            else:
                # No new data, sleep briefly
                time.sleep(0.1)

def main():
    """Main entry point"""
    # Validate configuration
    if not SLACK_WEBHOOK_URL:
        print("[FATAL ERROR] SLACK_WEBHOOK_URL environment variable not set!")
        print("[FATAL ERROR] Cannot send alerts. Exiting.")
        exit(1)
    
    try:
        tail_log_file(LOG_FILE)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Watcher stopped by user (Ctrl+C)")
        exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == '__main__':
    main()
