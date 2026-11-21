# CI Docker Build Failure

## Expected symptoms
- Workflow run conclusion is `failure`.
- A Docker build step fails.
- Logs show a build error (missing file, invalid instruction, base image pull failure).

## Diagnostic steps
1. Get the workflow run and identify the failed build job.
2. Download the failed job logs and find the first Docker error.
3. Check changed files in the commit for Dockerfile or build-context changes.

## Likely causes
- Missing file referenced by the Dockerfile (e.g. `.dockerignore` issue).
- Invalid Dockerfile instruction.
- Base image unavailable or network failure pulling it.

## Remediation
- Fix the Dockerfile or build context.
- Re-run the workflow.

## Reset
Fix the Dockerfile; re-run the workflow.
