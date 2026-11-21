# Security Model

## Trust Boundaries

OpenSRE AI has the following trust boundaries:

1. **External inputs (untrusted)** — GitHub webhook payloads, application logs, Prometheus responses, runbook content, commit messages, workflow logs. All external text may contain prompt-injection attempts. The system prompt instructs the model to treat all evidence as data, never instructions.

2. **Model provider (semi-trusted)** — The LLM may produce malformed or unexpected output. All model output is validated against Pydantic schemas before use. Tool calls are validated against allowlists before execution.

3. **Local operator (trusted)** — The person running the stack locally. Admin endpoints are protected by `DEMO_ADMIN_KEY`.

4. **GitHub API (read-only)** — The GitHub client uses read-only endpoints. No repository code is executed. No state-changing GitHub actions are performed.

## Controls

### Webhook Security
- HMAC-SHA256 signature verification using `X-Hub-Signature-256` (constant-time comparison)
- Delivery deduplication via `X-GitHub-Delivery` header
- Repository allowlisting (`GITHUB_ALLOWED_REPOS`)
- Event filtering (only `workflow_run` with `completed` action)
- Rate limiting on the webhook endpoint

### Tool Security
- Per-source tool allowlists (runtime tools vs GitHub tools)
- Pydantic input validation for all tool arguments
- Per-tool timeouts and output size limits
- No shell execution, no arbitrary Python execution, no unrestricted database access
- Prometheus queries use a predefined allowlist (no raw PromQL from the model)
- Secret redaction before logs enter model context or are stored

### Authentication & Authorization
- Demo-control and evaluation endpoints require `X-API-Key` matching `DEMO_ADMIN_KEY`
- Dashboard read endpoints are public (local demo)
- No production credentials are used in the demo

### Data Protection
- Secrets are redacted from logs and evidence excerpts
- No tokens, passwords, or connection strings are logged
- Evidence excerpts are bounded in size
- The GitHub client redacts tokens from job logs

### Infrastructure
- All services run in Docker containers on an internal network
- PostgreSQL is not exposed to the internet (only to Docker internal network)
- No Kubernetes or cloud deployment required for the local MVP

## Known Limitations

- The local demo does not use HTTPS; use ngrok or Cloudflare Tunnel for webhook reception
- The admin API key is a single shared secret (no RBAC)
- The evaluation harness uses keyword matching, not an LLM judge
- The system does not perform any state-changing remediation automatically

## Reporting Vulnerabilities

Please report security vulnerabilities by opening a private security advisory on the GitHub repository. Do not open public issues for security reports.
