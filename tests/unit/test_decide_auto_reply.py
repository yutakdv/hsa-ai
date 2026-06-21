"""
decide_auto_reply service 단위 테스트.
"""

import pytest

from app.services.decide_auto_reply import decide_auto_reply
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry
from schemas.process_result import RiskTag


def _in_transit_context() -> dict[str, object]:
    """배송 중(IN_TRANSIT) 하드 사실이 모두 채워진 자동응답 가능 context."""
    return {
        "deliveryStatus": "IN_TRANSIT",
        "carrier": "CJ대한통운",
        "trackingNumber": "1234-5678",
        "currentLocation": "옥천HUB",
    }


def _make_inquiry(
    message: str,
    context: dict[str, object] | None = None,
) -> CustomerInquiry:
    return CustomerInquiry(
        inquiry_id="inq_auto_reply_001",
        channel=Channel.KAKAO,
        message=message,
        context=context,
    )


def _make_classification(
    category: InquiryCategory,
    confidence: float = 0.9,
    reason: str = "테스트용 분류 근거",
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        confidence=confidence,
        reason=reason,
    )


def test_in_transit_delivery_with_complete_context_is_auto_reply_available() -> None:
    inquiry = _make_inquiry("제 주문 어디까지 왔나요?", context=_in_transit_context())
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is True
    assert result.filled_answer == (
        "현재 고객님의 주문은 CJ대한통운를 통해 배송 중이며, 현재 위치는 옥천HUB입니다.\n"
        "송장번호는 1234-5678입니다."
    )
    assert "배송 중" in result.reason


def test_delivery_inquiry_without_context_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry("제 주문 언제 도착하나요?", context=None)
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert result.reason.startswith("[No_Context]")


@pytest.mark.parametrize(
    "delivery_status",
    ["READY_FOR_SHIPMENT", "DELIVERED"],
)
def test_non_in_transit_delivery_status_falls_back_to_rag(delivery_status: str) -> None:
    """배송 중이 아닌 상태(배송 준비/완료)는 즉시 자동응답하지 않고 RAG 초안으로 전환한다."""
    context = _in_transit_context()
    context["deliveryStatus"] = delivery_status
    inquiry = _make_inquiry("제 주문 언제 도착하나요?", context=context)
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "RAG 초안" in result.reason


@pytest.mark.parametrize(
    "sentinel",
    ["NONE", "UNKNOWN", "미발급", "정보없음", "상품정보없음"],
)
def test_sentinel_context_value_blocks_auto_reply(sentinel: str) -> None:
    """백엔드 결측 sentinel 문자열은 빈 값으로 취급해 자동응답을 막는다."""
    context = _in_transit_context()
    context["trackingNumber"] = sentinel
    inquiry = _make_inquiry("제 주문 어디까지 왔나요?", context=context)
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert result.reason.startswith("[No_Context]")
    assert "trackingNumber" in result.reason


def test_refund_exchange_inquiry_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry(
        "사이즈가 안 맞아서 교환하고 싶어요.",
        context=_in_transit_context(),
    )
    classification = _make_classification(InquiryCategory.REFUND_EXCHANGE)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "환불/교환" in result.reason


def test_complex_inquiry_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry(
        "배송이 늦으면 환불 가능한가요?",
        context=_in_transit_context(),
    )
    classification = _make_classification(InquiryCategory.ETC)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert result.reason.startswith("[Complex]")


def test_delivery_inquiry_with_claim_keyword_requires_review() -> None:
    inquiry = _make_inquiry(
        "배송받은 상품이 파손됐어요. 어떻게 처리하나요?",
        context=_in_transit_context(),
    )
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "클레임" in result.reason


def test_refund_exchange_category_sets_risk_tag_refund() -> None:
    inquiry = _make_inquiry(
        "사이즈가 안 맞아서 교환하고 싶어요.",
        context=_in_transit_context(),
    )
    classification = _make_classification(InquiryCategory.REFUND_EXCHANGE)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.risk_tags == [RiskTag.REFUND]


def test_claim_keyword_sets_risk_tag_claim() -> None:
    inquiry = _make_inquiry(
        "배송받은 상품이 파손됐어요. 어떻게 처리하나요?",
        context=_in_transit_context(),
    )
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.risk_tags == [RiskTag.CLAIM]
