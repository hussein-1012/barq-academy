#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urljoin


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT = 5

passed = 0
failed = 0


def report(ok, message):
    global passed, failed

    if ok:
        print(f"PASS: {message}")
        passed += 1
    else:
        print(f"FAIL: {message}")
        failed += 1


def request(method, path, data=None):
    url = urljoin(BASE_URL + "/", path.lstrip("/"))

    headers = {
        "Accept": "application/json",
    }

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw

            return response.status, payload, dict(response.headers.items())

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw

        return exc.code, payload, dict(exc.headers.items())

    except Exception as exc:
        return None, None, {"error": str(exc)}


def run_command(command, timeout=10):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result.returncode, result.stdout.strip(), result.stderr.strip()

    except Exception as exc:
        return 1, "", str(exc)


def get_header(headers, name):
    name = name.lower()

    for key, value in headers.items():
        if key.lower() == name:
            return value

    return None


def get_instance(payload):
    if not isinstance(payload, dict):
        return None

    if "instance_id" in payload:
        return payload["instance_id"]

    if "instance" in payload:
        return payload["instance"]

    if "data" in payload and isinstance(payload["data"], dict):
        data = payload["data"]

        if "instance_id" in data:
            return data["instance_id"]

        return data.get("instance")

    return None

def get_ready_value(payload, service):
    if not isinstance(payload, dict):
        return None

    # Direct form:
    # {"postgres": true, "redis": true}
    if service in payload:
        return payload[service]

    # Nested form:
    # {"dependencies": {"postgres": true, "redis": true}}
    dependencies = payload.get("dependencies")

    if isinstance(dependencies, dict):
        return dependencies.get(service)

    # Another possible nested form
    checks = payload.get("checks")

    if isinstance(checks, dict):
        value = checks.get(service)

        if isinstance(value, dict):
            return value.get("ready") or value.get("status")

        return value

    return None


def is_ready(value):
    if value is True:
        return True

    if isinstance(value, str):
        return value.lower() in {
            "true",
            "ready",
            "ok",
            "healthy",
            "up",
        }

    return False


def extract_counter(payload):
    if isinstance(payload, int):
        return payload

    if isinstance(payload, dict):
        for key in ["counter", "count", "value"]:
            if key in payload:
                try:
                    return int(payload[key])
                except (ValueError, TypeError):
                    pass

        data = payload.get("data")

        if isinstance(data, dict):
            for key in ["counter", "count", "value"]:
                if key in data:
                    try:
                        return int(data[key])
                    except (ValueError, TypeError):
                        pass

    return None


def inspect_networks(container):
    code, stdout, stderr = run_command(
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{range $name, $network := .NetworkSettings.Networks}}{{$name}} {{end}}",
        ]
    )

    if code != 0:
        return []

    return stdout.split()


def get_docker_services():
    code, stdout, stderr = run_command(
        [
            "docker",
            "compose",
            "ps",
            "--services",
        ]
    )

    if code != 0:
        return set()

    return set(stdout.splitlines())


def get_container_states():
    """
    Use docker inspect instead of compose --format because
    older Docker Compose versions may not support the same
    format fields.
    """

    states = {}

    for container in [
        "app-01",
        "app-02",
        "app-03",
        "nginx",
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

        if code == 0 and stdout:
            parts = stdout.split("|", 1)

            state = parts[0]
            health = parts[1] if len(parts) > 1 else ""

            states[container] = (state, health)

    return states


print("===== BARQ ENVIRONMENT VALIDATION =====")
print(f"BASE_URL: {BASE_URL}")
print()


# ============================================================
# API ENDPOINTS
# ============================================================

print("===== API ENDPOINTS =====")

for path in ["/", "/health", "/ready", "/instance"]:
    status, payload, headers = request("GET", path)

    request_id = get_header(headers, "X-Request-ID")
    instance = get_instance(payload)

    ok = (
        status == 200
        and request_id is not None
        and request_id.strip() != ""
    )

    report(
        ok,
        f"GET {path} - status={status}, "
        f"instance={instance}, "
        f"request_id={'present' if request_id else 'missing'}"
    )


# ============================================================
# READINESS
# ============================================================

status, payload, headers = request("GET", "/ready")

postgres_value = get_ready_value(payload, "postgres")
redis_value = get_ready_value(payload, "redis")

report(
    status == 200 and is_ready(postgres_value),
    f"PostgreSQL readiness - {postgres_value}"
)

report(
    status == 200 and is_ready(redis_value),
    f"Redis readiness - {redis_value}"
)

print()


# ============================================================
# POSTGRES RECORDS
# ============================================================

print("===== POSTGRES RECORDS =====")

status, payload, headers = request("GET", "/records")

report(
    status == 200,
    f"GET /records - status={status}"
)

record_title = "Validator test record"

status, payload, headers = request(
    "POST",
    "/records",
    {"title": record_title},
)

report(
    status == 201,
    f"POST /records - status={status}"
)

status, payload, headers = request("GET", "/records")

persisted = False

records = payload

if isinstance(payload, dict):
    records = payload.get("records", payload.get("data", []))

if isinstance(records, list):
    persisted = any(
        isinstance(record, dict)
        and record.get("title") == record_title
        for record in records
    )

report(
    status == 200 and persisted,
    "Created record persisted"
)

print()


# ============================================================
# REDIS COUNTER
# ============================================================

print("===== REDIS COUNTER =====")

status1, payload1, headers1 = request("GET", "/counter")
status2, payload2, headers2 = request("GET", "/counter")

counter1 = extract_counter(payload1)
counter2 = extract_counter(payload2)

report(
    status1 == 200
    and status2 == 200
    and counter1 is not None
    and counter2 is not None
    and counter2 == counter1 + 1,
    f"Redis atomic counter - values={counter1},{counter2}"
)

print()


# ============================================================
# HTTP CONTRACT
# ============================================================

print("===== HTTP CONTRACT =====")

status, payload, headers = request(
    "GET",
    "/this-route-does-not-exist",
)

report(
    status == 404,
    f"Unknown route returns 404 - status={status}"
)

status, payload, headers = request(
    "POST",
    "/records",
    {"title": ""},
)

report(
    status == 400,
    f"Invalid record returns 400 - status={status}"
)

print()


# ============================================================
# LOAD BALANCING
# ============================================================

print("===== LOAD BALANCING =====")

instances = set()

for _ in range(20):
    status, payload, headers = request(
        "GET",
        "/instance",
    )

    instance = get_instance(payload)

    if instance:
        instances.add(instance)

report(
    "app-01" in instances
    and "app-02" in instances
    and "app-03" in instances,
    f"All backend instances receive traffic - instances={sorted(instances)}"
)
print()


# ============================================================
# DOCKER SERVICES
# ============================================================

print("===== DOCKER SERVICES =====")

services = get_docker_services()

required_services = {
    "app-01",
    "app-02",
    "app-03",
    "nginx",
    "postgres",
    "redis",
}

report(
    required_services.issubset(services),
    f"Required Compose services exist - services={sorted(services)}"
)

states = get_container_states()

for service in sorted(required_services):
    state, health = states.get(
        service,
        ("missing", "missing"),
    )

    if service in {
        "app-01",
        "app-02",
        "app-03",
        "postgres",
        "redis",
    }:
        ok = (
            state == "running"
            and health == "healthy"
        )
    else:
        ok = state == "running"

    report(
        ok,
        f"{service} state={state}, health={health}"
    )

print()


# ============================================================
# NETWORK ISOLATION
# ============================================================

print("===== NETWORK ISOLATION =====")

nginx_networks = inspect_networks("nginx")
postgres_networks = inspect_networks("postgres")
redis_networks = inspect_networks("redis")
app01_networks = inspect_networks("app-01")
app02_networks = inspect_networks("app-02")
app03_networks = inspect_networks("app-03")


report(
    nginx_networks == ["barq-assessment_frontend"],
    f"NGINX is frontend-only - networks={nginx_networks}"
)

report(
    postgres_networks == ["barq-assessment_backend"],
    f"PostgreSQL is backend-only - networks={postgres_networks}"
)

report(
    redis_networks == ["barq-assessment_backend"],
    f"Redis is backend-only - networks={redis_networks}"
)

report(
    "barq-assessment_frontend" in app01_networks
    and "barq-assessment_backend" in app01_networks,
    f"app-01 is on frontend/backend - networks={app01_networks}"
)

report(
    "barq-assessment_frontend" in app02_networks
    and "barq-assessment_backend" in app02_networks,
    f"app-02 is on frontend/backend - networks={app02_networks}"
)

report(
    "barq-assessment_frontend" in app03_networks
    and "barq-assessment_backend" in app03_networks,
    f"app-03 is on frontend/backend - networks={app03_networks}"
)

print()


# ============================================================
# PORT EXPOSURE
# ============================================================

print("===== PORT EXPOSURE =====")

code, stdout, stderr = run_command(
    [
        "docker",
        "ps",
        "--format",
        "{{.Names}}|{{.Ports}}",
    ]
)

ports = {}

if code == 0:
    for line in stdout.splitlines():
        if "|" in line:
            name, value = line.split("|", 1)
            ports[name] = value.strip()

nginx_ports = ports.get("nginx", "")

report(
    "127.0.0.1:8080->80/tcp" in nginx_ports,
    f"Only NGINX publishes host port 8080 - {nginx_ports}"
)

for container in [
    "app-01",
    "app-02",
    "app-03",
    "postgres",
    "redis",
]:
    value = ports.get(container, "")

    report(
        "->" not in value,
        f"{container} has no published host port - "
        f"{value or 'none'}"
    )


# ============================================================
# FINAL RESULT
# ============================================================

print()
print("======================================")
print(f"PASS: {passed}")
print(f"FAIL: {failed}")
print("======================================")

if failed:
    print("VALIDATION FAILED")
    sys.exit(1)

print("VALIDATION PASSED")
sys.exit(0)