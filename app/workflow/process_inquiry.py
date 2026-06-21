"""
문의 처리 workflow orchestrator.

현재 범위:
- 백엔드 DB/RAG 실제 연동 전까지 service 결과를 InquiryProcessResult로 집약한다.
- classify_inquiry -> decide_auto_reply -> generate_rag_draft 순서만 고정한다.
"""

import os

import httpx
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.boundaries.llm_client import STRICT_OUTPUT_FORMAT
from app.services.classify_inquiry import classify_inquiry
from app.services.decide_auto_reply import decide_auto_reply
from app.services.generate_rag_draft import generate_rag_draft
from schemas import CustomerInquiry, InquiryProcessResult
from schemas.classification import InquiryCategory
from schemas.process_result import InquiryProcessData, ProcessError, ProcessStatus

MAX_ORCHESTRATOR_RETRIES = int(os.getenv("MAX_ORCHESTRATOR_RETRIES", "2"))

_AUTO_REPLY_USED_SOURCES = [
    "context.deliveryStatus",
    "context.carrier",
    "context.trackingNumber",
    "context.currentLocation",
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
    # httpx.TimeoutException: pydantic_ai가 provider 호출 시 발생하는 실제 타임아웃.
    # Python 내장 TimeoutError와 상속 관계가 없으므로 별도로 명시한다.
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return _error_result(
            code="LLM_TIMEOUT",
            message="LLM 호출 시간 초과",
        )

    # UnexpectedModelBehavior: pydantic_ai가 structured output 검증 재시도를 소진한 뒤 raise.
    if isinstance(exc, (ValidationError, ValueError, UnexpectedModelBehavior)):
        return _error_result(
            code="LLM_PARSE_FAILED",
            message="LLM 출력 파싱 또는 Pydantic 검증 실패",
        )

    return _error_result(
        code="EXTERNAL_SYSTEM_ERROR",
        message="외부 시스템 또는 처리 단계 실패",
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
        ctx = inquiry.context or {}
        used_sources = [s for s in _AUTO_REPLY_USED_SOURCES if s.removeprefix("context.") in ctx]
        return InquiryProcessResult(
            status=ProcessStatus.SUCCESS,
            data=InquiryProcessData(
                inquiry_id=inquiry.inquiry_id,
                auto_reply_available=True,
                draft_answer=auto_reply.filled_answer,
                needs_admin_review=False,
                reason=auto_reply.reason,
                risk_tags=[],
                used_sources=used_sources,
            ),
            error=None,
        )

    rag_draft, rag_risk_tags = generate_rag_draft(inquiry)
    # 자동응답 단계 위험 태그 + RAG 경로 충돌 태그(policy_conflict) 병합, 순서 유지 중복 제거
    risk_tags = list(dict.fromkeys(auto_reply.risk_tags + rag_risk_tags))
    needs_admin_review = True  # RAG 초안은 항상 관리자 검토. risk_tags 존재 시 더욱이 필요

    if rag_draft is None:
        return InquiryProcessResult(
            status=ProcessStatus.NEEDS_REVIEW,
            data=_needs_review_data(
                inquiry,
                reason=(
                    f"{auto_reply.reason} / "
                    f"[No_Context] 관련 근거 문서 없음 (검색어: {inquiry.message[:50]})"
                ),
            ).model_copy(update={"risk_tags": risk_tags}),
            error=None,
        )

    return InquiryProcessResult(
        status=ProcessStatus.SUCCESS,
        data=InquiryProcessData(
            inquiry_id=inquiry.inquiry_id,
            auto_reply_available=False,
            draft_answer=rag_draft.draft_answer,
            needs_admin_review=needs_admin_review,
            reason=f"{auto_reply.reason} / {rag_draft.reason}",
            risk_tags=risk_tags,
            used_sources=rag_draft.used_sources,
        ),
        error=None,
    )


def process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """고객 문의를 분류하고 자동응답/RAG 초안 결과를 통합 응답으로 집약한다.

    parse 실패(ValidationError, ValueError, UnexpectedModelBehavior)는
    AGENTS.md 재시도 정책에 따라 최대 MAX_ORCHESTRATOR_RETRIES회 재시도한다.
    timeout 등 즉시 실패 예외는 재시도 없이 반환한다.
    """
    last_result: InquiryProcessResult | None = None
    for attempt in range(MAX_ORCHESTRATOR_RETRIES + 1):
        # AGENTS.md: 1차 재시도는 동일 프롬프트, 2차 재시도부터 형식 강제 지시.
        token = STRICT_OUTPUT_FORMAT.set(attempt > 1)
        try:
            return _process_inquiry(inquiry)
        except (ValidationError, ValueError, UnexpectedModelBehavior) as exc:
            last_result = _map_exception_to_error(exc)
        except Exception as exc:
            return _map_exception_to_error(exc)
        finally:
            STRICT_OUTPUT_FORMAT.reset(token)
    return last_result  # type: ignore[return-value]
