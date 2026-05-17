from fastapi import APIRouter

from app.workflow.process_inquiry import process_inquiry
from schemas import CustomerInquiry, InquiryProcessResult

router = APIRouter()


@router.post(
    "/inquiries/process",
    response_model=InquiryProcessResult,
    # BaseHsaModel의 alias_generator=to_camel이 동작하려면 필수
    # 미설정 시 응답이 snake_case로 나와 API 계약 위반
    response_model_by_alias=True,
)
def process(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """
    고객 문의를 처리하는 API 엔드포인트.

    입력: CustomerInquiry 모델 (채널, 고객 ID, 문의 내용 등)
    출력: InquiryProcessResult 모델 (처리 결과, 분류, 위험 태그 등)

    내부적으로 process_inquiry 함수를 호출하여 실제 비즈니스 로직을 수행.
    """
    return process_inquiry(inquiry)
