"""Canonical registry of demo incident scenarios.

Each scenario defines its expected symptoms, ground-truth cause, reset
procedure, and evaluation expectations. Used by the evaluation harness and
documented as runbooks. The demo API implements the actual fault behavior;
this registry is the source of truth for ground-truth metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioSpec:
    id: str
    title: str
    source: str  # runtime | github_actions
    description: str
    symptoms: list[str]
    ground_truth_cause: str
    expected_evidence: list[str]
    acceptable_alternatives: list[str]
    expected_next_step: str
    reset_instructions: str
    promql_keys: list[str] = field(default_factory=list)


SCENARIOS: dict[str, ScenarioSpec] = {
    "pool-exhaustion": ScenarioSpec(
        id="pool-exhaustion",
        title="PostgreSQL connection-pool exhaustion",
        source="runtime",
        description="All pooled database connections are held, so new requests time out.",
        symptoms=[
            "HTTP 500 errors on database-backed endpoints",
            "Errors mention pool timeout / 'connection timed out'",
            "Prometheus pool utilization at 100%",
            "Health dependency check reports postgresql down",
        ],
        ground_truth_cause=(
            "Database connection-pool exhaustion: connections were checked out and "
            "never released, so the pool has no available connections and new "
            "requests time out waiting for one."
        ),
        expected_evidence=[
            "error logs mentioning pool timeout",
            "prometheus db_pool_checked_out / utilization metrics",
            "service health dependency failure",
        ],
        acceptable_alternatives=[
            "database server overloaded or slow",
            "connection leak in application code",
        ],
        expected_next_step="Reset the fault via POST /api/v1/demo/reset and verify pool metrics return to zero.",
        reset_instructions="POST /api/v1/demo/reset (admin) releases held connections.",
        promql_keys=["db_pool_utilization_ratio", "db_pool_checked_out", "http_5xx_ratio", "error_log_rate"],
    ),
    "elevated-latency": ScenarioSpec(
        id="elevated-latency",
        title="Artificially elevated API latency",
        source="runtime",
        description="Real processing delay added to database-backed requests.",
        symptoms=[
            "P95 request duration well above baseline",
            "Average latency elevated",
            "No error increase (requests still succeed)",
        ],
        ground_truth_cause=(
            "Artificially elevated request latency: a fixed processing delay is "
            "added to database-backed requests, inflating duration percentiles."
        ),
        expected_evidence=[
            "prometheus http_request_duration_p95 / avg",
            "baseline vs current latency comparison",
        ],
        acceptable_alternatives=[
            "slow database queries",
            "upstream dependency slowness",
        ],
        expected_next_step="Compare P95 latency against baseline; reset the fault via POST /api/v1/demo/reset.",
        reset_instructions="POST /api/v1/demo/reset removes the artificial delay.",
        promql_keys=["http_request_duration_p95", "http_request_duration_avg"],
    ),
    "config-failure": ScenarioSpec(
        id="config-failure",
        title="Incorrect application configuration / dependency failure",
        source="runtime",
        description="The service is configured with an unreachable dependency URL.",
        symptoms=[
            "Health dependency check reports external-dependency down",
            "Error logs show connection errors to the dependency",
            "Dependency health metric at 0",
        ],
        ground_truth_cause=(
            "Incorrect application configuration: the external dependency URL "
            "points at an unreachable endpoint, causing real connection failures."
        ),
        expected_evidence=[
            "service health dependency failure for external-dependency",
            "error logs with connection errors",
            "prometheus demo_dependency_up = 0",
        ],
        acceptable_alternatives=[
            "dependency service actually down",
            "network partition",
        ],
        expected_next_step="Correct the dependency configuration; reset via POST /api/v1/demo/reset.",
        reset_instructions="POST /api/v1/demo/reset restores the default dependency URL.",
        promql_keys=["dependency_health", "error_log_rate"],
    ),
    "ci-test-failure": ScenarioSpec(
        id="ci-test-failure",
        title="Failing automated tests in CI",
        source="github_actions",
        description="A pytest step fails because an assertion does not hold.",
        symptoms=[
            "Workflow run conclusion is 'failure'",
            "A test step shows conclusion 'failure'",
            "Logs show a test assertion error",
        ],
        ground_truth_cause=(
            "Failed automated tests: a pytest assertion failed in the test step, "
            "failing the workflow."
        ),
        expected_evidence=[
            "failed job logs with test assertion error",
            "workflow jobs showing the failed test step",
        ],
        acceptable_alternatives=[
            "flaky test",
            "test environment issue",
        ],
        expected_next_step="Read the failing test's assertion and fix the code or the test.",
        reset_instructions="Fix the code; the sample workflow is reset by the repository owner.",
    ),
    "ci-missing-secret": ScenarioSpec(
        id="ci-missing-secret",
        title="Missing environment variable or secret in CI",
        source="github_actions",
        description="A deploy step fails because a required secret is not configured.",
        symptoms=[
            "Workflow run conclusion is 'failure'",
            "A deploy step fails",
            "Logs show a missing environment variable error",
        ],
        ground_truth_cause=(
            "Missing environment variable or secret: the deploy step requires a "
            "secret that is not configured in the repository."
        ),
        expected_evidence=[
            "failed job logs mentioning the missing variable",
            "workflow jobs showing the failed deploy step",
        ],
        acceptable_alternatives=[
            "typo in variable name",
            "expired credentials",
        ],
        expected_next_step="Add the missing secret in repository settings and re-run the workflow.",
        reset_instructions="Configure the secret; re-run the workflow.",
    ),
    "ci-docker-build-failure": ScenarioSpec(
        id="ci-docker-build-failure",
        title="Docker build failure in CI",
        source="github_actions",
        description="The docker build step fails during image construction.",
        symptoms=[
            "Workflow run conclusion is 'failure'",
            "A build step fails",
            "Logs show a Docker build error (e.g. missing file or bad instruction)",
        ],
        ground_truth_cause=(
            "Docker build failure: the image build failed, e.g. due to a missing "
            "build context file or an invalid Dockerfile instruction."
        ),
        expected_evidence=[
            "failed job logs with Docker build error",
            "workflow jobs showing the failed build step",
        ],
        acceptable_alternatives=[
            "base image unavailable",
            "network failure pulling dependencies",
        ],
        expected_next_step="Inspect the Dockerfile and build context; fix the build error.",
        reset_instructions="Fix the Dockerfile; re-run the workflow.",
    ),
}


def get_scenario(scenario_id: str) -> ScenarioSpec | None:
    return SCENARIOS.get(scenario_id)


def all_scenarios() -> list[ScenarioSpec]:
    return list(SCENARIOS.values())
