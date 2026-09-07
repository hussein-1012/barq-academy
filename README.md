# BARQ Systems — DevOps Assessment

## 1. Project Overview

This project is a containerized Flask application deployed using Docker Compose with:

* Two Flask application instances.
* NGINX as a reverse proxy and load balancer.
* PostgreSQL as the persistent relational database.
* Redis as the application cache/dependency.
* Docker health checks and service dependency conditions.
* Persistent named volumes for PostgreSQL and Redis.
* Automated validation and backend failure/recovery testing.
* PostgreSQL backup and restore procedures.
* Resource limits and restart policies.
* Separate frontend and backend Docker networks.

The objective is to provide a reproducible, fault-tolerant local deployment while documenting troubleshooting, design decisions, log analysis, security considerations, and recovery procedures.

---

## 2. Architecture

```text
                         Host
                          |
                    127.0.0.1:8080
                          |
                       NGINX
                    (frontend network)
                          |
             +------------+------------+
             |                         |
          app-01                    app-02
          :8080                    :8080
             |                         |
             +------------+------------+
                          |
                    backend network
                     /           \
                PostgreSQL       Redis
                  :5432          :6379
```

### Network Design

The deployment uses two Docker networks:

* `frontend` — connects NGINX to the Flask application instances.
* `backend` — connects the Flask applications to PostgreSQL and Redis.

The backend network is configured as `internal: true`, preventing direct external access to backend services.

Services communicate using Docker Compose service names rather than container IP addresses.

---

## 3. Services

| Service    | Purpose                       | Internal Port | Network            |
| ---------- | ----------------------------- | ------------: | ------------------ |
| `nginx`    | Reverse proxy / load balancer |            80 | frontend           |
| `app-01`   | Flask application instance    |          8080 | frontend + backend |
| `app-02`   | Flask application instance    |          8080 | frontend + backend |
| `postgres` | PostgreSQL database           |          5432 | backend            |
| `redis`    | Redis dependency/cache        |          6379 | backend            |

Only NGINX is published to the host.

The public endpoint is:

```text
http://127.0.0.1:8080
```

The published port can be changed using the `PUBLIC_PORT` environment variable.

Example:

```bash
PUBLIC_PORT=8090 docker compose up -d
```

---

## 4. Application Endpoints

The application provides the following endpoints:

| Endpoint    | Purpose                                   |
| ----------- | ----------------------------------------- |
| `/`         | Application response                      |
| `/health`   | Liveness check                            |
| `/ready`    | Dependency/readiness check                |
| `/instance` | Shows the responding application instance |
| `/records`  | PostgreSQL-backed records                 |
| `/counter`  | Redis-backed counter                      |

Example:

```bash
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
curl http://127.0.0.1:8080/instance
curl http://127.0.0.1:8080/records
curl http://127.0.0.1:8080/counter
```

---

## 5. Prerequisites

Required:

* Docker
* Docker Compose
* Git

Verify Docker:

```bash
docker --version
docker compose version
```

---

## 6. Configuration

Application configuration is provided through:

```text
config/app.env
```

The Compose configuration sets the application binding and port:

```text
APP_HOST=0.0.0.0
APP_PORT=8080
```

Each application instance has a unique identity:

```text
app-01 -> INSTANCE_ID=app-01
app-02 -> INSTANCE_ID=app-02
```

PostgreSQL and Redis are accessed through their Docker Compose service names:

```text
postgres:5432
redis:6379
```

---

## 7. Build and Start

Build the application images:

```bash
docker compose build
```

Start the complete stack:

```bash
docker compose up -d
```

Check service status:

```bash
docker compose ps
```

Expected application and dependency services should report healthy where health checks are configured.

---

## 8. Health and Readiness

The application separates liveness from readiness.

### Liveness

```bash
curl -i http://127.0.0.1:8080/health
```

This verifies that the application process is responding.

### Readiness

```bash
curl -i http://127.0.0.1:8080/ready
```

Readiness verifies that required dependencies are available.

The Docker application health check uses `/ready`:

```text
http://127.0.0.1:8080/ready
```

Application containers depend on healthy PostgreSQL and Redis services before starting.

---

## 9. Load Balancing

NGINX distributes requests between:

```text
app-01:8080
app-02:8080
```

The `/instance` endpoint can be used to observe which backend handled a request:

```bash
for i in {1..10}; do
  curl -s http://127.0.0.1:8080/instance
  echo
done
```

The validation procedure confirms that both backend instances receive traffic.

NGINX is configured to retry failed upstream requests using:

```text
proxy_next_upstream error timeout http_502 http_503 http_504;
```

and:

```text
proxy_next_upstream_tries 2;
```

---

## 10. Backend Failure and Recovery

The repository contains a failure/recovery test:

```bash
./failure_test.py
```

The test verifies:

1. Normal traffic distribution.
2. Service availability when `app-01` is stopped.
3. Recovery after `app-01` is restarted.

During the documented test:

```text
Baseline:
20/20 successful

app-01 stopped:
20/20 successful
All requests handled by app-02

After recovery:
20/20 successful
Traffic returned to both instances
```

To manually stop one backend:

```bash
docker stop app-01
```

Then test:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/instance
```

Restart it:

```bash
docker start app-01
```

Check recovery:

```bash
docker compose ps
```

---

## 11. Persistence

### PostgreSQL

PostgreSQL uses the named Docker volume:

```text
postgres-data:/var/lib/postgresql/data
```

This allows database data to survive container recreation.

### Redis

Redis uses:

```text
redis-data:/data
```

Redis persistence is enabled using AOF:

```text
--appendonly yes
--appendfsync everysec
```

List volumes:

```bash
docker volume ls
```

---

## 12. PostgreSQL Backup and Restore

A PostgreSQL backup can be created using the repository backup procedure.

Example:

```bash
./backup.sh
```

A generated dump is stored under:

```text
backups/
```

Restore using:

```bash
./restore.sh <backup-file>
```

Example:

```bash
./restore.sh backups/barq_tasks_YYYYMMDD_HHMMSS.dump
```

A real recovery test was performed by:

1. Creating a test record.
2. Creating a PostgreSQL dump.
3. Deleting the record.
4. Restoring the dump.
5. Verifying that the deleted record was restored.

The documented recovery proof restored:

```text
Backup Restore Proof
```

---

## 13. Validation

The repository includes automated validation for the deployment.

Run:

```bash
./validate.py
```

The validation checks the availability and behavior of the deployed stack, including dependency readiness and backend traffic distribution.

The validation procedure should be run after starting the stack:

```bash
docker compose up -d
./validate.py
```

---

## 14. Logs and Log Analysis

The assessment includes three application-related logs:

```text
logs/access.log
logs/error.log
logs/application.log
```

The logs were analyzed using Python because `jq` was not available in the assessment environment.

The analysis covered:

* HTTP status distribution.
* Request paths.
* Upstream distribution.
* Application event types.
* Backend instance distribution.
* Redis dependency failures.
* NGINX upstream failures.
* Request ID correlation.
* Failure timelines.
* Cross-log root-cause correlation.

The detailed analysis is documented in:

```text
log_analysis.md
```

---

## 15. Troubleshooting

The actual troubleshooting process and retest evidence are documented in:

```text
troubleshooting.md
```

Major issues investigated included:

* Flask binding to `127.0.0.1`.
* Incorrect readiness endpoint.
* Incorrect PostgreSQL and Redis connection settings.
* Duplicate backend instance identity.
* Incorrect PostgreSQL storage configuration.
* Incorrect NGINX upstream configuration.
* Backend failure and recovery.
* PostgreSQL backup and restore.

---

## 16. Design Decisions

Architecture and operational decisions are documented in:

```text
decisions.md
```

Important decisions include:

* Docker image digest pinning.
* Separate liveness and readiness checks.
* Frontend/backend network separation.
* Docker service-name based discovery.
* NGINX upstream retry behavior.
* Restart policies.
* Resource limits.
* Non-root application execution.
* Named database storage.
* Redis AOF persistence.
* PostgreSQL backup and restore.
* Automated failure testing.

---

## 17. Security Considerations

Security-related observations and recommendations are documented in:

```text
security_review.md
```

The deployment applies several local security controls:

* Backend network is internal.
* PostgreSQL and Redis are not published to the host.
* Only NGINX is externally exposed.
* Configuration files are mounted read-only where appropriate.
* Docker images are pinned by digest.
* Resource limits are configured.
* The application is designed to run as a non-root user.

Production deployment would additionally require proper secret management, encrypted off-host backups, external monitoring, and hardened infrastructure configuration.

---

## 18. Repository Documentation

| File                 | Purpose                                |
| -------------------- | -------------------------------------- |
| `README.md`          | Project overview and operational guide |
| `troubleshooting.md` | Actual troubleshooting journal         |
| `log_analysis.md`    | Historical log investigation           |
| `decisions.md`       | Architecture and engineering decisions |
| `security_review.md` | Security review                        |
| `AI_USAGE.md`        | AI usage disclosure                    |
| `backups/`           | PostgreSQL backup artifacts            |

---

## 19. Cleanup

Stop the stack:

```bash
docker compose down
```

Stop and remove containers without removing persistent volumes:

```bash
docker compose down
```

To remove the persistent volumes as well:

```bash
docker compose down -v
```

**Warning:** Removing volumes deletes persisted PostgreSQL and Redis data.

---

## 20. Assessment Evidence

The repository contains evidence for:

* Containerized application deployment.
* Multi-instance Flask architecture.
* NGINX load balancing.
* Backend failure and recovery.
* PostgreSQL persistence.
* Redis persistence configuration.
* PostgreSQL backup and restore.
* Automated validation.
* Historical log analysis.
* Troubleshooting and root-cause investigation.
* Security and architecture decisions.

All troubleshooting claims should be supported by the actual commands, outputs, commits, and documentation contained in the repository.
