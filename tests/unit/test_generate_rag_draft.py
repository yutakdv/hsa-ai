"""
generate_rag_draft 서비스 단위 테스트.

policy_retriever.retrieve_and_generate를 monkeypatch로 대체해
generate_rag_draft 함수 자체의 동작만 검증한다.
반환은 (RagDraftAnswer | None, list[RiskTag]) 튜플이다 (plan.md Phase 2 경로1).
"""

import pytest

import app.services.generate_rag_draft as rag_module
from schemas.inquiry import Channel, CustomerInquiry
from schemas.process_result import RiskTag
from schemas.rag_draft import RagDraftAnswer


def _make_inquiry(
    message: str,
    context: dict[str, object] | None = None,
) -> CustomerInquiry:
    return CustomerInquiry(
        inquiry_id="inq_rag_001",
        channel=Channel.KAKAO,
        message=message,
        context=context,
    )


def _make_rag_answer(
    draft_answer: str = "배송 중입니다.",
    reason: str = "policy.shipping 기준",
    used_sources: list[str] | None = None,
) -> RagDraftAnswer:
    return RagDraftAnswer(
        draft_answer=draft_answer,
        reason=reason,
        used_sources=used_sources or ["policy.shipping"],
    )


def test_returns_none_with_empty_risk_tags_when_no_relevant_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rag_module.policy_retriever, "retrieve_and_generate", lambda q, c: (None, [])
    )

    draft, risk_tags = rag_module.generate_rag_draft(_make_inquiry("세탁 방법이 궁금해요."))

    assert draft is None
    assert risk_tags == []


def test_returns_rag_answer_when_retriever_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _make_rag_answer()
    monkeypatch.setattr(
        rag_module.policy_retriever, "retrieve_and_generate", lambda q, c: (expected, [])
    )

    draft, risk_tags = rag_module.generate_rag_draft(_make_inquiry("배송 상태 알려주세요."))

    assert draft is expected
    assert risk_tags == []


def test_propagates_policy_conflict_risk_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _make_rag_answer()
    monkeypatch.setattr(
        rag_module.policy_retriever,
        "retrieve_and_generate",
        lambda q, c: (expected, [RiskTag.POLICY_CONFLICT]),
    )

    draft, risk_tags = rag_module.generate_rag_draft(_make_inquiry("반품 배송비 누가 내나요?"))

    assert draft is expected
    assert risk_tags == [RiskTag.POLICY_CONFLICT]


def test_passes_message_and_context_to_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_retrieve(query: str, context: object) -> tuple[RagDraftAnswer, list[RiskTag]]:
        captured["query"] = query
        captured["context"] = context
        return _make_rag_answer(), []

    monkeypatch.setattr(rag_module.policy_retriever, "retrieve_and_generate", fake_retrieve)

    inquiry = _make_inquiry(
        "반품 기간이 얼마나 되나요?",
        context={"orderStatus": "배송 완료"},
    )
    rag_module.generate_rag_draft(inquiry)

    assert captured["query"] == inquiry.message
    assert captured["context"] == inquiry.context


def test_used_sources_from_retriever_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_sources = ["context.orderStatus", "policy.exchange-refund"]
    monkeypatch.setattr(
        rag_module.policy_retriever,
        "retrieve_and_generate",
        lambda q, c: (_make_rag_answer(used_sources=expected_sources), []),
    )

    draft, _ = rag_module.generate_rag_draft(_make_inquiry("환불 가능한가요?"))

    assert draft is not None
    assert draft.used_sources == expected_sources
