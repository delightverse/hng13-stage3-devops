# HNG Stage 3 - Operations Runbook
## Blue/Green Deployment Alert Response Guide

---

## Overview

This runbook provides operational guidance for responding to alerts from the Blue/Green deployment monitoring system. All alerts are sent to Slack automatically when anomalies are detected.

**Primary Contact:** DevOps On-Call Team  
**Escalation:** Engineering Team Lead  
**System:** Blue/Green Deployment with NGINX Load Balancer

---

## Alert Types & Response Procedures

### 🚨 Alert 1: Failover Detected (Primary Pool Down)

#### What It Means

The primary pool (Blue) has failed and traffic has automatically switched to the backup pool (Green).

#### Example Alert
```
🚨 FAILOVER DETECTED: Primary Pool Down

Event Details:
- Previous Pool: BLUE (Primary)
- Current Pool: GREEN (Backup)
- Release ID: green-release-1.0.0
- Time: 2025-10-30T14:32:15Z

What This Means:
The primary pool (blue) has failed health checks or is returning errors.
Traffic has automatically failed over to the backup pool (green).

Immediate Actions Required:
1. Check blue container health
2. Verify container is running
3. Check application errors in logs
4. Investigate root cause
```

#### Immediate Response (Within 5 minutes)

**Step 1: Verify Current State**
```bash
# SSH to server
ssh -i ~/.ssh/hng-devops-keypair.pem ubuntu@YOUR-AWS-IP

# Check container status
docker ps | grep app_blue
docker ps | grep app_green

# Verify green is healthy
curl http://localhost:8082/healthz
curl http://localhost:8080/version
```

**Expected:** Green container running and healthy, serving traffic

**Step 2: Check Blue Container Logs**
```bash
# View recent logs
docker logs app_blue --tail 100

# Follow logs in real-time
docker logs app_blue --follow
```

**Look for:**
- Application crashes
- Out of memory errors
- Uncaught exceptions
- Database connection failures
- Timeout errors

**Step 3: Check Container Health**
```bash
# Check if container is running
docker ps -a | grep app_blue

# If stopped, check why
docker inspect app_blue | grep -A 10 "State"

# Check resource usage
docker stats app_blue --no-stream
```

**Step 4: Attempt to Access Blue Directly**
```bash
# Try health endpoint
curl http://localhost:8081/healthz

# Try version endpoint
curl http://localhost:8081/version
```

**If returns errors:** Blue is definitely down, proceed to investigation  
**If returns 200:** Blue might be intermittently failing, monitor closely

#### Root Cause Investigation

**Common Causes:**

| Cause | Symptoms | How to Verify |
|-------|----------|---------------|
| Application Crash | Container restarting | `docker ps` shows recent restart |
| Out of Memory | OOMKilled in logs | `docker inspect` shows OOMKilled |
| Unhandled Exception | Stack trace in logs | `docker logs` shows error trace |
| Resource Exhaustion | High CPU/memory | `docker stats` shows 100% usage |
| External Dependency Failure | Timeout errors | Logs show connection timeouts |
| Configuration Error | App won't start | Logs show config validation errors |

**Investigate Further:**
```bash
# Check system resources on host
free -h
df -h
top

# Check Docker daemon
sudo systemctl status docker

# Check network connectivity
docker exec app_blue ping -c 3 app_green
```

#### Resolution Steps

**Scenario A: Application Bug**
```bash
# Stop chaos if it was triggered
curl -X POST http://localhost:8081/chaos/stop

# If container is down, restart it
docker restart app_blue

# Monitor recovery
watch -n 2 'curl -s http://localhost:8081/healthz'
```

**Scenario B: Out of Resources**
```bash
# Increase container resources (if needed)
# Edit docker-compose.yml to add:
#   deploy:
#     resources:
#       limits:
#         memory: 1G
#         cpus: '1.0'

# Restart with new limits
docker-compose up -d app_blue
```

**Scenario C: Configuration Issue**
```bash
# Check environment variables
docker exec app_blue env | grep -E 'APP_POOL|RELEASE_ID|PORT'

# Verify configuration
docker inspect app_blue | grep -A 10 "Env"

# If misconfigured, fix .env and restart
nano .env
docker-compose up -d app_blue
