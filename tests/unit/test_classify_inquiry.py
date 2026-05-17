"""
classify_inquiry service 단위 테스트.

TDD RED 단계:
- 실제 OpenAI 호출 없이 LLM boundary를 fake로 대체한다.
- classify_inquiry는 CustomerInquiry를 받아 ClassificationResult를 반환해야 한다.
- LLM이 스키마에 없는 category를 반환하면 검증 실패로 reject해야 한다.
"""

import pytest
from pydantic import ValidationError

from app.boundaries import llm_client
from app.services.classify_inquiry import classify_inquiry
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry


def _make_inquiry(message: str) -> CustomerInquiry:
    return CustomerInquiry(
        inquiry_id="inq_unit_001",
        message=message,
        channel=Channel.KAKAO,
        context=None,
    )


def _patch_llm_category(
    monkeypatch: pytest.MonkeyPatch,
    category: str,
    confidence: float = 0.9,
    reason: str = "테스트용 분류 근거",
) -> None:
    def fake_generate_structured(
        prompt: str,
        output_schema: type[ClassificationResult],
        **kwargs: object,
    ) -> ClassificationResult:
        assert prompt
        assert output_schema is ClassificationResult
        return output_schema.model_validate(
            {
                "category": category,
                "confidence": confidence,
                "reason": reason,
            }
        )

    monkeypatch.setattr(llm_client, "generate_structured", fake_generate_structured, raising=False)


def test_classifies_delivery_inquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm_category(
        monkeypatch,
        InquiryCategory.DELIVERY.value,
        reason="도착, 배송 키워드가 포함되어 배송 문의로 분류",
    )

    result = classify_inquiry(_make_inquiry("제 주문 언제 도착하나요?"))

    assert result.category == InquiryCategory.DELIVERY
    assert result.confidence == pytest.approx(0.9)
    assert result.reason


def test_classifies_refund_exchange_inquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm_category(
        monkeypatch,
        InquiryCategory.REFUND_EXCHANGE.value,
        reason="교환 키워드가 포함되어 교환/환불 문의로 분류",
    )

    result = classify_inquiry(_make_inquiry("사이즈가 안 맞아서 교환하고 싶어요."))

    assert result.category == InquiryCategory.REFUND_EXCHANGE
    assert result.confidence == pytest.approx(0.9)
    assert result.reason


def test_classifies_product_inquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm_category(
        monkeypatch,
        InquiryCategory.PRODUCT.value,
        reason="사이즈와 재고 키워드가 포함되어 상품 문의로 분류",
    )

    result = classify_inquiry(_make_inquiry("이 상품 M 사이즈 재고 있나요?"))

    assert result.category == InquiryCategory.PRODUCT
    assert result.confidence == pytest.approx(0.9)
    assert result.reason


def test_classifies_etc_inquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm_category(
        monkeypatch,
        InquiryCategory.ETC.value,
        reason="배송과 환불 의도가 함께 있어 기타 문의로 분류",
    )

    result = classify_inquiry(_make_inquiry("배송이 늦으면 환불 가능한가요?"))

    assert result.category == InquiryCategory.ETC
    assert result.confidence == pytest.approx(0.9)
    assert result.reason


def test_rejects_invalid_llm_category(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm_category(
        monkeypatch,
        "배송/환불 문의",
        reason="스키마에 존재하지 않는 잘못된 카테고리",
    )

    with pytest.raises((ValueError, ValidationError)):
        classify_inquiry(_make_inquiry("배송이랑 환불 둘 다 궁금해요."))
