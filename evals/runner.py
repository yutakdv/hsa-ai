"""HTTP 호출과 응답 수집을 담당하는 runner.

각 task를 API에 POST하고, 응답 본문과 레이턴시를 TaskResult로 반환한다.
네트워크 오류나 JSON 파싱 실패도 TaskResult로 wrapping해 grader로 전달한다.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import requests

API_ENDPOINT = "http://localhost:8000/api/inquiries/process"
REQUEST_TIMEOUT = 120  # seconds — RAG 케이스 p95 latency 기준 2배 마진 확보
MAX_RETRIES = 1  # timeout 등 일시적 실패 시 1회 재시도


@dataclass
class TaskResult:
    task_id: str
    description: str
    input: dict[str, Any]
    expected: dict[str, Any]
    actual: dict[str, Any] | None  # 호출 실패 시 None
    latency: float  # seconds
    runner_error: str | None = field(default=None)  # 네트워크·파싱 오류 메시지
    # tasks.json 원본 (forbidden_sources 등 접근용)
    task: dict[str, Any] = field(default_factory=dict)


def run_tasks(tasks: list[dict[str, Any]]) -> list[TaskResult]:
    """tasks.json 케이스 목록을 순서대로 API에 호출하고 결과를 반환한다."""
    results: list[TaskResult] = []

    for task in tasks:
        task_id = task.get("task_id", "N/A")
        actual: dict[str, Any] | None = None
        runner_error: str | None = None
        latency = 0.0

        start = time.perf_counter()
        for _ in range(MAX_RETRIES + 1):
            try:
                response = requests.post(
                    API_ENDPOINT,
                    json=task["input"],
                    timeout=REQUEST_TIMEOUT,
                )
                latency = round(time.perf_counter() - start, 2)
                actual = response.json()
                runner_error = None
                break
            except Exception as exc:
                latency = round(time.perf_counter() - start, 2)
                runner_error = str(exc)

        results.append(
            TaskResult(
                task_id=task_id,
                description=task.get("description", ""),
                input=task["input"],
                expected=task["expected"],
                actual=actual,
                latency=latency,
                runner_error=runner_error,
                task=task,
            )
        )

    return results
