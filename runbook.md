# Blue/Green Deployment - Alert Runbook

This runbook provides guidance for operators responding to alerts from the Blue/Green deployment monitoring system.

---

## 🎯 Alert Types Overview

The system generates three types of alerts:

1. **Failover Detected** - Pool switching events (blue ↔ green)
2. **High Error Rate** - Upstream 5xx errors exceed threshold
3. **Recovery** - System returns to normal after an incident

---

## 📋 Alert Response Procedures

### 🔄 Alert Type: Failover Detected

**Alert Message Example:**
```
🔄 Failover Detected
• Pool switched: blue → green
• Timestamp: 2025-10-30T15:58:43+00:00
• Previous pool: blue (likely unhealthy)
• Current pool: green (now serving traffic)
```

#### What This Means

The active pool has switched from one environment to another. This indicates that:
- The primary pool failed health checks
- Nginx automatically failed over to the backup pool
- Traffic is now being served by the backup pool

#### Severity: ⚠️ **MEDIUM** (Automatic failover successful, but investigation required)

#### Immediate Actions (0-5 minutes)

1. **Verify traffic is flowing:**
   ```bash
   curl http://localhost:8080/
   ```
   Confirm you're getting valid responses from the new pool.

2. **Check container status:**
   ```bash
   docker-compose ps
   ```
   Identify which container is down or unhealthy.

3. **Review recent logs:**
   ```bash
   # Check failed pool logs
   docker logs app_blue --tail 100
   
   # Check Nginx error logs
   docker logs nginx_proxy --tail 50 | grep -i error
   ```

#### Investigation Actions (5-30 minutes)

1. **Identify root cause:**
   - Application crash? Check for stack traces in app logs
   - Resource exhaustion? Check container metrics:
     ```bash
     docker stats --no-stream
     ```
   - Network issue? Check connectivity between containers
   - Configuration error? Review recent changes

2. **Determine if immediate recovery is needed:**
   - If backup pool is stable → Schedule maintenance window for recovery
   - If backup pool is also degraded → Escalate immediately

3. **Document the incident:**
   - Timestamp of failover
   - Root cause (if identified)
   - Duration of primary pool downtime
   - Actions taken

#### Recovery Actions

**Option A: Quick Recovery (if root cause is known and fixable)**

1. Fix the issue in the failed pool
2. Restart the container:
   ```bash
   docker restart app_blue
   ```
3. Wait for health checks to pass (10-15 seconds)
4. Monitor logs for errors:
   ```bash
   docker logs -f app_blue
   ```

**Option B: Planned Maintenance (if extensive debugging needed)**

1. Set maintenance mode to suppress further alerts:
   ```bash
   # Edit .env
   MAINTENANCE_MODE=true
   
   # Restart watcher
   docker-compose restart alert_watcher
   ```

2. Investigate and fix the issue

3. Test fixes locally before deployment

4. Switch back when ready:
   ```bash
   # Update .env
   ACTIVE_POOL=blue
   
   # Restart services
   docker-compose down
   docker-compose up -d
   ```

5. Disable maintenance mode:
   ```bash
   MAINTENANCE_MODE=false
   docker-compose restart alert_watcher
   ```

#### Prevention

- Review application logs for patterns before failures
- Set up resource monitoring (CPU, memory)
- Implement circuit breakers in application code
- Regular health check testing
- Load testing to identify breaking points

---

### ⚠️ Alert Type: High Error Rate

**Alert Message Example:**
```
⚠️ High Error Rate Alert
• Error Rate: 5.50% (Threshold: 2%)
• Window: Last 200 requests
• Errors: 11 / 200 requests
• Timestamp: 2025-10-30T16:00:00+00:00
```

#### What This Means

The upstream application is returning 5xx errors at a rate higher than the configured threshold (default: 2%). This could indicate:
- Application bugs or crashes
- Database connection issues
- Resource exhaustion (OOM, CPU throttling)
- Dependency failures (external APIs, services)
- Configuration problems

#### Severity: 🔴 **HIGH** (Active service degradation affecting users)

#### Immediate Actions (0-2 minutes)

1. **Confirm current error rate:**
   ```bash
   docker logs alert_watcher --tail 50
   ```

2. **Check which pool is affected:**
   ```bash
   docker-compose ps
   docker logs app_blue --tail 50 | grep -i error
   docker logs app_green --tail 50 | grep -i error
   ```

3. **Determine impact scope:**
   ```bash
   # Count recent 5xx errors
   docker exec nginx_proxy sh -c "tail -n 200 /var/log/nginx/access.log | grep -c '\"status\":5'"
   ```

#### Investigation Actions (2-15 minutes)

1. **Analyze error patterns:**
   ```bash
   # View detailed error logs with context
   docker exec nginx_proxy cat /var/log/nginx/access.log | tail -n 200
   ```

2. **Check for specific error types:**
   - 500 Internal Server Error → Application crash/bug
   - 502 Bad Gateway → App not responding to Nginx
   - 503 Service Unavailable → App overloaded or down
   - 504 Gateway Timeout → App too slow to respond

3. **Review application health:**
   ```bash
   # Test health endpoint directly
   curl http://localhost:8081/healthz  # Blue
   curl http://localhost:8082/healthz  # Green
   ```

4. **Check resource utilization:**
   ```bash
   docker stats --no-stream
   ```

5. **Review recent changes:**
   - Recent deployments?
   - Configuration changes?
   - Traffic spike?

#### Mitigation Actions

**Option 1: Quick Fix - Switch Pools**

If one pool is healthy and the other is not:

```bash
# Edit .env
ACTIVE_POOL=green  # Switch to healthy pool

# Apply changes
docker-compose down
docker-compose up -d
```

**Option 2: Scale Back - Reduce Load**

If both pools are struggling:

1. Implement rate limiting (if available)
2. Enable caching for static content
3. Temporarily block non-critical traffic sources

**Option 3: Restart - Clear Transient Issues**

If errors seem transient (memory leaks, stuck threads):

```bash
docker-compose restart app_blue app_green
```

**Option 4: Rollback - Revert Recent Changes**

If errors started after a deployment:

```bash
# Update .env with previous working images
BLUE_IMAGE=yimikaade/wonderful:previous-version
GREEN_IMAGE=yimikaade/wonderful:previous-version

# Redeploy
docker-compose down
docker-compose up -d
```

#### Recovery Verification

1. **Monitor error rate:**
   ```bash
   docker logs -f alert_watcher
   ```
   Watch for error rate to drop below threshold

2. **Verify application health:**
   ```bash
   for i in {1..50}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/; sleep 1; done
   ```
   Should see mostly 200s

3. **Check for new alerts:**
   Monitor Slack channel for 10-15 minutes

#### Prevention

- Implement request timeout limits
- Add circuit breakers to external dependencies
- Set up resource limits (memory, CPU) in docker-compose
- Implement retry logic with exponential backoff
- Add request rate limiting
- Comprehensive error handling in application code
- Regular load testing

---

### ✅ Alert Type: Recovery

**Alert Message Example:**
```
✅ Recovery Detected
• Pool switched: green → blue
• Timestamp: 2025-10-30T16:10:00+00:00
• Primary pool restored
• System operating normally
```

#### What This Means

The system has automatically failed back to the primary pool after it recovered from an earlier failure. This is generally a positive sign that:
- The primary pool is healthy again
- Health checks are passing
- Traffic has been restored to the primary environment

#### Severity: ℹ️ **INFO** (Informational only, no action required unless unexpected)

#### Verification Actions (Optional)

1. **Confirm system health:**
   ```bash
   docker-compose ps
   ```
   All containers should be "Up (healthy)"

2. **Monitor for stability:**
   ```bash
   docker logs -f alert_watcher
   ```
   Watch for 5-10 minutes to ensure no new alerts

3. **Verify error rate is normal:**
   Check that error rate is below threshold (<2%)

#### Follow-up Actions

1. **Review incident timeline:**
   - When did initial failover occur?
   - How long was primary pool down?
   - What fixed the issue?

2. **Document post-mortem:**
   - Root cause
   - Duration
   - Impact (if any)
   - Resolution steps
   - Prevention measures

3. **Update monitoring if needed:**
   ```bash
   # Adjust thresholds if getting false positives
   ERROR_RATE_THRESHOLD=3  # Increase if needed
   ```

---

## 🛠️ Common Troubleshooting Commands

### Container Management

```bash
# View all container status
docker-compose ps

# Restart specific container
docker restart app_blue

# Restart all services
docker-compose restart

# Stop and remove everything
docker-compose down

# Full rebuild
docker-compose up -d --build --force-recreate
```

### Log Analysis

```bash
# Real-time logs
docker logs -f alert_watcher
docker logs -f app_blue
docker logs -f nginx_proxy

# Recent logs with timestamps
docker logs app_blue --tail 100 --timestamps

# Search for errors
docker logs app_blue | grep -i error
docker logs nginx_proxy | grep -i "upstream"
```

### Health Checking

```bash
# Direct health checks
curl http://localhost:8081/healthz  # Blue
curl http://localhost:8082/healthz  # Green
curl http://localhost:8080/         # Nginx (active pool)

# Check which pool is active
docker exec nginx_proxy cat /etc/nginx/conf.d/default.conf | grep "server app_"
```

### Network Debugging

```bash
# Test connectivity between containers
docker exec app_blue ping -c 3 app_green
docker exec nginx_proxy ping -c 3 app_blue

# Check network configuration
docker network ls
docker network inspect hng13-stage3-devops_app-network
```

---

## 🚨 Escalation Criteria

**Escalate to senior engineer or on-call lead if:**

1. Both pools are failing simultaneously
2. Error rate exceeds 10% for more than 5 minutes
3. Complete service outage (all containers down)
4. Suspected security incident or data breach
5. Unable to identify root cause within 30 minutes
6. User-facing impact affecting critical business operations

**Escalation Contacts:**
- On-call Lead: [Contact Info]
- DevOps Team Lead: [Contact Info]
- Slack Channel: #ops-emergency

---

## 📊 Monitoring Best Practices

### Regular Health Checks

Run these commands daily or set up automated checks:

```bash
# 1. Verify all containers are healthy
docker-compose ps

# 2. Check for error patterns
docker logs nginx_proxy --since 24h | grep -i error | wc -l

# 3. Review alert history
docker logs alert_watcher --since 24h | grep "\[ALERT\]"

# 4. Test failover capability (in non-prod)
docker stop app_blue
sleep 5
curl http://localhost:8080/  # Should get green response
docker start app_blue
```

### Maintenance Windows

When performing planned maintenance:

1. **Enable maintenance mode:**
   ```bash
   # Edit .env
   MAINTENANCE_MODE=true
   docker-compose restart alert_watcher
   ```

2. **Perform maintenance**

3. **Disable maintenance mode:**
   ```bash
   # Edit .env
   MAINTENANCE_MODE=false
   docker-compose restart alert_watcher
   ```

### Alert Fine-Tuning

If you're getting too many or too few alerts:

```bash
# Edit .env and adjust thresholds

# More sensitive (catch issues earlier)
ERROR_RATE_THRESHOLD=1
WINDOW_SIZE=100

# Less sensitive (reduce noise)
ERROR_RATE_THRESHOLD=5
WINDOW_SIZE=300

# Longer cooldown (reduce alert spam)
ALERT_COOLDOWN_SEC=600  # 10 minutes
```

---

## 📝 Incident Response Checklist

### ✅ During an Incident

- [ ] Alert received and acknowledged
- [ ] Immediate impact assessment completed
- [ ] Mitigation actions identified and executed
- [ ] Stakeholders notified (if customer-facing)
- [ ] Progress updates communicated
- [ ] Root cause identified
- [ ] System recovery verified
- [ ] Monitoring continued for stability

### ✅ Post-Incident

- [ ] Post-mortem document created
- [ ] Timeline documented
- [ ] Root cause analysis completed
- [ ] Action items identified
- [ ] Prevention measures implemented
- [ ] Runbook updated with learnings
- [ ] Team review conducted
- [ ] Monitoring/alerting tuned if needed

---

## 🔗 Additional Resources

- **Nginx Upstream Documentation:** https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- **Docker Health Checks:** https://docs.docker.com/engine/reference/builder/#healthcheck
- **Slack Webhooks:** https://api.slack.com/messaging/webhooks
- **Blue/Green Deployment Pattern:** https://martinfowler.com/bliki/BlueGreenDeployment.html

---

## 📞 Support

For questions or issues with this runbook:
- Open an issue in the project repository
- Contact DevOps team in #devops-support channel
- Review README.md for general setup questions

---

**Last Updated:** 2025-10-30  
**Version:** 1.0  
**Maintained By:** HNG13 DevOps Track
