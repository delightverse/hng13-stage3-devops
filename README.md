# HNG DevOps Stage 3 - Observability & Alerts for Blue/Green Deployment

This project implements a **Blue/Green deployment** with **Nginx failover**, **real-time log monitoring**, and **Slack alerting** using Docker Compose.

## 🎯 Project Overview

**Stage 3** extends Stage 2 by adding operational visibility through:
- Custom Nginx logging with pool, release ID, upstream status, and latency tracking
- Python log-watcher service that monitors logs in real-time
- Slack alerts for failover events and high error rates
- Operator runbook for alert response procedures

---

## 🏗️ Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   Nginx (Proxy)     │
│  - Blue/Green       │
│  - Health Checks    │
│  - JSON Logging     │◄───┐
└──────┬──────────────┘    │
       │                   │
       ├──────────┬────────┤
       ▼          ▼        │
┌──────────┐ ┌──────────┐ │
│ App Blue │ │App Green │ │
│ (Primary)│ │ (Backup) │ │
└──────────┘ └──────────┘ │
                           │
                    ┌──────┴────────┐
                    │ Log Watcher   │
                    │ - Failover    │
                    │ - Error Rate  │
                    └──────┬────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Slack    │
                    └─────────────┘
```

---

## 📋 Prerequisites

- Docker & Docker Compose
- Slack workspace with webhook URL
- Git

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd hng13-stage3-devops
```

### 2. Configure Slack Webhook

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your Slack webhook URL:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Or use the setup script:**

```bash
./setup-slack.sh
```

### 3. Deploy Services

```bash
docker-compose up -d --build
```

### 4. Verify Deployment

Check all services are running:

```bash
docker-compose ps
```

Expected output:
```
NAME                IMAGE                                    STATUS
alert_watcher       hng13-stage3-devops-alert_watcher        Up
app_blue            yimikaade/wonderful:devops-stage-two     Up (healthy)
app_green           yimikaade/wonderful:devops-stage-two     Up (healthy)
nginx_proxy         nginx:alpine                             Up
```

### 5. Test the Application

```bash
curl http://localhost:8080/
```

You should see a response from the active pool (blue by default).

---

## 🧪 Testing Failover & Alerts

### Test 1: Basic Failover

Stop the active pool (blue) to trigger failover:

```bash
docker stop app_blue
```

Generate traffic to trigger the failover:

```bash
for i in {1..10}; do curl http://localhost:8080/; sleep 1; done
```

**Expected Result:**
- Traffic automatically switches to green pool
- Slack alert: **"🔄 Failover Detected"** message appears

Restart blue:

```bash
docker start app_blue
```

### Test 2: High Error Rate Alert

Simulate errors by making requests to a non-existent endpoint:

```bash
for i in {1..250}; do 
  curl -s http://localhost:8080/error-endpoint > /dev/null
  sleep 0.1
done
```

**Expected Result:**
- Error rate exceeds threshold (>2%)
- Slack alert: **"⚠️ High Error Rate Alert"** message appears

### Test 3: Recovery Verification

After failover, restart the primary pool:

```bash
docker start app_blue
sleep 10  # Wait for health check
docker stop app_green
```

Generate traffic:

```bash
for i in {1..10}; do curl http://localhost:8080/; sleep 1; done
```

**Expected Result:**
- Traffic switches back to blue (recovery)
- Slack alert: **"🔄 Failover Detected"** (green → blue)

---

## 📊 Monitoring & Logs

### View Log Watcher Output

```bash
docker logs -f alert_watcher
```

Sample output:
```
🔍 NGINX LOG WATCHER - Stage 3 Observability
============================================================
[INFO] Active pool: blue
[INFO] Error threshold: 2.0%
[INFO] Window size: 200 requests
[INFO] Alert cooldown: 300s
============================================================
✅ [1] 200 | Pool: blue | GET / HTTP/1.1
✅ [2] 200 | Pool: blue | GET /health HTTP/1.1
❌ [3] 500 | Pool: green | GET / HTTP/1.1
[ALERT] Failover: blue → green
[SUCCESS] Slack alert sent: failover
```

### View Nginx Logs

```bash
docker exec nginx_proxy cat /var/log/nginx/access.log | tail -n 5
```

Sample JSON log entry:
```json
{
  "timestamp": "2025-10-30T15:58:43+00:00",
  "remote_addr": "172.18.0.1",
  "request": "GET / HTTP/1.1",
  "status": 200,
  "pool": "blue",
  "release": "blue-release-1.0.0",
  "upstream_addr": "172.18.0.2:3000",
  "upstream_status": "200",
  "upstream_response_time": "0.005",
  "request_time": 0.006,
  "bytes_sent": 1234
}
```

### View Application Logs

```bash
docker logs app_blue
docker logs app_green
```

---

## ⚙️ Configuration

All configuration is in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | (required) |
| `ACTIVE_POOL` | Initial active pool (blue/green) | `blue` |
| `ERROR_RATE_THRESHOLD` | Error rate % to trigger alert | `2` |
| `WINDOW_SIZE` | Number of requests to track | `200` |
| `ALERT_COOLDOWN_SEC` | Seconds between duplicate alerts | `300` |
| `MAINTENANCE_MODE` | Suppress failover alerts during maintenance | `false` |

### Changing Active Pool

Update `.env`:

```bash
ACTIVE_POOL=green
```

Restart services:

```bash
docker-compose down
docker-compose up -d
```

### Maintenance Mode

To suppress failover alerts during planned maintenance:

```bash
MAINTENANCE_MODE=true
```

Error rate alerts will still be sent.

---

## 📸 Required Screenshots

For submission, include the following screenshots:

### 1. Slack Alert - Failover Event
![Failover Alert](./screenshots/slack-failover.png)

**How to capture:**
1. Run `docker stop app_blue`
2. Generate traffic: `curl http://localhost:8080/`
3. Screenshot the Slack message showing pool change

### 2. Slack Alert - High Error Rate
![Error Rate Alert](./screenshots/slack-error-rate.png)

**How to capture:**
1. Run error simulation script (see Test 2 above)
2. Screenshot the Slack message showing error rate threshold breach

### 3. Container Logs - Nginx JSON Log
![Nginx Logs](./screenshots/nginx-logs.png)

**How to capture:**
```bash
docker exec nginx_proxy cat /var/log/nginx/access.log | tail -n 5
```
Screenshot showing structured JSON with pool, release, upstream_status fields

---

## 🔧 Troubleshooting

### Slack Alerts Not Sending

1. Verify webhook URL in `.env`:
   ```bash
   grep SLACK_WEBHOOK_URL .env
   ```

2. Test webhook manually:
   ```bash
   curl -X POST "YOUR_WEBHOOK_URL" \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test message"}'
   ```

3. Check watcher logs:
   ```bash
   docker logs alert_watcher | grep -i slack
   ```

### Failover Not Working

1. Check container health:
   ```bash
   docker-compose ps
   ```

2. Verify Nginx configuration:
   ```bash
   docker exec nginx_proxy cat /etc/nginx/conf.d/default.conf
   ```

3. Check Nginx error logs:
   ```bash
   docker logs nginx_proxy | grep -i error
   ```

### No Logs Generated

1. Generate some traffic:
   ```bash
   for i in {1..50}; do curl http://localhost:8080/; done
   ```

2. Verify log file exists:
   ```bash
   docker exec nginx_proxy ls -la /var/log/nginx/
   ```

---

## 📖 Alert Runbook

See [runbook.md](./runbook.md) for detailed alert meanings and operator response procedures.

---

## 🧹 Cleanup

Stop and remove all services:

```bash
docker-compose down -v
```

Remove images:

```bash
docker-compose down -v --rmi all
```

---

## 📚 Additional Resources

- **Nginx Documentation**: https://nginx.org/en/docs/
- **Docker Compose**: https://docs.docker.com/compose/
- **Slack Webhooks**: https://api.slack.com/messaging/webhooks

---

## 🙋 Webhook Setup Note

**Q: Do I need to add/run the webhook URL in the Slack channel?**

**A:** No, you don't need to do anything in the Slack channel itself. The webhook URL you created is already configured to post to a specific channel. Just:

1. Copy the webhook URL from Slack
2. Add it to your `.env` file
3. The watcher service will automatically use it to send alerts to the designated channel

The webhook is a "write-only" URL that allows your application to post messages directly to Slack without any additional setup in the channel.

---

## 📝 License

This project is part of the HNG DevOps Internship Stage 3 assignment.

---

## 👥 Author

[Your Name] - HNG13 DevOps Track
