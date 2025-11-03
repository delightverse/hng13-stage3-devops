#!/usr/bin/env python3
"""
HNG Stage 3 - Observability & Alert System
CORRECTED VERSION with full debugging
"""

import json
import os
import time
import requests
from collections import deque
from datetime import datetime
import subprocess

# ===== CONFIGURATION =====
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', 200))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'

LOG_FILE = '/var/log/nginx/access.log'
EXPECTED_PRIMARY_POOL = 'blue'
EXPECTED_BACKUP_POOL = 'green'

# ===== STATE =====
last_seen_pool = None
request_window = deque(maxlen=WINDOW_SIZE)
last_alert_times = {
    'failover': None,
    'recovery': None,
    'error_rate': None
}

def send_slack_alert(message, alert_type='info', emoji='ℹ️'):
    """Send formatted alert to Slack with debugging"""
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
    
    # Simple payload for reliability
    payload = {
        "text": f"{emoji} *{alert_type.upper()} ALERT*\n\n{message}\n\n_Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}_"
    }
    
    print(f"[DEBUG] Sending {alert_type} alert to Slack...")
    print(f"[DEBUG] Webhook: {SLACK_WEBHOOK_URL[:50]}...")
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        
        print(f"[DEBUG] Response Status: {response.status_code}")
        print(f"[DEBUG] Response Text: {response.text}")
        
        if response.status_code == 200:
            print(f"[✓ ALERT SENT] {alert_type} alert successfully sent!")
            last_alert_times[alert_type] = datetime.now()
        else:
            print(f"[✗ SLACK ERROR] Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[✗ ERROR] Failed to send alert: {e}")
        import traceback
        traceback.print_exc()

def calculate_error_rate():
    """Calculate error percentage"""
    if len(request_window) == 0:
        return 0.0
    error_count = sum(1 for req in request_window if req.get('is_error', False))
    return (error_count / len(request_window)) * 100

def is_error_status(status):
    """Check if status is 5xx error"""
    try:
        status_int = int(status)
        return 500 <= status_int < 600
    except (ValueError, TypeError):
        return False

def parse_log_line(line):
    """Parse JSON log line"""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None

def process_log_entry(entry):
    """Process log entry and trigger alerts"""
    global last_seen_pool
    
    # Extract fields
    pool = entry.get('pool', '')
    release = entry.get('release', '')
    status = entry.get('status', 0)
    upstream_status = entry.get('upstream_status', '')
    timestamp = entry.get('timestamp', datetime.now().isoformat())
    upstream_addr = entry.get('upstream_addr', 'unknown')
    
    # DEBUG: Show what we're processing
    print(f"[DEBUG] Processing entry: pool='{pool}', status={status}, last_pool='{last_seen_pool}'")
    
    # Skip invalid entries
    if not pool or pool == '-' or pool == 'null' or pool == '':
        print(f"[DEBUG] SKIPPED - Invalid pool value: '{pool}'")
        return
    
    # Determine if error
    is_error = is_error_status(status)
    if upstream_status:
        for us in str(upstream_status).split(','):
            if is_error_status(us.strip()):
                is_error = True
                break
    
    if is_error:
        print(f"[DEBUG] ERROR DETECTED - Status: {status}, Upstream: {upstream_status}")
    
    # Add to window
    request_window.append({
        'pool': pool,
        'status': status,
        'is_error': is_error,
        'timestamp': timestamp
    })
    
    print(f"[DEBUG] Window size: {len(request_window)}, Errors: {sum(1 for r in request_window if r.get('is_error'))}")
    
    # ===== FAILOVER DETECTION =====
    if last_seen_pool and last_seen_pool != pool:
        print(f"[DEBUG] ⚠️  POOL CHANGE DETECTED! '{last_seen_pool}' -> '{pool}'")
        
        if last_seen_pool == EXPECTED_PRIMARY_POOL and pool == EXPECTED_BACKUP_POOL:
            print(f"[DEBUG] ✓ FAILOVER CONDITION MET! {EXPECTED_PRIMARY_POOL} -> {EXPECTED_BACKUP_POOL}")
            
            # FAILOVER: Blue → Green
            message = (
                f"*🚨 FAILOVER DETECTED*\n\n"
                f"*Event:* Primary pool has failed\n\n"
                f"*Pool Change:*\n"
                f"• *Primary Pool (was serving):* `{last_seen_pool.upper()}` ❌ DOWN\n"
                f"• *Backup Pool (now serving):* `{pool.upper()}` ✅ ACTIVE\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Upstream:* `{upstream_addr}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What Happened:*\n"
                f"The primary pool (`{last_seen_pool}`) failed health checks or returned errors. "
                f"Traffic automatically switched to backup pool (`{pool}`).\n\n"
                f"*Actions Required:*\n"
                f"1️⃣ Check primary container health:\n"
                f"   ```docker logs app_{last_seen_pool} --tail 50```\n"
                f"2️⃣ Verify container status:\n"
                f"   ```docker ps | grep app_{last_seen_pool}```\n"
                f"3️⃣ Investigate root cause\n"
                f"4️⃣ Fix issue and wait for automatic recovery"
            )
            send_slack_alert(message, alert_type='failover', emoji='🚨')
        
        elif last_seen_pool == EXPECTED_BACKUP_POOL and pool == EXPECTED_PRIMARY_POOL:
            print(f"[DEBUG] ✓ RECOVERY CONDITION MET! {EXPECTED_BACKUP_POOL} -> {EXPECTED_PRIMARY_POOL}")
            
            # RECOVERY: Green → Blue
            message = (
                f"*✅ RECOVERY DETECTED*\n\n"
                f"*Event:* Primary pool has been restored\n\n"
                f"*Pool Change:*\n"
                f"• *Backup Pool (was serving):* `{last_seen_pool.upper()}`\n"
                f"• *Primary Pool (now serving):* `{pool.upper()}` ✅ RESTORED\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Upstream:* `{upstream_addr}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What Happened:*\n"
                f"The primary pool (`{pool}`) has recovered and passed health checks. "
                f"Traffic automatically returned to the primary pool.\n\n"
                f"*Post-Recovery Actions:*\n"
                f"1️⃣ Monitor primary pool stability:\n"
                f"   ```docker logs app_{pool} --tail 50```\n"
                f"2️⃣ Verify no errors for next 15 minutes\n"
                f"3️⃣ Document the incident and root cause\n\n"
                f"*Status:* ✅ System operating normally"
            )
            send_slack_alert(message, alert_type='recovery', emoji='✅')
        else:
            print(f"[DEBUG] Pool change but not failover/recovery: {last_seen_pool} -> {pool}")
    
    # Update last seen pool
    last_seen_pool = pool
    
    # ===== ERROR RATE DETECTION =====
    if len(request_window) >= WINDOW_SIZE:
        error_rate = calculate_error_rate()
        
        print(f"[DEBUG] Error rate check: {error_rate:.2f}% (threshold: {ERROR_RATE_THRESHOLD}%)")
        
        if error_rate > ERROR_RATE_THRESHOLD:
            error_count = sum(1 for req in request_window if req.get('is_error', False))
            
            print(f"[DEBUG] ✓ ERROR RATE THRESHOLD EXCEEDED! {error_rate:.2f}% > {ERROR_RATE_THRESHOLD}%")
            
            message = (
                f"*⚠️ HIGH ERROR RATE DETECTED*\n\n"
                f"*Metrics:*\n"
                f"• *Error Rate:* `{error_rate:.2f}%` (Threshold: `{ERROR_RATE_THRESHOLD}%`) 🔴\n"
                f"• *Errors:* `{error_count}` out of `{WINDOW_SIZE}` requests\n"
                f"• *Current Pool:* `{pool.upper()}`\n"
                f"• *Release ID:* `{release}`\n"
                f"• *Time:* `{timestamp}`\n\n"
                f"*What This Means:*\n"
                f"The application is experiencing elevated error rates. "
                f"This may indicate bugs, resource exhaustion, or infrastructure problems.\n\n"
                f"*Immediate Actions:*\n"
                f"1️⃣ Check application logs:\n"
                f"   ```docker logs app_{pool} --tail 100```\n"
                f"2️⃣ Check resource usage:\n"
                f"   ```docker stats app_{pool} --no-stream```\n"
                f"3️⃣ Review recent deployments or changes\n"
                f"4️⃣ Consider manual pool toggle if errors persist\n"
                f"5️⃣ Escalate if unresolved in 15 minutes"
            )
            send_slack_alert(message, alert_type='error_rate', emoji='⚠️')

def tail_log_file_with_subprocess(filepath):
    """
    Tail log file using subprocess (works with Docker volumes)
    This avoids the 'not seekable' error
    """
    print("=" * 70)
    print("HNG STAGE 3 - ALERT WATCHER v2.0")
    print("=" * 70)
    print(f"[CONFIG] Log File: {filepath}")
    print(f"[CONFIG] Error Rate Threshold: {ERROR_RATE_THRESHOLD}%")
    print(f"[CONFIG] Window Size: {WINDOW_SIZE} requests")
    print(f"[CONFIG] Alert Cooldown: {ALERT_COOLDOWN_SEC} seconds")
    print(f"[CONFIG] Maintenance Mode: {MAINTENANCE_MODE}")
    print(f"[CONFIG] Expected Primary Pool: {EXPECTED_PRIMARY_POOL}")
    print(f"[CONFIG] Expected Backup Pool: {EXPECTED_BACKUP_POOL}")
    print(f"[CONFIG] Slack Webhook: {SLACK_WEBHOOK_URL[:50] if SLACK_WEBHOOK_URL else 'NOT SET'}...")
    print("=" * 70)
    
    # Wait for log file
    wait_count = 0
    while not os.path.exists(filepath):
        wait_count += 1
        print(f"[WAITING] Log file not found: {filepath} (attempt {wait_count})")
        time.sleep(2)
        if wait_count > 30:
            print("[ERROR] Log file did not appear after 60 seconds!")
            exit(1)
    
    print(f"[READY] Log file found!")
    print("[READY] Starting real-time monitoring...")
    print("=" * 70)
    
    # Send startup alert
    startup_message = (
        f"*🟢 Alert Watcher Started*\n\n"
        f"*Configuration:*\n"
        f"• Monitoring: `{filepath}`\n"
        f"• Error Threshold: `{ERROR_RATE_THRESHOLD}%`\n"
        f"• Window Size: `{WINDOW_SIZE}` requests\n"
        f"• Cooldown: `{ALERT_COOLDOWN_SEC}s`\n"
        f"• Primary Pool: `{EXPECTED_PRIMARY_POOL.upper()}`\n"
        f"• Backup Pool: `{EXPECTED_BACKUP_POOL.upper()}`\n\n"
        f"*Status:* Monitoring active and ready to detect failovers"
    )
    send_slack_alert(startup_message, alert_type='info', emoji='🟢')
    
    print("[MONITORING] Using 'tail -F -n 0' to follow logs...")
    print("[MONITORING] Waiting for new log entries...")
    print("=" * 70)
    
    # Use subprocess to tail (works with Docker volumes)
    # -F: follow and retry if file is rotated
    # -n 0: start from end (only new lines)
    process = subprocess.Popen(
        ['tail', '-F', '-n', '0', filepath],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    line_count = 0
    try:
        for line in process.stdout:
            if line:
                line_count += 1
                if line_count % 10 == 0:
                    print(f"[INFO] Processed {line_count} log entries...")
                
                entry = parse_log_line(line)
                if entry:
                    process_log_entry(entry)
                else:
                    print(f"[DEBUG] Failed to parse log line: {line[:100]}")
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping watcher...")
        process.terminate()
    except Exception as e:
        print(f"[ERROR] Unexpected error in tail loop: {e}")
        import traceback
        traceback.print_exc()
        process.terminate()
        raise

def main():
    """Main entry point"""
    print("\n" + "=" * 70)
    print("STARTING HNG STAGE 3 ALERT WATCHER")
    print("=" * 70 + "\n")
    
    if not SLACK_WEBHOOK_URL:
        print("[FATAL ERROR] SLACK_WEBHOOK_URL environment variable not set!")
        print("[FATAL ERROR] Cannot send alerts. Exiting.")
        exit(1)
    
    print(f"[INIT] Slack webhook configured: {SLACK_WEBHOOK_URL[:50]}...")
    print(f"[INIT] Starting monitoring system...\n")
    
    try:
        tail_log_file_with_subprocess(LOG_FILE)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Watcher stopped by user (Ctrl+C)")
        exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] Watcher crashed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == '__main__':
    main()