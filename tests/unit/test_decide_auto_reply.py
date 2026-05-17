"""
decide_auto_reply service 단위 테스트.
"""

from app.services.decide_auto_reply import decide_auto_reply
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry


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


def test_delivery_inquiry_with_complete_single_order_context_is_auto_reply_available() -> None:
    inquiry = _make_inquiry(
        "제 주문 언제 도착하나요?",
        context={
            "orderStatus": "배송 중",
            "expectedDeliveryDate": "05월 15일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 1,
        },
    )
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is True
    assert result.filled_answer == (
        "현재 고객님의 주문은 배송 중 상태이며, 예상 도착일은 05월 15일입니다.\n"
        "송장번호는 1234-5678입니다."
    )
    assert "DB 조회 결과" in result.reason


def test_delivery_inquiry_without_context_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry("제 주문 언제 도착하나요?", context=None)
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert result.reason.startswith("[No_Context]")


def test_delivery_inquiry_with_multiple_matched_orders_requires_review() -> None:
    inquiry = _make_inquiry(
        "제 주문 언제 도착하나요?",
        context={
            "orderStatus": "배송 중",
            "expectedDeliveryDate": "05월 15일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 2,
        },
    )
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "주문이 여러 건" in result.reason


def test_refund_exchange_inquiry_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry(
        "사이즈가 안 맞아서 교환하고 싶어요.",
        context={
            "orderStatus": "배송 완료",
            "expectedDeliveryDate": "05월 12일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 1,
        },
    )
    classification = _make_classification(InquiryCategory.REFUND_EXCHANGE)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "환불/교환" in result.reason


def test_complex_inquiry_is_not_auto_reply_available() -> None:
    inquiry = _make_inquiry(
        "배송이 늦으면 환불 가능한가요?",
        context={
            "orderStatus": "배송 중",
            "expectedDeliveryDate": "05월 15일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 1,
        },
    )
    classification = _make_classification(InquiryCategory.ETC)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert result.reason.startswith("[Complex]")


def test_delivery_inquiry_with_claim_keyword_requires_review() -> None:
    inquiry = _make_inquiry(
        "배송받은 상품이 파손됐어요. 어떻게 처리하나요?",
        context={
            "orderStatus": "배송 완료",
            "expectedDeliveryDate": "05월 12일",
            "trackingNumber": "1234-5678",
            "matchedOrderCount": 1,
        },
    )
    classification = _make_classification(InquiryCategory.DELIVERY)

    result = decide_auto_reply(inquiry, classification)

    assert result.available is False
    assert result.filled_answer is None
    assert "클레임" in result.reason
