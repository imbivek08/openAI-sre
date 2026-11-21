# CI Missing Secret / Environment Variable

## Expected symptoms
- Workflow run conclusion is `failure`.
- A deploy or test step fails.
- Logs show a missing environment variable or secret error.

## Diagnostic steps
1. Get the workflow run and identify the failed job.
2. Download the failed job logs and find the missing variable name.
3. Compare the workflow file with the repository's configured secrets.

## Likely causes
- Required secret not configured in repository settings.
- Typo in the secret name referenced by the workflow.
- Secret expired or was rotated.

## Remediation
- Add or correct the secret in repository settings.
- Re-run the workflow.

## Reset
Configure the secret; re-run the workflow.
