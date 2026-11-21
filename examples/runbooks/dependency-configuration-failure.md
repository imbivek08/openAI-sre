# Dependency Configuration Failure

## Expected symptoms
- Health check reports an external dependency as down.
- Error logs contain connection errors (e.g. `ConnectError`, `ConnectionRefusedError`).
- Prometheus `demo_dependency_up{name="external-dependency"}` = 0.

## Diagnostic steps
1. Check service health: `GET /health/dependencies`.
2. Search application logs for `Connection` errors.
3. Query Prometheus for `demo_dependency_health`.
4. Review recent configuration changes in deployments.

## Likely causes
- Incorrect dependency URL in configuration.
- Dependency service actually down.
- Network connectivity issue.

## Remediation
- Reset the lab fault: `POST /api/v1/demo/reset` (admin).
- In production: correct the configuration and roll forward.

## Reset
`POST /api/v1/demo/reset` restores the default dependency URL.
