# Log Analysis

## 1. Scope

This document analyzes the supplied synthetic lab logs for the BARQ Academy DevOps assessment.

The analysis covers:

* `logs/access.log`
* `logs/error.log`
* `logs/application.log`

The analysis was performed using Python and standard Linux/macOS shell tools.

Only observed log evidence is used for conclusions. No real production data or secrets were used.

---

## 2. Log Integrity

Initial line counts:

| Log               | Total Lines | Valid JSON | Malformed |
| ----------------- | ----------: | ---------: | --------: |
| `access.log`      |         726 |        725 |         1 |
| `application.log` |         730 |        729 |         1 |
| `error.log`       |          68 |        N/A |       N/A |

Both JSON logs contain one malformed/non-JSON line. The malformed records were excluded from JSON-based statistical analysis rather than modified.

`error.log` contains 68 lines. The final line is a log collector notice rather than an upstream request error:

```text
2026/08/20 11:30:00 [notice] 31#31: log collector rotated stream
```

Therefore, this line was not counted as an NGINX request failure.

---

## 3. Access Log Analysis

### 3.1 HTTP Status Distribution

The 725 valid access records contain:

| Status    |   Count |
| --------- | ------: |
| `200`     |     620 |
| `404`     |      10 |
| `502`     |      40 |
| `503`     |      47 |
| `504`     |       8 |
| **Total** | **725** |

There were therefore:

* 620 successful responses (`200`)
* 10 `404` responses
* 95 upstream/server failure responses (`502`, `503`, `504`)

The `404` responses are associated with requests to `/missing` and represent requests for a deliberately missing endpoint.

### 3.2 Request Paths

| Path        | Requests |
| ----------- | -------: |
| `/`         |      123 |
| `/records`  |      119 |
| `/instance` |      119 |
| `/health`   |      118 |
| `/ready`    |      118 |
| `/counter`  |      118 |
| `/missing`  |       10 |

The workload is distributed across the main application endpoints, with `/missing` specifically producing the observed `404` responses.

### 3.3 Upstream Distribution

The access log contains:

| Upstream                       | Records |
| ------------------------------ | ------: |
| `172.23.0.11:8080`             |     365 |
| `172.23.0.12:8080`             |     341 |
| Retry involving both upstreams |      19 |

The records containing both upstreams show retry behavior. For example, one request was observed with:

```text
upstream: 172.23.0.12:8080, 172.23.0.11:8080
upstream_status: 502, 200
```

This demonstrates that NGINX attempted the first upstream, received a failure, and successfully retried another upstream for that request.

---

## 4. Application Log Analysis

### 4.1 Event Types

The 729 valid application log records contain:

| Event              | Count |
| ------------------ | ----: |
| `http_request`     |   682 |
| `dependency_error` |    47 |

The application log therefore contains both HTTP request events and dependency failure events.

### 4.2 HTTP Status Distribution

Among application records containing an HTTP status:

| Status | Count |
| ------ | ----: |
| `200`  |   625 |
| `503`  |    47 |
| `404`  |    10 |

The 47 records without an HTTP status are dependency error events.

### 4.3 Application Instances

Application records are distributed between the two Flask instances:

| Instance | Records |
| -------- | ------: |
| `app-01` |     404 |
| `app-02` |     325 |

The application logs therefore confirm activity from both application instances.

---

## 5. Dependency Error Analysis

There are exactly 47 `dependency_error` events in `application.log`.

### 5.1 Errors by Instance

| Instance  | Redis Errors |
| --------- | -----------: |
| `app-01`  |           23 |
| `app-02`  |           24 |
| **Total** |       **47** |

Both application instances were affected.

### 5.2 Errors by Type

| Error Type        |  Count |
| ----------------- | -----: |
| `TimeoutError`    |     31 |
| `InvalidPassword` |     16 |
| **Total**         | **47** |

The logs therefore show two distinct Redis failure modes during the dependency incident:

1. Redis connection timeouts.
2. Redis authentication failures caused by an invalid password.

The evidence does not support reducing the entire incident to only one of these error types.

### 5.3 HTTP 503 Responses by Instance

The application produced 47 HTTP `503` responses:

| Instance  | HTTP 503 |
| --------- | -------: |
| `app-01`  |       23 |
| `app-02`  |       24 |
| **Total** |   **47** |

The distribution exactly matches the Redis dependency error distribution.

### 5.4 HTTP 503 Responses by Endpoint

| Endpoint   | HTTP 503 |
| ---------- | -------: |
| `/ready`   |       23 |
| `/counter` |       16 |
| `/records` |        8 |
| **Total**  |   **47** |

The affected endpoints were therefore `/ready`, `/counter`, and `/records`.

---

## 6. Redis Incident Timeline

The first Redis dependency error occurred at:

```text
2026-08-20T11:12:09.524Z
```

The last Redis dependency error occurred at:

```text
2026-08-20T11:21:45.040Z
```

Therefore, the observed Redis dependency failure window was approximately:

```text
11:12:09 → 11:21:45
```

During this period:

* Both `app-01` and `app-02` generated Redis dependency errors.
* 31 errors were `TimeoutError`.
* 16 errors were `InvalidPassword`.
* All 47 corresponding HTTP failures were `503`.

This indicates that the application instances were both affected by a shared Redis dependency problem.

---

## 7. NGINX Error Analysis

The NGINX error log contains a major upstream failure sequence beginning at:

```text
2026/08/20 11:05:02
```

and continuing through:

```text
2026/08/20 11:09:57
```

The request IDs in this sequence include:

```text
lab-000122
lab-000124
lab-000126
...
lab-000236
lab-000240
```

The errors during this period repeatedly reference:

```text
172.23.0.12:8080
```

A second smaller error sequence occurs between:

```text
11:25:14
```

and:

```text
11:26:47
```

with request IDs:

```text
lab-000606
lab-000607
lab-000618
lab-000619
lab-000630
lab-000631
lab-000642
lab-000643
```

The final `error.log` entry at 11:30 is a log rotation notice and is not considered a request failure.

---

## 8. Cross-Log Correlation

The logs can be correlated using the shared `request_id`.

For example:

```text
lab-000122
```

appears in the NGINX error log and access log.

The access record shows:

```text
path: /health
status: 502
upstream: 172.23.0.12:8080
upstream_status: 502
```

Another example is:

```text
lab-000124
```

The access log shows:

```text
path: /ready
status: 200
upstream: 172.23.0.12:8080, 172.23.0.11:8080
upstream_status: 502, 200
```

This demonstrates the following sequence:

```text
Client request
      |
      v
NGINX
      |
      v
172.23.0.12:8080
      |
    502
      |
      v
NGINX retry
      |
      v
172.23.0.11:8080
      |
    200
      |
      v
Client
```

Therefore, the logs provide direct evidence of upstream failure followed by successful retry for some requests.

Not every request in the NGINX failure period succeeded after retry; the access log also contains final `502`, `503`, and `504` responses.

---

## 9. Redis Cross-Log Correlation

The strongest correlation in the application logs is between `dependency_error` and `http_request`.

For example:

```text
request_id: lab-000292
instance: app-02
dependency: redis
error_type: TimeoutError
```

The same request ID then appears as:

```text
request_id: lab-000292
instance: app-02
path: /ready
status: 503
```

The same pattern is observed for the other Redis dependency failures.

Across the entire dataset:

```text
47 Redis dependency errors
47 HTTP 503 responses
```

with identical instance distribution:

```text
app-01: 23
app-02: 24
```

This provides direct evidence that the Redis dependency failures were associated with the application's `503` responses.

---

## 10. Request ID Observations

### Access Log

The 725 valid access records contain:

```text
720 unique request IDs
```

There are five duplicated request IDs:

```text
lab-000121
lab-000241
lab-000361
lab-000481
lab-000601
```

Each appears twice with identical request data:

* Same path: `/`
* Same upstream: `172.23.0.11:8080`
* Same status: `200`
* Same upstream status: `200`

Because the duplicated records are identical, they are treated as duplicate access-log records rather than evidence of an upstream retry.

### Application Log

The application log contains:

```text
729 records
680 unique request IDs
```

The application log has 49 duplicated request IDs.

These duplicates have a different meaning from the access-log duplicates.

For Redis failures, the same request ID is used for two different application events:

```text
dependency_error
        +
http_request
```

For example:

```text
lab-000292
```

has:

```text
dependency_error → Redis TimeoutError
http_request     → /ready → 503
```

Therefore, these records should not be treated as duplicate requests. They represent multiple log events associated with the same request.

---

## 11. Failure Timeline

The observed events can be summarized chronologically as follows:

| Time         | Observation                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------- |
| 11:00 onward | Normal application traffic including `200` responses and expected `/missing` `404` responses |
| 11:05:02     | NGINX upstream error sequence begins                                                         |
| 11:05–11:09  | Repeated upstream errors involving `172.23.0.12:8080`; some requests succeed after retry     |
| 11:09:57     | Last request in the first major NGINX error sequence                                         |
| 11:12:09     | First Redis dependency error                                                                 |
| 11:12–11:21  | Redis `TimeoutError` and `InvalidPassword` events affect both application instances          |
| 11:21:45     | Last observed Redis dependency error                                                         |
| 11:25:14     | Second smaller NGINX error sequence begins                                                   |
| 11:26:47     | Last request in the second NGINX error sequence                                              |
| 11:30:00     | NGINX log collector rotation notice                                                          |

The NGINX upstream failures and Redis dependency failures occur in separate time windows and are therefore analyzed as separate incidents.

---

## 12. Root Cause Findings

### 12.1 Upstream/Application Connectivity Failure

The NGINX logs show repeated failures when communicating with:

```text
172.23.0.12:8080
```

The access log confirms corresponding `502` responses and, for some requests, successful retries to:

```text
172.23.0.11:8080
```

The evidence therefore indicates an upstream availability/connectivity problem involving one backend during the observed failure window.

The logs alone do not establish the exact internal reason why that upstream failed.

### 12.2 Redis Dependency Failure

The application logs provide stronger evidence for the Redis incident.

There are:

```text
47 dependency_error events
```

consisting of:

```text
31 TimeoutError
16 InvalidPassword
```

and these correspond exactly to:

```text
47 HTTP 503 responses
```

Both application instances were affected:

```text
app-01 → 23
app-02 → 24
```

Therefore, the evidence supports a shared Redis dependency failure rather than an isolated failure of one Flask instance.

The presence of `InvalidPassword` indicates an authentication/configuration failure was observed.

The presence of `TimeoutError` indicates connection/response timeout failures were also observed.

---

## 13. Impact

The access log contains 725 valid requests.

Observed responses were:

```text
620 × 200
10  × 404
40  × 502
47  × 503
8   × 504
```

Therefore:

* Normal successful responses: 620
* Expected missing-endpoint responses: 10
* Upstream/server failure responses: 95

The application-level Redis incident specifically resulted in:

```text
47 HTTP 503 responses
```

affecting:

```text
app-01 and app-02
```

and the following endpoints:

```text
/ready
/counter
/records
```

---

## 14. Key Findings

### Finding 1 — Upstream Failure

A significant NGINX upstream failure sequence occurred between approximately:

```text
11:05:02 and 11:09:57
```

The failing upstream repeatedly referenced:

```text
172.23.0.12:8080
```

### Finding 2 — NGINX Retry Behavior

Some requests that initially received `502` from the first upstream were retried against the second upstream and successfully returned `200`.

Example:

```text
upstream_status: 502, 200
```

### Finding 3 — Shared Redis Failure

Between approximately:

```text
11:12:09 and 11:21:45
```

both application instances experienced Redis dependency failures.

### Finding 4 — Redis Failure Types

The Redis incident contained two observed failure types:

```text
31 TimeoutError
16 InvalidPassword
```

### Finding 5 — Direct Error-to-503 Correlation

The 47 Redis dependency errors correspond exactly to 47 application-level `503` responses.

### Finding 6 — Both Instances Were Affected

The Redis failures were distributed almost evenly:

```text
app-01: 23
app-02: 24
```

This supports the conclusion that the problem was with a shared dependency rather than a single application container.

### Finding 7 — Expected 404 Responses

All 10 observed `404` responses were associated with `/missing`.

These are treated as expected missing-resource responses rather than infrastructure failures.

### Finding 8 — Log Collector Notice

The final `error.log` line at 11:30 is a log collector rotation notice and was excluded from request-error counts.

---

## 15. Reproducible Analysis Commands

### Count log lines

```bash
wc -l logs/access.log logs/error.log logs/application.log
```

### Analyze JSON logs using Python

```bash
python3 <<'PY'
import json
from collections import Counter

def read_json_log(path):
    records = []
    bad = 0

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1

    return records, bad

access, access_bad = read_json_log("logs/access.log")
app, app_bad = read_json_log("logs/application.log")

print("=== FILE COUNTS ===")
print("access.log lines:", len(access) + access_bad)
print("access.log valid JSON:", len(access))
print("access.log malformed:", access_bad)
print("application.log lines:", len(app) + app_bad)
print("application.log valid JSON:", len(app))
print("application.log malformed:", app_bad)

print("\n=== ACCESS STATUS ===")
print(Counter(r.get("status") for r in access))

print("\n=== ACCESS PATH ===")
print(Counter(r.get("path") for r in access))

print("\n=== ACCESS UPSTREAM ===")
print(Counter(r.get("upstream") for r in access))

print("\n=== ACCESS REQUEST IDS ===")
request_ids = [r["request_id"] for r in access if "request_id" in r]
print("records with request_id:", len(request_ids))
print("unique request IDs:", len(set(request_ids)))

print("\n=== APPLICATION EVENT TYPES ===")
print(Counter(r.get("event", "NO_EVENT") for r in app))

print("\n=== APPLICATION STATUS ===")
status_records = [r for r in app if "status" in r]
print(Counter(r["status"] for r in status_records))

print("\n=== APPLICATION INSTANCES ===")
print(Counter(r.get("instance_id", "NO_INSTANCE") for r in app))

print("\n=== APPLICATION REQUEST IDS ===")
request_ids = [r["request_id"] for r in app if "request_id" in r]
print("records with request_id:", len(request_ids))
print("unique request IDs:", len(set(request_ids)))

print("\n=== APPLICATION ERRORS ===")
errors = [
    r for r in app
    if isinstance(r.get("status"), int) and r["status"] >= 400
]
print("error responses:", len(errors))
PY
```

### Correlate NGINX errors with request IDs

```bash
grep -o 'request_id=[^,]*' logs/error.log | sort | uniq -c
```

### Inspect NGINX error timeline

```bash
awk '{print $1, $2, $NF}' logs/error.log
```

### Analyze Redis failures

```bash
python3 <<'PY'
import json
from collections import Counter

records = []

with open("logs/application.log") as f:
    for line in f:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass

errors = [
    r for r in records
    if r.get("event") == "dependency_error"
]

print("=== REDIS ERRORS BY INSTANCE ===")
print(Counter(r.get("instance_id") for r in errors))

print("\n=== REDIS ERRORS BY ERROR TYPE ===")
print(Counter(r.get("error_type") for r in errors))

print("\n=== 503 REQUESTS BY INSTANCE ===")
requests_503 = [
    r for r in records
    if r.get("event") == "http_request"
    and r.get("status") == 503
]
print(Counter(r.get("instance_id") for r in requests_503))

print("\n=== 503 REQUESTS BY PATH ===")
print(Counter(r.get("path") for r in requests_503))

print("\n=== REDIS ERROR TIME RANGE ===")
times = [r["timestamp"] for r in errors]
print("first:", min(times))
print("last :", max(times))
print("count:", len(errors))
PY
```

---

## 16. Conclusion

The supplied logs show two distinct infrastructure/dependency failure periods.

The first occurred around 11:05 and involved repeated NGINX upstream failures against `172.23.0.12:8080`. Some requests recovered through NGINX retry to the other backend, while others resulted in `502`, `503`, or `504` responses.

The second occurred between approximately 11:12 and 11:21 and involved Redis dependency failures affecting both Flask application instances. The application logs identify 31 `TimeoutError` events and 16 `InvalidPassword` events. These 47 dependency failures correspond exactly to 47 HTTP `503` responses.

The cross-log correlation using `request_id` provides evidence linking infrastructure/dependency failures to the resulting HTTP responses.

The analysis also distinguishes actual request failures from expected `404` responses and from the final NGINX log collector rotation notice.

All conclusions in this document are based on the observed synthetic lab logs and the reproducible analysis commands documented above.
