# Elevated API Latency

## Expected symptoms
- P95 request duration significantly above baseline.
- Average request duration elevated.
- Error rate usually unchanged (requests still succeed).

## Diagnostic steps
1. Query Prometheus for `http_request_duration_p95` and compare with baseline.
2. Query `db_operation_duration_avg` to see if the database is the bottleneck.
3. Check `demo_dependency_up` for dependency health.
4. Review recent deployments/configuration changes.

## Likely causes
- Slow database queries or missing indexes.
- Upstream dependency slowness.
- Artificial delay introduced by fault injection (demo lab).

## Remediation
- Reset the lab fault: `POST /api/v1/demo/reset` (admin).
- In production: profile slow queries, add indexes, or scale the database.

## Reset
`POST /api/v1/demo/reset` removes the artificial delay.
