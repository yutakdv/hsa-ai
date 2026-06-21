"""분류 정확도 측정용 in-process classify 실행기.

runner.py(HTTP 호출)와 분리된 실행 계층이다.
`category`는 api-contract Phase 0.3 ③에 따라 HTTP 응답에 노출되지 않으므로,
HTTP를 거치지 않고 classify_inquiry service를 직접 호출해 예측 category를 수집한다.

분리 이유: 실행(예측 수집)은 runner 계층, 채점은 grader 계층이라는 기존 분리를 유지한다.
"""

from typing import Any

from app.services.classify_inquiry import classify_inquiry
from schemas.inquiry import CustomerInquiry


def run_classification(tasks: list[dict[str, Any]]) -> dict[str, str]:
    """`expected_category`가 있는 태스크마다 classify_inquiry를 직접 호출한다.

    Returns:
        {task_id: 예측된 category 값(한글 enum value)} dict.
        라벨이 없는 태스크(expected_category 미지정)는 측정 대상에서 제외한다.
    """
    predictions: dict[str, str] = {}
    for task in tasks:
        if not task.get("expected_category"):
            continue
        inquiry = CustomerInquiry.model_validate(task["input"])
        result = classify_inquiry(inquiry)
        predictions[task["task_id"]] = result.category.value
    return predictions
