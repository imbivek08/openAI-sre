# CI Test Failure

## Expected symptoms
- Workflow run conclusion is `failure`.
- A test step (e.g. `pytest`) shows conclusion `failure`.
- Job logs show a test assertion error or stack trace.

## Diagnostic steps
1. Get the workflow run and identify failed jobs.
2. Download the failed job logs and find the first error.
3. Get the commit details and changed files to see what changed.
4. Check whether the failure is deterministic or flaky.

## Likely causes
- Failing automated tests (regression).
- Flaky test (timing, ordering, external dependency).
- Test environment misconfiguration.

## Remediation
- Read the failing assertion; fix the code or the test.
- Re-run the workflow to confirm the fix.

## Reset
Fix the underlying code; no lab reset required.
