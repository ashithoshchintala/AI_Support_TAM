"""
Run all Task 1 and Task 2 evaluation cases.

This module generates:
- eval_report.json
- eval_report.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data_repository import (
    DataRepository,
    get_repository,
)
from app.prompts.tam_summary_v1 import TAM_PROMPT_VERSION
from app.prompts.triage_v1 import TRIAGE_PROMPT_VERSION
from app.tam_summarizer import summarize_account
from app.triage_agent import triage_ticket
from evals.scoring import (
    score_task1_case,
    score_task2_case,
)
from evals.test_cases import (
    TASK1_CASES,
    TASK2_CASES,
)


# The project root is one directory above evals/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

JSON_REPORT_PATH = PROJECT_ROOT / "eval_report.json"
MARKDOWN_REPORT_PATH = PROJECT_ROOT / "eval_report.md"


def create_runtime_failure(
    test_id: str,
    name: str,
    task: str,
    adversarial: bool,
    error: Exception,
) -> dict[str, Any]:
    """
    Create a controlled failed result when a test crashes.

    This prevents one failed API request from stopping the
    complete evaluation run.
    """

    return {
        "test_id": test_id,
        "name": name,
        "task": task,
        "adversarial": adversarial,
        "passed": False,
        "quality_score": 0.0,
        "checks": {
            "execution_succeeded": 0.0,
        },
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }


def normalize_result(
    scored_result: dict[str, Any],
    test_id: str,
    name: str,
    task: str,
    adversarial: bool,
) -> dict[str, Any]:
    """
    Give every evaluation result the same top-level structure.
    """

    result = dict(scored_result)

    result["test_id"] = test_id
    result["name"] = name
    result["task"] = task
    result["adversarial"] = adversarial
    result["passed"] = bool(
        result.get("passed", False)
    )

    quality_score = float(
        result.get("quality_score", 0.0)
    )

    # Keep the score inside the assignment's required
    # range of 0 to 1.
    quality_score = max(
        0.0,
        min(1.0, quality_score),
    )

    result["quality_score"] = round(
        quality_score,
        4,
    )

    return result


def run_task1_evaluations(
    repository: DataRepository,
) -> list[dict[str, Any]]:
    """
    Execute and score all five Task 1 cases.
    """

    results: list[dict[str, Any]] = []

    for index, case in enumerate(
        TASK1_CASES,
        start=1,
    ):
        print(
            f"[Task 1: {index}/{len(TASK1_CASES)}] "
            f"{case.name}"
        )

        try:
            triage_result = triage_ticket(
                case.ticket_input
            )

            scored_result = score_task1_case(
                case=case,
                result=triage_result,
                repository=repository,
            )

            result = normalize_result(
                scored_result=scored_result,
                test_id=case.test_id,
                name=case.name,
                task="Task 1",
                adversarial=case.adversarial,
            )

        except Exception as error:
            result = create_runtime_failure(
                test_id=case.test_id,
                name=case.name,
                task="Task 1",
                adversarial=case.adversarial,
                error=error,
            )

        results.append(result)

        print(
            "  Result:",
            "PASS" if result["passed"] else "FAIL",
            "| Quality:",
            result["quality_score"],
        )

    return results


def run_task2_evaluations(
    repository: DataRepository,
) -> list[dict[str, Any]]:
    """
    Execute and score all five Task 2 cases.
    """

    results: list[dict[str, Any]] = []

    for index, case in enumerate(
        TASK2_CASES,
        start=1,
    ):
        print(
            f"[Task 2: {index}/{len(TASK2_CASES)}] "
            f"{case.name}"
        )

        brief = None
        caught_error: Exception | None = None
        deterministic_repeat: bool | None = None

        try:
            brief = summarize_account(
                case.account_id
            )

            # Invalid-account cases are expected to raise an
            # error before reaching this section.
            if case.expected_error is None:
                repeated_brief = summarize_account(
                    case.account_id
                )

                deterministic_repeat = (
                    brief.model_dump(mode="json")
                    == repeated_brief.model_dump(
                        mode="json"
                    )
                )

        except Exception as error:
            caught_error = error

        try:
            scored_result = score_task2_case(
                case=case,
                brief=brief,
                caught_error=caught_error,
                deterministic_repeat=(
                    deterministic_repeat
                ),
                repository=repository,
            )

            result = normalize_result(
                scored_result=scored_result,
                test_id=case.test_id,
                name=case.name,
                task="Task 2",
                adversarial=case.adversarial,
            )

        except Exception as scoring_error:
            result = create_runtime_failure(
                test_id=case.test_id,
                name=case.name,
                task="Task 2",
                adversarial=case.adversarial,
                error=scoring_error,
            )

        results.append(result)

        print(
            "  Result:",
            "PASS" if result["passed"] else "FAIL",
            "| Quality:",
            result["quality_score"],
        )

    return results


def summarize_results(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate total passes and average quality.
    """

    total = len(results)

    passed = sum(
        1
        for result in results
        if result["passed"]
    )

    failed = total - passed

    average_quality = (
        sum(
            result["quality_score"]
            for result in results
        )
        / total
        if total
        else 0.0
    )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(
            passed / total if total else 0.0,
            4,
        ),
        "average_quality_score": round(
            average_quality,
            4,
        ),
    }


def build_report(
    task1_results: list[dict[str, Any]],
    task2_results: list[dict[str, Any]],
    repository: DataRepository,
) -> dict[str, Any]:
    """
    Build the final JSON-compatible evaluation report.
    """

    all_results = (
        task1_results
        + task2_results
    )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "evaluation_method": (
            "Deterministic rule-based acceptance checks"
        ),
        "prompt_versions": {
            "task_1": TRIAGE_PROMPT_VERSION,
            "task_2": TAM_PROMPT_VERSION,
        },
        "dataset": {
            "tickets": len(repository.tickets),
            "accounts": len(repository.accounts),
        },
        "overall": summarize_results(
            all_results
        ),
        "task_1_summary": summarize_results(
            task1_results
        ),
        "task_2_summary": summarize_results(
            task2_results
        ),
        "results": all_results,
    }


def escape_markdown(value: Any) -> str:
    """
    Prevent values from breaking a Markdown table.
    """

    return (
        str(value)
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def build_markdown_report(
    report: dict[str, Any],
) -> str:
    """
    Convert the evaluation report into a readable
    Markdown table.
    """

    overall = report["overall"]

    lines = [
        "# Evaluation Report",
        "",
        (
            f"Generated: "
            f"{report['generated_at']}"
        ),
        "",
        (
            f"Evaluation method: "
            f"{report['evaluation_method']}"
        ),
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total tests | {overall['total']} |",
        f"| Passed | {overall['passed']} |",
        f"| Failed | {overall['failed']} |",
        (
            f"| Pass rate | "
            f"{overall['pass_rate']:.2%} |"
        ),
        (
            f"| Average quality | "
            f"{overall['average_quality_score']:.2f} |"
        ),
        "",
        "## Test results",
        "",
        (
            "| Test ID | Task | Test name | "
            "Adversarial | Result | Quality |"
        ),
        "|---|---|---|---:|---:|---:|",
    ]

    for result in report["results"]:
        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        lines.append(
            "| "
            + " | ".join(
                [
                    escape_markdown(
                        result["test_id"]
                    ),
                    escape_markdown(
                        result["task"]
                    ),
                    escape_markdown(
                        result["name"]
                    ),
                    (
                        "Yes"
                        if result["adversarial"]
                        else "No"
                    ),
                    status,
                    (
                        f"{result['quality_score']:.2f}"
                    ),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Prompt versions",
            "",
            (
                f"- Task 1: "
                f"`{report['prompt_versions']['task_1']}`"
            ),
            (
                f"- Task 2: "
                f"`{report['prompt_versions']['task_2']}`"
            ),
            "",
        ]
    )

    return "\n".join(lines)


def write_reports(
    report: dict[str, Any],
) -> None:
    """
    Save both required report formats.
    """

    JSON_REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    MARKDOWN_REPORT_PATH.write_text(
        build_markdown_report(report),
        encoding="utf-8",
    )


def main() -> None:
    """
    Run the complete evaluation harness.
    """

    print("Loading validated repository...")
    repository = get_repository()

    print("\nRunning Task 1 evaluations...")
    task1_results = run_task1_evaluations(
        repository
    )

    print("\nRunning Task 2 evaluations...")
    task2_results = run_task2_evaluations(
        repository
    )

    report = build_report(
        task1_results=task1_results,
        task2_results=task2_results,
        repository=repository,
    )

    write_reports(report)

    overall = report["overall"]

    print("\nEvaluation complete")
    print("Total tests:", overall["total"])
    print("Passed:", overall["passed"])
    print("Failed:", overall["failed"])
    print(
        "Average quality:",
        overall["average_quality_score"],
    )
    print("JSON report:", JSON_REPORT_PATH)
    print("Markdown report:", MARKDOWN_REPORT_PATH)


if __name__ == "__main__":
    main()