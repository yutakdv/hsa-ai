"""
자동응답 가능 여부 판단 service.

현재는 백엔드 연동이 아직 되어 있지 않으므로, inquiry.context에 전달된
임시 context와 classification만으로 자동응답 가능 여부를 판단한다.

백엔드 연동 이후에는 DB 조회 결과를 기반으로 자동응답 가능 여부를 판별하도록
변경할 예정이다. reason 역시 현재의 고정 문구가 아니라 LLM 응답 기반 설명으로
변경할 예정이다.

이 service는 RAG 검색은 수행하지 않는다.
"""

from collections.abc import Mapping

from schemas.auto_reply import AutoReplyDecision
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import CustomerInquiry

_AUTO_REPLY_TEMPLATE = (
    "현재 고객님의 주문은 {orderStatus} 상태이며, 예상 도착일은 {expectedDeliveryDate}입니다.\n"
    "송장번호는 {trackingNumber}입니다."
)
_REQUIRED_CONTEXT_FIELDS = (
    "orderStatus",
    "expectedDeliveryDate",
    "trackingNumber",
    "matchedOrderCount",
)
_POLICY_OR_EXCEPTION_KEYWORDS = (
    "환불",
    "교환",
    "반품",
    "취소",
    "착용",
)
_CLAIM_KEYWORDS = (
    "클레임",
    "하자",
    "파손",
    "불량",
    "피해",
)


def _is_blank(value: object) -> bool:
    """context 값이 자동응답 템플릿에 쓰기 어려운 빈 값인지 판단한다."""
    return value is None or (isinstance(value, str) and not value.strip())


def _missing_context_fields(context: Mapping[str, object] | None) -> list[str]:
    """자동응답에 필요한 camelCase context 필드 중 누락된 필드를 반환한다."""
    if context is None:
        return list(_REQUIRED_CONTEXT_FIELDS)
    return [field for field in _REQUIRED_CONTEXT_FIELDS if _is_blank(context.get(field))]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _as_template_context(context: Mapping[str, object]) -> dict[str, str]:
    """자동응답 템플릿에 삽입할 context 값을 문자열로 변환한다."""
    return {
        "orderStatus": str(context["orderStatus"]),
        "expectedDeliveryDate": str(context["expectedDeliveryDate"]),
        "trackingNumber": str(context["trackingNumber"]),
    }


def decide_auto_reply(
    inquiry: CustomerInquiry,
    classification: ClassificationResult,
) -> AutoReplyDecision:
    """고객 문의가 DB 기반 자동응답 대상인지 판단한다."""
    if classification.category == InquiryCategory.ETC:
        return AutoReplyDecision(
            available=False,
            reason="[Complex] 복합 문의 또는 의도 불명확 문의는 관리자 검토로 전환",
        )

    if classification.category == InquiryCategory.REFUND_EXCHANGE:
        return AutoReplyDecision(
            available=False,
            reason="환불/교환 가능 여부는 정책 해석과 예외 판단이 필요하므로 자동응답 불가",
        )

    if classification.category == InquiryCategory.PRODUCT:
        return AutoReplyDecision(
            available=False,
            reason="상품 정보 문의는 정책/상품 문서 근거가 필요하므로 RAG 초안 생성 대상으로 전환",
        )

    if _contains_any(inquiry.message, _CLAIM_KEYWORDS):
        return AutoReplyDecision(
            available=False,
            reason="상품 하자/파손 등 클레임 또는 고객 피해 가능성이 있어 관리자 검토 필요",
        )

    if _contains_any(inquiry.message, _POLICY_OR_EXCEPTION_KEYWORDS):
        return AutoReplyDecision(
            available=False,
            reason="정책 해석이나 예외 판단이 필요한 표현이 포함되어 자동응답 불가",
        )

    context = inquiry.context
    missing_fields = _missing_context_fields(context)
    if missing_fields:
        return AutoReplyDecision(
            available=False,
            reason=(
                "[No_Context] 자동응답에 필요한 DB 조회 context 부족 "
                f"(누락: {', '.join(missing_fields)})"
            ),
        )

    assert context is not None  # missing_fields가 없으면 context는 존재한다.
    matched_order_count = context["matchedOrderCount"]
    if int(matched_order_count) != 1:
        return AutoReplyDecision(
            available=False,
            reason="동일 고객의 주문이 여러 건이거나 단일 주문으로 특정되지 않아 관리자 검토 필요",
        )

    filled_answer = _AUTO_REPLY_TEMPLATE.format(**_as_template_context(context))
    return AutoReplyDecision(
        available=True,
        filled_answer=filled_answer,
        reason="주문/배송 DB 조회 결과가 단일 주문으로 명확하여 자동응답 가능",
    )
