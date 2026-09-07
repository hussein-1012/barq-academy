# Security Review

This document reviews the main security risks identified in the assessment
environment, the controls implemented, and additional improvements required
for production deployment.

---

## 1. Secrets and credentials

### Risk
Database credentials must not be committed to the repository or embedded
inside Docker images.

### Current control
Secrets are provided through environment configuration rather than being
copied into the application image.

Sensitive local environment files are excluded through `.gitignore`.

### Status
**Implemented**

### Production improvement
Use a dedicated secret-management system such as Docker Secrets, Kubernetes
Secrets, or a cloud secret manager.

Credentials should also be rotated regularly.

---

## 2. Unnecessary host port exposure

### Risk
Publishing PostgreSQL, Redis, or application ports directly to the host could
allow clients to bypass NGINX and access internal services.

### Current control
Only NGINX publishes a host port.

The application, PostgreSQL, and Redis services do not publish host ports.

Public traffic enters through:

```text
127.0.0.1:8080 -> nginx:80

Status

Implemented

Production improvement

Expose only the required ingress/load-balancer port and keep all internal
services on private networks.

3. Network isolation
Risk

If all containers share the same network, a compromised frontend service could
potentially communicate directly with databases or caches.

Current control

The deployment uses separate Docker networks:

frontend
backend

NGINX is connected only to frontend.

The application containers are connected to both networks.

PostgreSQL and Redis are connected only to backend.

Status

Implemented

Production improvement

Apply explicit network policies and least-privilege service communication
rules in production.

4. Running containers as root
Risk

Running the application as root increases the potential impact of a container
escape or application compromise.

Current control

The application Dockerfile creates a dedicated non-root user with UID 10001
and runs the application using that user.

Status

Implemented

Production improvement

Use a read-only root filesystem where possible and remove unnecessary Linux
capabilities.

5. Untrusted or mutable container images
Risk

Using only mutable image tags can cause builds to use different image contents
over time.

Current control

The main Docker images are pinned using SHA256 digests.

This provides deterministic image selection.

Status

Implemented

Production improvement

Automate image vulnerability scanning and controlled digest updates.

A software supply-chain scanning solution should also be integrated into CI.

6. Database persistence and recovery
Risk

Container recreation or accidental deletion could result in database data loss
if storage is not persistent.

Current control

PostgreSQL uses a named Docker volume:

postgres-data:/var/lib/postgresql/data

The repository also contains database backup and restore scripts.

Status

Implemented

Evidence

Database persistence was verified after recreating the PostgreSQL and
application containers.

Backup and restore were also tested using a real PostgreSQL dump.

Production improvement

Store encrypted backups outside the Docker host and define retention,
monitoring, and restore-testing policies.

7. Redis data durability
Risk

Redis data could be lost if the container is recreated without persistence.

Current control

Redis uses:

--appendonly yes
--appendfsync everysec

and a named Docker volume.

Status

Implemented

Production improvement

Determine whether Redis data is disposable cache data or business-critical
state.

For critical state, define replication, backup, and recovery requirements.

8. Dependency health and readiness
Risk

An application container may be running while PostgreSQL or Redis is
unavailable.

Treating a running process as healthy can cause traffic to be sent to an
unready instance.

Current control

The application provides:

/health
/ready

/health represents application liveness.

/ready checks PostgreSQL and Redis readiness.

Docker Compose also waits for healthy PostgreSQL and Redis dependencies before
starting the application services.

Status

Implemented

Production improvement

Use separate liveness, readiness, and startup probes in the production
orchestration platform.

9. Reverse-proxy failure handling
Risk

A failed backend instance can cause unnecessary public request failures if the
reverse proxy does not retry another healthy backend.

Current control

NGINX is configured with upstream timeouts and retry behavior for upstream
errors.

The application instances are registered as:

app-01:8080
app-02:8080
Status

Implemented

Evidence

The failure/recovery test stopped app-01 and verified that traffic continued
successfully through app-02.

Production improvement

Tune retry behavior based on request idempotency and add circuit-breaking and
observability mechanisms.

10. Resource exhaustion
Risk

A single container consuming excessive CPU or memory can affect other services
on the same host.

Current control

Memory limits and CPU limits are defined for the application and supporting
services.

Status

Implemented

Production improvement

Tune limits using production workload measurements and configure monitoring
and alerts for sustained resource pressure.

11. Excessive error exposure
Risk

Returning internal dependency errors, stack traces, or implementation details
to clients can expose information useful to attackers.

Current control

The API uses explicit HTTP status codes for dependency and validation failures,
including:

400
404
503
Status

Implemented

Production improvement

Ensure production responses never expose stack traces or internal credentials,
and centralize detailed errors in protected server-side logs.

12. Request traceability
Risk

Without request identifiers, it is difficult to correlate client requests with
reverse-proxy and application logs during an incident.

Current control

Responses include an X-Request-ID header.

NGINX also records the request ID in its structured access log.

Status

Implemented

Production improvement

Propagate a trusted request/trace ID through all services and integrate it
with distributed tracing and centralized logging.

13. Single NGINX edge instance
Risk

Although the application has two backend instances, a single NGINX container
can become a single point of failure.

Current control

The assessment architecture uses one NGINX container as the public entry point.

Status

Assessment limitation

Production improvement

Use multiple ingress/reverse-proxy instances behind a highly available
load balancer.

14. Local backup storage
Risk

A database dump stored only on the same host as the application does not
protect against host loss or major infrastructure failure.

Current control

The repository provides a tested PostgreSQL backup and restore procedure.

Status

Partially implemented

Production improvement

Copy backups to independent off-host storage, encrypt them, define retention
periods, and regularly perform automated restore tests.

Security Summary
Area	Assessment Status
Secrets handling	Implemented
Host port exposure	Implemented
Network isolation	Implemented
Non-root application	Implemented
Image pinning	Implemented
PostgreSQL persistence	Implemented
Redis persistence	Implemented
Health/readiness checks	Implemented
Backend failover	Implemented
Resource limits	Implemented
Error handling	Implemented
Request traceability	Implemented
NGINX high availability	Production improvement
Off-host backups	Production improvement
Production Security Priorities

Before production deployment, the highest-priority improvements would be:

Move all secrets to a dedicated secret-management solution.
Use off-host encrypted database backups.
Add centralized logging, monitoring, and alerting.
Add vulnerability scanning to the CI pipeline.
Deploy redundant ingress/reverse-proxy instances.
Apply explicit network policies and least-privilege access.
Regularly test backup restoration and service failure scenarios.
Review and rotate credentials and other sensitive configuration regularly.

The assessment implementation intentionally focuses on the required local
containerized environment. Production controls are clearly identified above
rather than being represented as already implemented.