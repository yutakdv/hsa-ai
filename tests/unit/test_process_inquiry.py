"""
process_inquiry orchestrator 단위 테스트.

현재 범위:
- 실제 LLM/RAG/DB 연결 없이 service 결과를 InquiryProcessResult로 집약한다.
- classify_inquiry / decide_auto_reply / generate_rag_draft는 monkeypatch로 대체한다.
"""

import pytest

import app.workflow.process_inquiry as process_module
from app.boundaries.llm_client import STRICT_OUTPUT_FORMAT
from schemas.auto_reply import AutoReplyDecision
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry
from schemas.process_result import ProcessStatus, RiskTag
from schemas.rag_draft import RagDraftAnswer


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
        "제 주문 어디까지 왔나요?",
        context={
            "deliveryStatus": "IN_TRANSIT",
            "carrier": "CJ대한통운",
            "trackingNumber": "1234-5678",
            "currentLocation": "옥천HUB",
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
        "context.deliveryStatus",
        "context.carrier",
        "context.trackingNumber",
        "context.currentLocation",
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

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer | None, list[RiskTag]]:
        return None, []

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
    assert "[No_Context]" in result.data.reason
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


def test_process_inquiry_aggregates_rag_draft_success(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry("반품 가능 기간이 얼마나 되나요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.REFUND_EXCHANGE,
            confidence=0.9,
            reason="교환/환불 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="환불/교환은 정책 해석 필요",
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer, list[RiskTag]]:
        return (
            RagDraftAnswer(
                draft_answer="수령일로부터 7일 이내 반품 가능합니다.",
                reason="policy.exchange-refund 문서 기준",
                used_sources=["policy.exchange-refund"],
            ),
            [],
        )

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.SUCCESS
    assert result.data is not None
    assert result.data.auto_reply_available is False
    assert result.data.draft_answer == "수령일로부터 7일 이내 반품 가능합니다."
    assert result.data.needs_admin_review is True
    assert result.data.used_sources == ["policy.exchange-refund"]


def test_risk_tags_propagated_to_result(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry("사이즈가 안 맞아서 교환하고 싶어요.")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.REFUND_EXCHANGE,
            confidence=0.9,
            reason="교환/환불 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="환불/교환은 정책 해석 필요",
            risk_tags=[RiskTag.REFUND],
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer, list[RiskTag]]:
        return (
            RagDraftAnswer(
                draft_answer="수령일로부터 7일 이내 반품 가능합니다.",
                reason="policy.exchange-refund 문서 기준",
                used_sources=["policy.exchange-refund"],
            ),
            [],
        )

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.data is not None
    assert result.data.risk_tags == [RiskTag.REFUND]


def test_claim_risk_forces_needs_admin_review(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry("배송받은 상품이 파손됐어요.")

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
            available=False,
            reason="클레임 관련 관리자 검토 필요",
            risk_tags=[RiskTag.CLAIM],
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer, list[RiskTag]]:
        return (
            RagDraftAnswer(
                draft_answer="교환/환불 절차 안내입니다.",
                reason="policy.exchange-refund 문서 기준",
                used_sources=["policy.exchange-refund"],
            ),
            [],
        )

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.data is not None
    assert result.data.needs_admin_review is True
    assert result.data.risk_tags == [RiskTag.CLAIM]


def test_policy_conflict_risk_tag_merged_from_rag_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAG 경로가 policy_conflict를 반환하면 riskTags에 포함되고 needsAdminReview=True.

    status는 success 가능 (api-contract-v2.md 관리자 검토 테이블).
    """
    inquiry = _make_inquiry("반품 배송비는 누가 부담하나요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.REFUND_EXCHANGE,
            confidence=0.9,
            reason="교환/환불 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="환불/교환은 정책 해석 필요",
            risk_tags=[RiskTag.REFUND],
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer, list[RiskTag]]:
        return (
            RagDraftAnswer(
                draft_answer="배송비 부담 주체는 문서마다 다르게 안내됩니다.",
                reason="policy.shipping / policy.exchange-refund 충돌",
                used_sources=["policy.shipping"],
            ),
            [RiskTag.POLICY_CONFLICT],
        )

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.SUCCESS
    assert result.data is not None
    assert result.data.needs_admin_review is True
    # 자동응답 단계 REFUND + RAG 경로 POLICY_CONFLICT 병합, 순서 유지
    assert result.data.risk_tags == [RiskTag.REFUND, RiskTag.POLICY_CONFLICT]


def test_auto_reply_reason_preserved_in_rag_path(monkeypatch: pytest.MonkeyPatch) -> None:
    inquiry = _make_inquiry("반품 가능 기간이 얼마나 되나요?")

    def fake_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        return ClassificationResult(
            category=InquiryCategory.REFUND_EXCHANGE,
            confidence=0.9,
            reason="교환/환불 문의",
        )

    def fake_decide_auto_reply(
        inquiry: CustomerInquiry,
        classification: ClassificationResult,
    ) -> AutoReplyDecision:
        return AutoReplyDecision(
            available=False,
            reason="자동응답 불가 이유A",
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer, list[RiskTag]]:
        return (
            RagDraftAnswer(
                draft_answer="7일 이내 반품 가능합니다.",
                reason="RAG 근거 이유B",
                used_sources=["policy.exchange-refund"],
            ),
            [],
        )

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.data is not None
    assert result.data.reason == "자동응답 불가 이유A / RAG 근거 이유B"


def test_auto_reply_reason_preserved_in_no_context_path(
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
            reason="자동응답 불가 이유A",
        )

    def fake_generate_rag_draft(
        inquiry: CustomerInquiry,
    ) -> tuple[RagDraftAnswer | None, list[RiskTag]]:
        return None, []

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.data is not None
    assert result.data.reason.startswith("자동응답 불가 이유A / [No_Context]")


def test_orchestrator_retries_once_on_llm_parse_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("배송 상태 알려주세요.")
    call_count = {"n": 0}

    def flaky_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("1차 parse 실패")
        return ClassificationResult(
            category=InquiryCategory.ETC,
            confidence=0.8,
            reason="복합 문의",
        )

    monkeypatch.setattr(process_module, "classify_inquiry", flaky_classify_inquiry)

    result = process_module.process_inquiry(inquiry)

    assert call_count["n"] == 2
    assert result.status == ProcessStatus.NEEDS_REVIEW


def test_orchestrator_returns_error_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inquiry = _make_inquiry("배송 상태 알려주세요.")

    def always_fail_classify(inquiry: CustomerInquiry) -> ClassificationResult:
        raise ValueError("반복 parse 실패")

    monkeypatch.setattr(process_module, "classify_inquiry", always_fail_classify)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.ERROR
    assert result.error is not None
    assert result.error.code == "LLM_PARSE_FAILED"


def test_orchestrator_enables_strict_format_on_second_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AGENTS.md: 1차 재시도는 동일 프롬프트, 2차 재시도부터 형식 강제 지시."""
    inquiry = _make_inquiry("배송 상태 알려주세요.")
    observed: list[bool] = []

    def flaky_classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
        observed.append(STRICT_OUTPUT_FORMAT.get())
        if len(observed) < 3:
            raise ValueError(f"{len(observed)}차 parse 실패")
        return ClassificationResult(
            category=InquiryCategory.ETC,
            confidence=0.8,
            reason="복합 문의",
        )

    monkeypatch.setattr(process_module, "classify_inquiry", flaky_classify_inquiry)

    process_module.process_inquiry(inquiry)

    assert observed == [False, False, True]
    assert STRICT_OUTPUT_FORMAT.get() is False
