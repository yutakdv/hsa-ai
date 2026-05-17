"""
문의 유형 분류 service.

도메인 분류 규칙과 출력 schema 선택은 service 계층이 소유한다.
실제 LLM provider 호출 방식은 app.boundaries.llm_client.generate_structured에 위임한다.
"""

from app.boundaries import llm_client
from schemas.classification import ClassificationResult
from schemas.inquiry import CustomerInquiry

_CLASSIFICATION_SYSTEM_PROMPT = """
너의 역할은 고객 문의 유형 분류다.
가능한 category는 다음 네 개뿐이다.
- 배송 문의
- 교환/환불 문의
- 상품 문의
- 기타 문의

규칙:
- 문의 유형만 분류한다.
- 자동응답 가능 여부, 환불 가능 여부, 교환 가능 여부, 배송 예정일은 판단하지 않는다.
- 복합 의도이거나 단일 유형으로 안전하게 분류하기 어려우면 기타 문의로 분류한다.
- 반드시 ClassificationResult schema에 맞는 구조화 결과만 반환한다.
""".strip()


def _build_classification_prompt(inquiry: CustomerInquiry) -> str:
    """CustomerInquiry를 분류 전용 프롬프트로 변환한다."""
    channel = inquiry.channel.value if inquiry.channel is not None else "unknown"
    return "\n".join(
        [
            "아래 고객 문의를 하나의 category로 분류해줘.",
            f"inquiry_id: {inquiry.inquiry_id}",
            f"channel: {channel}",
            f"message: {inquiry.message}",
        ]
    )


def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    """고객 문의를 ClassificationResult로 분류한다."""
    return llm_client.generate_structured(
        prompt=_build_classification_prompt(inquiry),
        output_schema=ClassificationResult,
        system_prompt=_CLASSIFICATION_SYSTEM_PROMPT,
    )
