"""Typed schemas for GitHub API responses and webhook payloads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowRun(BaseModel):
    id: int
    name: str = ""
    head_branch: str = ""
    head_sha: str = ""
    event: str = ""
    status: str = ""
    conclusion: str | None = None
    html_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    run_attempt: int = 1
    repository: str = ""  # owner/repo


class WorkflowJob(BaseModel):
    id: int
    run_id: int
    name: str = ""
    status: str = ""
    conclusion: str | None = None
    started_at: str = ""
    completed_at: str | None = None
    steps: list[dict] = Field(default_factory=list)


class Commit(BaseModel):
    sha: str
    message: str = ""
    author: str = ""
    date: str = ""
    changed_files: list[str] = Field(default_factory=list)


class WebhookWorkflowRunPayload(BaseModel):
    action: str = ""
    workflow_run: dict = Field(default_factory=dict)
    repository: dict = Field(default_factory=dict)
    sender: dict = Field(default_factory=dict)
