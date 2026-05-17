"""
문의 처리 workflow orchestrator.

현재 범위:
- 백엔드 DB/RAG 실제 연동 전까지 service 결과를 InquiryProcessResult로 집약한다.
- classify_inquiry -> decide_auto_reply -> generate_rag_draft 순서만 고정한다.
- 실제 LLM/RAG 실패 처리와 usedSources 확정은 후속 구현에서 보강한다.
"""

from pydantic import ValidationError

from app.services.classify_inquiry import classify_inquiry
from app.services.decide_auto_reply import decide_auto_reply
from app.services.generate_rag_draft import generate_rag_draft
from schemas import CustomerInquiry, InquiryProcessResult
from schemas.classification import InquiryCategory
from schemas.process_result import InquiryProcessData, ProcessError, ProcessStatus

_AUTO_REPLY_USED_SOURCES = [
    "context.orderStatus",
    "context.expectedDeliveryDate",
    "context.trackingNumber",
]


def _needs_review_data(
    inquiry: CustomerInquiry,
    reason: str,
) -> InquiryProcessData:
    """관리자 검토가 필요한 기본 data payload를 만든다."""
    return InquiryProcessData(
        inquiry_id=inquiry.inquiry_id,
        auto_reply_available=False,
        draft_answer=None,
        needs_admin_review=True,
        reason=reason,
        risk_tags=[],
        used_sources=[],
    )


def _error_result(code: str, message: str) -> InquiryProcessResult:
    """API v2 error wrapper 형태의 실패 응답을 만든다."""
    return InquiryProcessResult(
        status=ProcessStatus.ERROR,
        data=None,
        error=ProcessError(code=code, message=message),
    )


def _map_exception_to_error(exc: Exception) -> InquiryProcessResult:
    """LLM/RAG/service 실패를 API 계약의 error 응답으로 변환한다."""
    if isinstance(exc, TimeoutError):
        return _error_result(
            code="LLM_TIMEOUT",
            message="LLM 호출 시간 초과",
        )

    if isinstance(exc, (ValidationError, ValueError)):
        return _error_result(
            code="LLM_PARSE_FAILED",
            message=f"LLM 출력 파싱 또는 Pydantic 검증 실패: {exc}",
        )

    return _error_result(
        code="EXTERNAL_SYSTEM_ERROR",
        message=f"외부 시스템 또는 처리 단계 실패: {exc}",
    )


def _process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """고객 문의 처리의 정상 경로를 실행한다."""
    classification = classify_inquiry(inquiry)

    if classification.category == InquiryCategory.ETC:
        return InquiryProcessResult(
            status=ProcessStatus.NEEDS_REVIEW,
            data=_needs_review_data(
                inquiry,
                reason=f"[Complex] {classification.reason}",
            ),
            error=None,
        )

    auto_reply = decide_auto_reply(inquiry, classification)
    if auto_reply.available:
        return InquiryProcessResult(
            status=ProcessStatus.SUCCESS,
            data=InquiryProcessData(
                inquiry_id=inquiry.inquiry_id,
                auto_reply_available=True,
                draft_answer=auto_reply.filled_answer,
                needs_admin_review=False,
                reason=auto_reply.reason,
                risk_tags=[],
                used_sources=_AUTO_REPLY_USED_SOURCES,
            ),
            error=None,
        )

    rag_draft = generate_rag_draft(inquiry)
    if rag_draft is None:
        return InquiryProcessResult(
            status=ProcessStatus.NEEDS_REVIEW,
            data=_needs_review_data(
                inquiry,
                reason="[No_Context] 관련 근거 문서 없음 또는 RAG 초안 생성 미구현",
            ),
            error=None,
        )

    return InquiryProcessResult(
        status=ProcessStatus.SUCCESS,
        data=InquiryProcessData(
            inquiry_id=inquiry.inquiry_id,
            auto_reply_available=False,
            draft_answer=rag_draft.draft_answer,
            needs_admin_review=True,
            reason=rag_draft.reason,
            risk_tags=[],
            used_sources=[],
        ),
        error=None,
    )


def process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """고객 문의를 분류하고 자동응답/RAG 초안 결과를 통합 응답으로 집약한다."""
    try:
        return _process_inquiry(inquiry)
    except Exception as exc:
        return _map_exception_to_error(exc)
