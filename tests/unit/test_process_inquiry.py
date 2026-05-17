"""
process_inquiry orchestrator 단위 테스트.

현재 범위:
- 실제 LLM/RAG/DB 연결 없이 service 결과를 InquiryProcessResult로 집약한다.
- classify_inquiry / decide_auto_reply / generate_rag_draft는 monkeypatch로 대체한다.
"""

import pytest

import app.workflow.process_inquiry as process_module
from schemas.auto_reply import AutoReplyDecision
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry
from schemas.process_result import ProcessStatus


def _make_inquiry(
    message: str,
    context: dict[str, object] | None = None,
) -> CustomerInquiry:
    return CustomerInquiry(
        inquiry_id="inq_process_001",
        channel=Channel.KAKAO,
        message=message,
        context=context,
    )


def test_process_inquiry_aggregates_auto_reply_success(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry(
        "제 주문 언제 도착하나요?",
        context={
            "orderStatus": "배송 중",
            "expectedDeliveryDate": "05월 15일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 1,
        },
    )

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.DELIVERY,
            confidence=0.9,
            reason="배송 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=True,
            filled_answer="배송 중입니다.",
            reason="DB 조회 결과가 명확함",
        )

    def fail_generate_rag_draft(inquiry: CustomerInquiry) -> None:
        pytest.fail("자동응답 가능 시 RAG 초안 생성은 호출하지 않아야 한다.")

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fail_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.SUCCESS
    assert result.error is None
    assert result.data is not None
    assert result.data.inquiry_id == inquiry.inquiry_id
    assert result.data.auto_reply_available is True
    assert result.data.draft_answer == "배송 중입니다."
    assert result.data.needs_admin_review is False
    assert result.data.reason == "DB 조회 결과가 명확함"
    assert result.data.risk_tags == []
    assert result.data.used_sources == [
        "context.orderStatus",
        "context.expectedDeliveryDate",
        "context.trackingNumber",
    ]


def test_process_inquiry_routes_etc_classification_to_needs_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("배송이 늦으면 환불 가능한가요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.ETC,
            confidence=0.8,
            reason="복합 문의",
        )

    def fail_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        pytest.fail("기타 문의는 자동응답 판단으로 넘기지 않아야 한다.")

    def fail_generate_rag_draft(inquiry: CustomerInquiry) -> None:
        pytest.fail("기타 문의는 기본 집약 단계에서 needs_review로 전환한다.")

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fail_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fail_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.NEEDS_REVIEW
    assert result.error is None
    assert result.data is not None
    assert result.data.auto_reply_available is False
    assert result.data.draft_answer is None
    assert result.data.needs_admin_review is True
    assert result.data.reason.startswith("[Complex]")


def test_process_inquiry_routes_auto_reply_false_and_no_rag_to_needs_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("세탁은 어떻게 하나요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.PRODUCT,
            confidence=0.9,
            reason="상품 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="상품 정보 문의는 RAG 초안 대상",
        )

    def fake_generate_rag_draft(inquiry: CustomerInquiry) -> None:
        return None

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.NEEDS_REVIEW
    assert result.error is None
    assert result.data is not None
    assert result.data.auto_reply_available is False
    assert result.data.draft_answer is None
    assert result.data.needs_admin_review is True
    assert result.data.reason.startswith("[No_Context]")
    assert result.data.used_sources == []


def test_process_inquiry_maps_classification_validation_failure_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("배송 상태 알려주세요.")

    def fail_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        raise ValueError("LLM output validation failed")

    monkeypatch.setattr(process_module, "classify_inquiry", fail_classify_inquiry)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.ERROR
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "LLM_PARSE_FAILED"
    assert "검증 실패" in result.error.message


def test_process_inquiry_maps_timeout_to_error(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry("배송 상태 알려주세요.")

    def fail_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(process_module, "classify_inquiry", fail_classify_inquiry)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.ERROR
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "LLM_TIMEOUT"
    assert result.error.message == "LLM 호출 시간 초과"


def test_process_inquiry_maps_rag_external_failure_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("세탁은 어떻게 하나요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.PRODUCT,
            confidence=0.9,
            reason="상품 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="상품 정보 문의는 RAG 초안 대상",
        )

    def fail_generate_rag_draft(inquiry: CustomerInquiry) -> None:
        raise RuntimeError("retriever unavailable")

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fail_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.ERROR
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "EXTERNAL_SYSTEM_ERROR"
    assert "처리 단계 실패" in result.error.message
