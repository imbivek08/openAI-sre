"""Tool allowlists and validation policies per incident source."""

from __future__ import annotations

from .schemas import EngineLimits

RUNTIME_TOOLS = [
    "query_prometheus",
    "search_application_logs",
    "get_service_health",
    "get_recent_deployments",
    "search_runbook",
]

GITHUB_TOOLS = [
    "get_workflow_run",
    "get_workflow_jobs",
    "get_failed_job_logs",
    "get_commit_details",
    "get_changed_files",
]

MANUAL_TOOLS = RUNTIME_TOOLS


def allowed_tools_for(source: str) -> list[str]:
    if source == "github_actions":
        return list(GITHUB_TOOLS)
    if source == "manual":
        return list(MANUAL_TOOLS)
    return list(RUNTIME_TOOLS)


def default_limits() -> EngineLimits:
    return EngineLimits()
