Troubleshooting Journal

This document records the actual troubleshooting performed during the assessment.

Only observed symptoms, commands, results, root causes, fixes, and retests are documented.

1. Application Binding Prevented NGINX Connectivity
Symptom

NGINX could not reliably reach the Flask application containers.

Hypothesis

The Flask application was bound to 127.0.0.1, which makes it reachable only from inside its own container instead of from other containers on the Docker network.

Command / Test

Inspected the application configuration and Compose environment variables.

Actual Finding

The application was configured with:

APP_HOST=127.0.0.1
Root Cause

The Flask server was listening only on the container loopback interface.

Fix

Changed the application binding to:

APP_HOST=0.0.0.0
Retest Evidence

The application containers became reachable through NGINX and the validation test passed.

Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

The assessment environment was validated locally. Production deployment would require additional external network and ingress testing.

2. Application Health Check Used the Wrong Endpoint
Symptom

The application health check did not match the required readiness endpoint.

Hypothesis

The container health check was calling an endpoint that did not represent PostgreSQL and Redis readiness.

Command / Test

Inspected the Docker Compose health check configuration.

Actual Finding

The health check used:

/healthz

while the required readiness endpoint was:

/ready
Root Cause

The container health check was configured against the wrong application endpoint.

Fix

Changed the Docker health check to call:

/ready
Retest Evidence

Both application containers reported:

running (healthy)

The validation script also reported:

PASS: PostgreSQL readiness - ready
PASS: Redis readiness - ready
Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

The health check validates readiness from inside the application container; external monitoring would still be required in production.

3. Database and Redis Connection Configuration Was Incorrect
Symptom

The application dependency configuration did not match the ports and credentials exposed by the Compose services.

Hypothesis

The application was using incorrect database and cache connection settings.

Command / Test

Inspected the Compose service definitions and application environment configuration.

Actual Findings

The application configuration contained incorrect dependency connection settings, including:

PostgreSQL port 5433 instead of 5432.
Redis port 6380 instead of 6379.
PostgreSQL credentials did not match the PostgreSQL container configuration.
Root Cause

The application was configured with incorrect dependency connection settings instead of the Docker service names and internal service ports.

Fix

Updated the application configuration to use:

postgres:5432
redis:6379

and aligned the PostgreSQL credentials.

Retest Evidence

The validation script reported:

PASS: PostgreSQL readiness - ready
PASS: Redis readiness - ready

The /ready endpoint returned HTTP 200.

Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

Production credentials must be supplied through a proper secret-management mechanism rather than repository files.

4. Application Instances Were Not Uniquely Identified
Symptom

The two application containers did not have distinct backend identities.

Hypothesis

Both instances were configured with the same INSTANCE_ID.

Command / Test

Inspected the Compose environment configuration and repeatedly called /instance.

Actual Finding

app-02 was configured with:

INSTANCE_ID=app-01
Root Cause

The second application instance inherited the identity of the first instance.

Fix

Configured the instances as:

app-01 -> INSTANCE_ID=app-01
app-02 -> INSTANCE_ID=app-02
Retest Evidence

Repeated /instance requests reached both instances.

The validation script reported:

PASS: Both backend instances receive traffic

with:

instances=['app-01', 'app-02']
Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

A production deployment with more replicas would require a scalable identity/discovery strategy.

5. PostgreSQL Storage Was Not Using the Required Named Volume
Symptom

PostgreSQL storage configuration did not provide the required persistent named volume.

Hypothesis

The database data directory was mapped to an unsuitable host or temporary storage configuration.

Command / Test

Inspected the PostgreSQL Compose volume configuration.

Actual Finding

The PostgreSQL data directory was not correctly backed by a named Docker volume.

Root Cause

The database storage mapping did not provide reliable container-independent persistence.

Fix

Changed the configuration to:

postgres-data:/var/lib/postgresql/data
Retest Evidence

The Docker volume was present as:

barq-assessment_postgres-data

PostgreSQL was recreated with:

docker compose up -d --force-recreate postgres app-01 app-02

After recreation, the record:

Backup Restore Proof

was still present.

Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

The named volume provides local persistence but is not itself a disaster-recovery solution. Regular external backups are still required.

6. NGINX Upstream Configuration Prevented Correct Load Balancing and Failover
Symptom

The NGINX upstream configuration did not match the actual application ports and did not provide the required retry behavior.

Hypothesis

NGINX was forwarding requests to incorrect application ports and was not retrying failed upstream requests.

Command / Test

Inspected nginx/nginx.conf and tested repeated requests through the public endpoint.

Actual Findings

The upstream configuration referenced incorrect application ports, and upstream retry behavior was disabled.

Root Cause

The reverse proxy configuration did not match the Docker service network configuration.

Fix

Updated the upstream servers to:

app-01:8080
app-02:8080

and enabled retries for upstream errors and timeouts.

Retest Evidence

Repeated /instance requests reached both backend instances.

The validation test reported:

PASS: Both backend instances receive traffic

The failure/recovery test also proved continued service availability after stopping app-01.

Related Commit

be7ae1b — fix: repair container networking and service readiness

Remaining Uncertainty

NGINX remains a single edge instance in the assessment architecture and is therefore a potential production single point of failure.

7. Backend Failure and Recovery Test
Symptom

A backend failure needed to be tested to verify service availability.

Hypothesis

If one backend instance is stopped, NGINX should continue serving requests through the remaining instance.

Command / Test

Ran:

./failure_test.py

The test stopped only app-01 without running docker compose down.

Actual Result

Baseline:

Total requests: 20
Successful: 20
Failed: 0
Instances: {'app-02': 10, 'app-01': 10}

While app-01 was down:

Total requests: 20
Successful: 20
Failed: 0
Instances: {'app-02': 20}

After recovery:

Total requests: 20
Successful: 20
Failed: 0
Instances: {'app-02': 11, 'app-01': 9}
Root Cause

The test intentionally introduced an application-instance failure.

Fix

No permanent configuration change was required for this test. The NGINX failover configuration allowed traffic to continue through app-02.

Retest Evidence

app-01 was restarted and became healthy again.

Final state:

app-01: running, healthy
app-02: running, healthy
postgres: running, healthy
redis: running, healthy
Related Commit

c2526a0 — test: add backend failure recovery test

Remaining Uncertainty

The test validates one backend failure. It does not prove high availability of the NGINX edge itself.

8. PostgreSQL Backup and Restore
Symptom

The assessment required a real PostgreSQL backup and restore proof.

Hypothesis

A PostgreSQL dump should allow a deleted record to be restored.

Command / Test

Created the record:

Backup Restore Proof

Created backup:

backups/barq_tasks_20260906_184603.dump

Deleted the record using PostgreSQL:

DELETE 1

Restored the backup using:

./restore.sh backups/barq_tasks_20260906_184603.dump
Actual Result

The restore completed successfully:

PASS: PostgreSQL restore completed.

The subsequent /records request showed:

{"id":9,"title":"Backup Restore Proof"}
Root Cause

The record had intentionally been deleted as part of the recovery test.

Fix

Restored the PostgreSQL database from the generated dump.

Retest Evidence

The deleted record was present again after restoration.

Related Commit

710cfc9 — feat: add PostgreSQL backup and restore

Remaining Uncertainty

The backup is currently a local dump. Production requires encrypted, off-host, regularly scheduled backups and tested retention.

Summary

The main troubleshooting themes were:

Container-to-container connectivity.
Correct health/readiness semantics.
Correct PostgreSQL and Redis service addressing.
Unique backend identity.
Persistent database storage.
NGINX load balancing and upstream failover.
Backend failure and recovery.
PostgreSQL backup and restore.

All implemented fixes were retested using the validation and recovery procedures available in the repository.