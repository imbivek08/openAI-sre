"""Read-only GitHub REST API client with pagination, rate limits and redaction."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from integrations.github.redact import redact_text

logger = logging.getLogger(__name__)

USER_AGENT = "opensre-ai/0.1"
PER_PAGE = 100


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubRateLimitError(GitHubError):
    pass


class GitHubAuthError(GitHubError):
    pass


class GitHubClient:
    def __init__(self, token: str, timeout: float = 30.0, max_retries: int = 2) -> None:
        if not token:
            raise GitHubAuthError("No GitHub token configured")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    # --- internal ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(method, url, headers=self._headers(), **kwargs)
            except httpx.TimeoutException as exc:
                last_error = GitHubError(f"GitHub timeout: {exc}")
            except httpx.HTTPError as exc:
                last_error = GitHubError(f"GitHub connection error: {exc}")
            else:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining == "0" and resp.status_code != 200:
                    reset = resp.headers.get("X-RateLimit-Reset")
                    wait = _seconds_until_reset(reset)
                    raise GitHubRateLimitError(
                        f"GitHub API rate limit exceeded; resets in {wait:.0f}s"
                    )
                if resp.status_code == 401 or resp.status_code == 403:
                    raise GitHubAuthError(
                        f"GitHub authentication/authorization failed (HTTP {resp.status_code})",
                        status_code=resp.status_code,
                    )
                if resp.status_code >= 500:
                    last_error = GitHubError(f"GitHub HTTP {resp.status_code}", status_code=resp.status_code)
                elif resp.status_code >= 400:
                    raise GitHubError(
                        f"GitHub HTTP {resp.status_code}: {resp.text[:300]}",
                        status_code=resp.status_code,
                    )
                else:
                    return resp
            logger.warning("GitHub request attempt %d failed: %s", attempt + 1, last_error)
        raise last_error or GitHubError("GitHub request failed")

    async def _paginate(self, url: str, params: dict | None = None) -> list[dict]:
        results: list[dict] = []
        params = {**(params or {}), "per_page": PER_PAGE}
        page = 1
        while True:
            resp = await self._request("GET", url, params={**params, "page": page})
            data = resp.json()
            if not isinstance(data, list):
                raise GitHubError(f"Expected list response from {url}")
            results.extend(data)
            if len(data) < PER_PAGE:
                break
            page += 1
            if page > 50:  # hard cap: 5000 items
                break
        return results

    # --- workflow runs ------------------------------------------------------

    async def get_workflow_run(self, owner: str, repo: str, run_id: int) -> dict:
        resp = await self._request("GET", f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}")
        return resp.json()

    async def get_workflow_jobs(self, owner: str, repo: str, run_id: int) -> list[dict]:
        return await self._paginate(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        )

    async def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        """Download job logs. Returned text is redacted by the caller before storage."""
        resp = await self._request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            follow_redirects=False,
        )
        if resp.status_code in (301, 302):
            location = resp.headers.get("location", "")
            if location:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    log_resp = await client.get(location)
                return log_resp.text
        return resp.text

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict:
        resp = await self._request(
            "GET", f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
        )
        return resp.json()

    async def get_workflow_file(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Fetch a workflow file's content (base64-encoded by the API)."""
        import base64

        resp = await self._request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        data = resp.json()
        content = data.get("content", "")
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return content

    async def get_repo(self, owner: str, repo: str) -> dict:
        resp = await self._request("GET", f"https://api.github.com/repos/{owner}/{repo}")
        return resp.json()


def redact_logs(raw: str, max_bytes: int = 256_000) -> str:
    """Redact and bound job log content before it enters a report or model context."""
    bounded = raw.encode("utf-8", errors="replace")[:max_bytes].decode("utf-8", errors="replace")
    return redact_text(bounded)


def _seconds_until_reset(reset: str | None) -> float:
    if not reset:
        return 60.0
    try:
        reset_ts = int(reset)
    except ValueError:
        return 60.0
    return max(0.0, reset_ts - datetime.now(UTC).timestamp() + 1)
