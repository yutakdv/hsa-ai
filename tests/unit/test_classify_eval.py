"""분류 단위 eval(classify_runner + grader 분류 정확도) 단위 테스트.

실제 LLM을 호출하지 않는다(키 불필요). classify_inquiry를 monkeypatch해
① grader의 분류 정확도 채점 로직 ② classify_runner의 예측 수집 로직만 검증한다.
"""

import sys
from pathlib import Path

import pytest

# evals/ 모듈은 bare import(from runner import ...)를 쓰므로 경로에 추가한다.
_EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"
if str(_EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVALS_DIR))

import classify_runner  # noqa: E402
import grader  # noqa: E402
from runner import TaskResult  # noqa: E402

from schemas.classification import ClassificationResult, InquiryCategory  # noqa: E402


def _task_result(task_id: str, expected_category: str) -> TaskResult:
    """expected_category를 가진 최소 TaskResult를 만든다.

    분류 채점은 r.task_id와 r.task["expected_category"]만 보므로 나머지는 더미.
    """
    return TaskResult(
        task_id=task_id,
        description="",
        input={"inquiryId": task_id, "message": "msg"},
        expected={},
        actual={"status": "success", "data": {}, "error": None},
        latency=0.1,
        runner_error=None,
        task={"task_id": task_id, "expected_category": expected_category},
    )


def _metric(report: grader.GradeReport, name: str) -> grader.MetricResult:
    return next(m for m in report.metrics if m.name == name)


def test_classification_accuracy_pass_at_threshold() -> None:
    # 5개 중 4개 정답 → 0.8, 임계값 0.80 → 통과
    results = [_task_result(f"T{i}", "배송 문의") for i in range(5)]
    predictions = {
        "T0": "배송 문의", "T1": "배송 문의", "T2": "배송 문의",
        "T3": "배송 문의", "T4": "상품 문의",  # T4 오답
    }
    report = grader.grade_results(results, predictions)
    metric = _metric(report, "분류 정확도")
    assert metric.score == pytest.approx(0.8)
    assert metric.passed is True


def test_classification_accuracy_fail_below_threshold() -> None:
    # 5개 중 3개 정답 → 0.6 → 미달 (게이트 차단)
    results = [_task_result(f"T{i}", "배송 문의") for i in range(5)]
    predictions = {
        "T0": "배송 문의", "T1": "배송 문의", "T2": "배송 문의",
        "T3": "상품 문의", "T4": "상품 문의",
    }
    report = grader.grade_results(results, predictions)
    metric = _metric(report, "분류 정확도")
    assert metric.score == pytest.approx(0.6)
    assert metric.passed is False
    assert report.threshold_passed is False


def test_classification_blocks_when_predictions_missing() -> None:
    # predictions 미제공 → 측정 불가로 간주, 블로킹(passed=False)
    results = [_task_result("T0", "배송 문의")]
    report = grader.grade_results(results)  # predictions 인자 없음
    metric = _metric(report, "분류 정확도")
    assert metric.score is None
    assert metric.passed is False


def test_run_classification_collects_only_labeled(monkeypatch: pytest.MonkeyPatch) -> None:
    # classify_inquiry를 mock해 실제 LLM 없이 예측 수집 로직 검증.
    def fake_classify(inquiry: object) -> ClassificationResult:
        cat = (
            InquiryCategory.REFUND_EXCHANGE
            if "반품" in inquiry.message  # type: ignore[attr-defined]
            else InquiryCategory.DELIVERY
        )
        return ClassificationResult(category=cat, confidence=0.9, reason="test")

    monkeypatch.setattr(classify_runner, "classify_inquiry", fake_classify)

    tasks = [
        {
            "task_id": "A",
            "expected_category": "배송 문의",
            "input": {"inquiryId": "a", "message": "배송 언제 와요"},
        },
        {
            "task_id": "B",
            "expected_category": "교환/환불 문의",
            "input": {"inquiryId": "b", "message": "반품하고 싶어요"},
        },
        {
            # expected_category 없음 → 측정 대상에서 제외돼야 한다
            "task_id": "C",
            "input": {"inquiryId": "c", "message": "기타 문의"},
        },
    ]
    predictions = classify_runner.run_classification(tasks)
    assert predictions == {"A": "배송 문의", "B": "교환/환불 문의"}
