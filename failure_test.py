#!/usr/bin/env python3

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
REQUEST_TIMEOUT = 3
REQUEST_COUNT = 20
RECOVERY_TIMEOUT = 60


def run_command(command, timeout=15):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    return result.returncode, result.stdout.strip(), result.stderr.strip()


def http_get(path):
    url = f"{BASE_URL}{path}"

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
        },
    )

    started = time.time()

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:

            body = response.read().decode(
                "utf-8",
                errors="replace",
            )

            elapsed = time.time() - started

            return {
                "success": True,
                "status": response.status,
                "instance": extract_instance(body),
                "elapsed": elapsed,
            }

    except urllib.error.HTTPError as exc:
        elapsed = time.time() - started

        return {
            "success": False,
            "status": exc.code,
            "instance": None,
            "elapsed": elapsed,
        }

    except Exception:
        elapsed = time.time() - started

        return {
            "success": False,
            "status": None,
            "instance": None,
            "elapsed": elapsed,
        }


def extract_instance(body):
    marker = '"instance_id":"'

    if marker not in body:
        return None

    value = body.split(marker, 1)[1]

    return value.split('"', 1)[0]


def send_traffic(count):
    results = []

    for _ in range(count):
        results.append(
            http_get("/instance")
        )

        time.sleep(0.15)

    return results


def summarize(results):
    successes = [
        result
        for result in results
        if result["success"] and result["status"] == 200
    ]

    failures = [
        result
        for result in results
        if not (
            result["success"]
            and result["status"] == 200
        )
    ]

    instances = Counter(
        result["instance"]
        for result in successes
        if result["instance"]
    )

    return successes, failures, instances


def wait_for_container_healthy(container):
    deadline = time.time() + RECOVERY_TIMEOUT

    while time.time() < deadline:
        code, stdout, stderr = run_command(
            [
                "docker",
                "inspect",
                container,
                "--format",
                "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}",
            ]
        )

        if code == 0:
            parts = stdout.split("|", 1)

            state = parts[0]
            health = parts[1] if len(parts) > 1 else ""

            if state == "running" and health == "healthy":
                return True

        time.sleep(2)

    return False


def print_traffic_summary(title, results):
    successes, failures, instances = summarize(results)

    print()
    print(title)
    print("-" * len(title))

    print(f"Total requests: {len(results)}")
    print(f"Successful: {len(successes)}")
    print(f"Failed: {len(failures)}")
    print(f"Instances: {dict(instances)}")

    if successes:
        avg_latency = (
            sum(
                result["elapsed"]
                for result in successes
            )
            / len(successes)
        )

        print(
            f"Average successful latency: "
            f"{avg_latency * 1000:.1f} ms"
        )

    return successes, failures, instances


print("===== BARQ FAILURE / RECOVERY TEST =====")
print(f"BASE_URL: {BASE_URL}")
print(f"Requests per phase: {REQUEST_COUNT}")
print()

# ============================================================
# PRE-CHECK
# ============================================================

print("===== PRE-CHECK =====")

code, stdout, stderr = run_command(
    [
        "docker",
        "inspect",
        "app-01",
        "--format",
        "{{.State.Status}}",
    ]
)

if code != 0 or stdout != "running":
    print("FAIL: app-01 is not running before the test.")
    sys.exit(1)

code, stdout, stderr = run_command(
    [
        "docker",
        "inspect",
        "app-02",
        "--format",
        "{{.State.Status}}",
    ]
)

if code != 0 or stdout != "running":
    print("FAIL: app-02 is not running before the test.")
    sys.exit(1)

print("PASS: app-01 is running")
print("PASS: app-02 is running")


# ============================================================
# BASELINE TRAFFIC
# ============================================================

print()
print("===== BASELINE TRAFFIC =====")

baseline = send_traffic(REQUEST_COUNT)

baseline_successes, baseline_failures, baseline_instances = (
    print_traffic_summary(
        "Baseline results",
        baseline,
    )
)

if not baseline_successes:
    print("FAIL: No successful baseline requests.")
    sys.exit(1)

if "app-01" not in baseline_instances:
    print("FAIL: app-01 did not receive baseline traffic.")
    sys.exit(1)

if "app-02" not in baseline_instances:
    print("FAIL: app-02 did not receive baseline traffic.")
    sys.exit(1)

print("PASS: Both backend instances receive baseline traffic")


# ============================================================
# STOP APP-01
# ============================================================

print()
print("===== STOPPING app-01 =====")

code, stdout, stderr = run_command(
    [
        "docker",
        "stop",
        "app-01",
    ],
    timeout=20,
)

if code != 0:
    print("FAIL: Could not stop app-01.")
    print(stderr)
    sys.exit(1)

print("PASS: app-01 stopped")


# ============================================================
# FAILURE TRAFFIC
# ============================================================

print()
print("===== TRAFFIC WHILE app-01 IS DOWN =====")

failure_phase = send_traffic(REQUEST_COUNT)

failure_successes, failure_failures, failure_instances = (
    print_traffic_summary(
        "Failure-phase results",
        failure_phase,
    )
)

if not failure_successes:
    print(
        "FAIL: No successful requests while app-01 was down."
    )

    # Cleanup
    run_command(["docker", "start", "app-01"])

    sys.exit(1)

if "app-02" not in failure_instances:
    print(
        "FAIL: app-02 did not receive traffic while "
        "app-01 was down."
    )

    # Cleanup
    run_command(["docker", "start", "app-01"])

    sys.exit(1)

print(
    "PASS: Service remained available through app-02"
)

print(
    f"PASS: {len(failure_successes)}/{len(failure_phase)} "
    "requests succeeded while app-01 was down"
)

if failure_failures:
    print(
        f"INFO: {len(failure_failures)} requests failed "
        "during the failure window"
    )


# ============================================================
# RESTORE APP-01
# ============================================================

print()
print("===== RESTORING app-01 =====")

code, stdout, stderr = run_command(
    [
        "docker",
        "start",
        "app-01",
    ],
    timeout=20,
)

if code != 0:
    print("FAIL: Could not start app-01.")
    print(stderr)
    sys.exit(1)

print("PASS: app-01 start requested")

print("Waiting for app-01 to become healthy...")

if not wait_for_container_healthy("app-01"):
    print(
        "FAIL: app-01 did not become healthy "
        f"within {RECOVERY_TIMEOUT} seconds."
    )
    sys.exit(1)

print("PASS: app-01 is healthy again")


# ============================================================
# RECOVERY TRAFFIC
# ============================================================

print()
print("===== RECOVERY TRAFFIC =====")

recovery = send_traffic(REQUEST_COUNT)

recovery_successes, recovery_failures, recovery_instances = (
    print_traffic_summary(
        "Recovery results",
        recovery,
    )
)

if not recovery_successes:
    print("FAIL: No successful requests after recovery.")
    sys.exit(1)

if "app-01" not in recovery_instances:
    print(
        "FAIL: app-01 did not receive traffic after recovery."
    )
    sys.exit(1)

if "app-02" not in recovery_instances:
    print(
        "FAIL: app-02 did not receive traffic after recovery."
    )
    sys.exit(1)

print(
    "PASS: Both backend instances receive traffic "
    "after recovery"
)


# ============================================================
# FINAL HEALTH CHECK
# ============================================================

print()
print("===== FINAL HEALTH CHECK =====")

for container in [
    "app-01",
    "app-02",
    "postgres",
    "redis",
]:
    code, stdout, stderr = run_command(
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}",
        ]
    )

    if code != 0:
        print(f"FAIL: Could not inspect {container}.")
        sys.exit(1)

    parts = stdout.split("|", 1)

    state = parts[0]
    health = parts[1] if len(parts) > 1 else ""

    if state == "running" and (
        health == "healthy"
        or health == "no-healthcheck"
    ):
        print(
            f"PASS: {container} "
            f"state={state}, health={health}"
        )
    else:
        print(
            f"FAIL: {container} "
            f"state={state}, health={health}"
        )
        sys.exit(1)


# ============================================================
# FINAL RESULT
# ============================================================

print()
print("======================================")
print("FAILURE / RECOVERY TEST PASSED")
print("======================================")
print()
print(
    "Evidence:"
)
print(
    "- Baseline traffic reached both app-01 and app-02."
)
print(
    "- app-01 was stopped without docker compose down."
)
print(
    "- Traffic continued through app-02."
)
print(
    "- app-01 was restored and became healthy."
)
print(
    "- Both instances received traffic after recovery."
)

sys.exit(0)