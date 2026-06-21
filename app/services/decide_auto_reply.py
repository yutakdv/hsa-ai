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
from schemas.process_result import RiskTag

# 자동응답(즉시 발송) = "배송 중" 하드 사실만. 예상 도착일/배송 소요일은 정책 지식이라
# RAG 초안으로 처리한다(api-contract-v2.md 0.3 결정). 따라서 템플릿은 백엔드가 제공하는
# 배송 하드 사실(carrier·currentLocation·trackingNumber)만 삽입한다.
_AUTO_REPLY_TEMPLATE = (
    "현재 고객님의 주문은 {carrier}를 통해 배송 중이며, 현재 위치는 {currentLocation}입니다.\n"
    "송장번호는 {trackingNumber}입니다."
)
_REQUIRED_CONTEXT_FIELDS = (
    "deliveryStatus",
    "carrier",
    "trackingNumber",
    "currentLocation",
)

# 즉시 자동응답 발송 트리거 축은 deliveryStatus다(api-contract-v2.md 0.3 ③ 결정).
# orderStatus=SHIPPED가 동시에 와도 트리거로 쓰지 않는다.
_IN_TRANSIT = "IN_TRANSIT"

# 백엔드 deliveryStatus enum(3값) → 한글 표현. AI 측이 관리하며 백엔드 enum에 정렬한다.
_DELIVERY_STATUS_KO = {
    "READY_FOR_SHIPMENT": "배송 준비 중",
    "IN_TRANSIT": "배송 중",
    "DELIVERED": "배송 완료",
}

# 백엔드가 결측 필드를 null이 아니라 sentinel 문자열로 보낸다(InquiryContextService).
# 미처리 시 "송장번호는 NONE입니다" 같은 응답이 나가므로 blank로 취급한다.
_SENTINEL_VALUES = frozenset({"NONE", "UNKNOWN", "미발급", "정보없음", "상품정보없음"})
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
    """context 값이 자동응답 템플릿에 쓰기 어려운 빈 값인지 판단한다.

    None/공백뿐 아니라 백엔드 결측 sentinel 문자열도 빈 값으로 본다.
    """
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped in _SENTINEL_VALUES
    return False


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
        "carrier": str(context["carrier"]),
        "currentLocation": str(context["currentLocation"]),
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
            risk_tags=[RiskTag.REFUND],
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
            risk_tags=[RiskTag.CLAIM],
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
    # 즉시 자동응답은 "배송 중(IN_TRANSIT)" 하드 사실에만 한정한다.
    # 그 외 상태(배송 준비 중/완료)나 "언제 와요?"류 예상 도착일 문의는 RAG 초안으로 전환한다.
    delivery_status = str(context["deliveryStatus"]).strip()
    if delivery_status != _IN_TRANSIT:
        status_ko = _DELIVERY_STATUS_KO.get(delivery_status, delivery_status)
        return AutoReplyDecision(
            available=False,
            reason=(
                f"배송 중 상태가 아니어서(현재: {status_ko}) "
                "즉시 자동응답 불가, RAG 초안으로 전환"
            ),
        )

    filled_answer = _AUTO_REPLY_TEMPLATE.format(**_as_template_context(context))
    return AutoReplyDecision(
        available=True,
        filled_answer=filled_answer,
        reason="배송 중(IN_TRANSIT) 상태와 배송 정보가 명확하여 자동응답 가능",
    )
