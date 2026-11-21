# PostgreSQL Connection-Pool Exhaustion

## Expected symptoms
- HTTP 500 errors on database-backed endpoints.
- Log messages containing `PoolTimeoutError` or `connection timed out`.
- Prometheus `demo_db_pool_utilization_ratio` near 1.0.
- Health check reports the `postgresql` dependency as down.

## Diagnostic steps
1. Query Prometheus for `db_pool_utilization_ratio` and `db_pool_checkedout`.
2. Search application logs for `pool timeout` or `PoolTimeoutError`.
3. Check service health: `GET /health/dependencies`.
4. Correlate with recent deployments/configuration changes.

## Likely causes
- Connections checked out and never released (connection leak).
- Pool size too small for the concurrency load.
- Long-running queries holding connections.

## Remediation
- Reset the lab fault: `POST /api/v1/demo/reset` (admin).
- In production: fix the leak, increase `pool_size`, or reduce `pool_timeout`.
- Add monitoring alerts on pool utilization > 80%.

## Reset
`POST /api/v1/demo/reset` releases held connections and restores normal operation.
