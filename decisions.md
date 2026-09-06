# Technical Decisions

This document records the main technical decisions made during the assessment.
Each decision includes the reasoning, alternatives, trade-offs, evidence, and possible
production improvements.

---

## 1. Pin Docker images by digest

### Choice
Docker images are pinned to specific SHA256 digests instead of relying only on
mutable tags.

### Why
Pinning the image digest makes the build more reproducible because the exact
image version is fixed.

### Alternative
Use tags such as:

```text
python:3.12-slim-bookworm
postgres:16-alpine
redis:7.4-alpine
nginx:1.28-alpine

Trade-off

Digest pinning improves reproducibility and supply-chain control, but image
updates require manually updating the digest.

Evidence / commit

Implemented in the Docker configuration and application image definition.

Related assessment fix commit:

be7ae1b
Production improvement

Use an automated dependency/image update process that proposes digest updates
and validates them through CI before deployment.

2. Separate liveness and readiness checks
Choice

The application exposes separate /health and /ready endpoints.

/health is used for liveness.
/ready verifies PostgreSQL and Redis readiness.
Why

A running application process is not necessarily ready to serve requests.
Separating these checks prevents dependency failures from being confused with
application process failures.

Alternative

Use a single health endpoint for both liveness and readiness.

Trade-off

Separate endpoints make the system more explicit and reliable, but require
additional application and monitoring configuration.

Evidence / commit

The Docker health check was changed to use /ready.

Related commit:

be7ae1b

Validation confirmed PostgreSQL and Redis readiness.

Production improvement

Use platform-native liveness and readiness probes and define appropriate
startup, readiness, and liveness thresholds.

3. Use separate frontend and backend Docker networks
Choice

The Compose deployment uses:

frontend
backend

NGINX is connected only to frontend.

The application containers are connected to both networks.

PostgreSQL and Redis are connected only to backend.

Why

This limits which services can communicate directly with each other.

The public-facing reverse proxy cannot directly access PostgreSQL or Redis.

Alternative

Place all containers on one Docker network.

Trade-off

Network separation improves isolation but adds configuration complexity.

Evidence / commit

Implemented as part of the container networking fixes.

Related commit:

be7ae1b
Production improvement

Use additional network policies or equivalent controls in a production
orchestrator such as Kubernetes.

4. Use service names instead of container IP addresses
Choice

Application dependencies use Docker Compose service names:

postgres:5432
redis:6379

NGINX uses:

app-01:8080
app-02:8080
Why

Container IP addresses can change when containers are recreated.

Docker's internal DNS allows services to discover each other using stable
service names.

Alternative

Hard-code container IP addresses.

Trade-off

Service-name discovery depends on the Docker network and internal DNS, but it
is significantly more suitable for dynamic container environments.

Evidence / commit

Related container connectivity fixes:

be7ae1b
Production improvement

Use service discovery provided by the production orchestration platform.

5. Configure NGINX upstream retries and timeouts
Choice

NGINX uses upstream timeout settings and retries failed upstream requests.

The configuration includes:

proxy_connect_timeout 2s
proxy_read_timeout 3s

and retries for:

error
timeout
502
503
504
Why

A failed application instance should not unnecessarily make the public API
unavailable when another healthy instance exists.

Alternative

Disable upstream retries and immediately return the upstream error.

Trade-off

Retries improve availability but can increase latency and duplicate work in
some failure scenarios.

Evidence / commit

The configuration was changed as part of the NGINX and networking fixes.

Related commit:

be7ae1b

The failure/recovery test demonstrated continued successful traffic when
app-01 was stopped.

Production improvement

Tune retry behavior based on request idempotency and use circuit-breaking or
service-mesh capabilities where appropriate.

6. Use restart policies and resource limits
Choice

Application and infrastructure services use restart policies such as:

unless-stopped

Resource limits are also configured for the services.

Why

Restart policies improve recovery from unexpected container termination.

Resource limits reduce the risk of one service consuming all available host
resources.

Alternative

Use no restart policy and unlimited resources.

Trade-off

Automatic restarts improve resilience but can hide persistent application
failures if monitoring is not configured.

Resource limits improve isolation but may cause legitimate workloads to be
throttled or terminated if limits are too low.

Evidence / commit

Implemented in the Compose configuration.

Related commit:

be7ae1b
Production improvement

Use production monitoring and alerting to detect restart loops, CPU pressure,
and memory exhaustion. Resource limits should be based on measured workload
requirements.

7. Run the application container as a non-root user
Choice

The application Docker image creates and uses a dedicated non-root user:

uid 10001
Why

Running the application as a non-root user reduces the impact of a potential
container compromise.

Alternative

Run the application as the default root user.

Trade-off

Non-root execution improves security but may require additional permission
configuration when the application needs access to files or system resources.

Evidence / commit

Implemented in the application Dockerfile.

Related assessment fix commit:

be7ae1b
Production improvement

Use a read-only root filesystem where possible and drop unnecessary Linux
capabilities.

8. Use named persistent storage for PostgreSQL
Choice

PostgreSQL data is stored in the named Docker volume:

postgres-data:/var/lib/postgresql/data
Why

Database data must survive PostgreSQL container recreation.

Alternative

Store database data only inside the container filesystem.

Trade-off

Named volumes provide persistence across container recreation, but the volume
is still tied to the local Docker environment.

Evidence / commit

The named PostgreSQL volume was implemented and verified after recreating the
PostgreSQL and application containers.

Related commit:

be7ae1b

The persistence test confirmed that the record:

Backup Restore Proof

remained available after container recreation.

Production improvement

Use managed PostgreSQL or replicated persistent storage in production, together
with tested off-host backups.

9. Enable Redis persistence using AOF
Choice

Redis is configured with append-only persistence:

--appendonly yes
--appendfsync everysec

and uses a named volume:

redis-data:/data
Why

This provides persistence for Redis data instead of relying entirely on
container memory.

Alternative

Run Redis without persistence.

Trade-off

Persistence improves recovery but introduces disk I/O and does not replace a
complete backup strategy.

Evidence / commit

Implemented in the Compose configuration.

Related assessment fix commit:

be7ae1b
Production improvement

For production workloads, define an explicit Redis durability and recovery
strategy based on whether Redis is a cache or a system-of-record dependency.

10. Use PostgreSQL backup and restore scripts
Choice

The repository includes:

backup.sh
restore.sh

using PostgreSQL pg_dump and pg_restore.

Why

The assessment requires an actual database recovery procedure, not only
persistent storage.

Alternative

Rely only on the PostgreSQL Docker volume.

Trade-off

Backups provide recovery from data corruption or deletion, but they require
storage management, retention, security, and regular restore testing.

Evidence / commit

Related commit:

710cfc9

The backup and restore procedure successfully restored the deleted record:

Backup Restore Proof
Production improvement

Store encrypted backups outside the Docker host, define retention policies,
and perform scheduled automated restore tests.

11. Validate failure recovery using an automated test
Choice

A dedicated:

failure_test.py

stops one backend instance, measures traffic, restores the instance, and
verifies recovery.

Why

A load-balanced architecture should be tested under an actual backend failure,
not only under normal healthy conditions.

Alternative

Only check that both containers are running.

Trade-off

Failure testing provides stronger evidence but temporarily removes capacity
from the environment.

Evidence / commit

Related commit:

c2526a0

The test demonstrated:

20/20 requests succeeded while app-01 was down

and both instances received traffic again after recovery.

Production improvement

Run controlled failure tests regularly and add monitoring for error rate,
latency, and recovery time.

Summary

The main architectural decisions prioritize:

Reproducible container images.
Explicit health and readiness semantics.
Network isolation.
Service-name based discovery.
Reverse-proxy failover.
Container resilience and resource control.
Non-root execution.
Persistent database storage.
Redis persistence.
Tested database recovery.
Automated failure testing.

These choices satisfy the assessment requirements while keeping the deployment
simple enough to reproduce locally. Production deployment would require
additional controls such as external secret management, off-host backups,
monitoring, alerting, and stronger high-availability mechanisms.