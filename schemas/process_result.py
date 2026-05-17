"""
schemas/process_result.py

백엔드로 반환되는 통합 응답 모델.
docs/api-contract-v2.md "Response" 섹션과 1:1 대응.

process_inquiry 함수가 classify_inquiry, decide_auto_reply, generate_rag_draft의
결과를 받아 이 모델로 집약해 반환한다. 내부 처리 모델(ClassificationResult,
AutoReplyDecision, RagDraftAnswer)은 외부에 노출하지 않는다.
"""

from enum import Enum

from pydantic import Field

from schemas.base import BaseHsaModel


class ProcessStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"


class RiskTag(str, Enum):
    REFUND = "refund"
    CLAIM = "claim"
    POLICY_CONFLICT = "policy_conflict"


class ProcessError(BaseHsaModel):
    """오류 응답의 error 필드. status='error'일 때만 채워진다."""

    code: str = Field(
        ...,
        description="오류 코드. 예: LLM_TIMEOUT | LLM_PARSE_FAILED | EXTERNAL_SYSTEM_ERROR",
    )
    message: str = Field(..., description="오류 상세 메시지")


class InquiryProcessData(BaseHsaModel):
    """
    process 응답의 data 필드.

    docs/api-contract-v2.md Response data 구조와 1:1 대응.
    내부 처리 결과(AutoReplyDecision, RagDraftAnswer)는
    process_inquiry orchestrator가 아래 필드로 집약한다.

    JSON 직렬화 시 모든 키는 camelCase로 변환된다:
      inquiry_id           -> inquiryId
      auto_reply_available -> autoReplyAvailable
      draft_answer         -> draftAnswer
      needs_admin_review   -> needsAdminReview
      risk_tags            -> riskTags
      used_sources         -> usedSources
    """

    inquiry_id: str = Field(..., min_length=1, description="원본 문의 ID")
    auto_reply_available: bool = Field(
        ...,
        description=(
            "자동응답 즉시 발송 가능 여부. "
            "True이면 백엔드가 draft_answer를 고객에게 즉시 발송한다. "
            "source: AutoReplyDecision.available"
        ),
    )
    draft_answer: str | None = Field(
        default=None,
        description=(
            "답변 내용. "
            "자동응답 시: AutoReplyDecision.filled_answer | "
            "RAG 초안 시: RagDraftAnswer.draft_answer | "
            "근거 없음 시: None"
        ),
    )
    needs_admin_review: bool = Field(..., description="관리자 검토 필요 여부")
    reason: str = Field(
        ...,
        min_length=1,
        description=(
            "판단 이유. process_inquiry가 집약: "
            "자동응답 시 AutoReplyDecision.reason | "
            "RAG 초안 시 RagDraftAnswer.reason | "
            "검토 필요 시 [No_Context] 또는 [Complex] 태그 포함 문자열"
        ),
    )
    risk_tags: list[RiskTag] = Field(default_factory=list, description="위험 태그 목록")
    used_sources: list[str] = Field(
        default_factory=list,
        description=(
            "출처 목록. prefix로 구분: "
            "context.{필드명} | policy.{파일명} | faq.{문서ID}"
        ),
    )


class InquiryProcessResult(BaseHsaModel):
    """
    백엔드로 반환되는 최종 응답 래퍼.

    docs/api-contract-v2.md의 공통 래퍼 구조를 따른다:
      { status, data, error }
    """

    status: ProcessStatus
    data: InquiryProcessData | None = None
    error: ProcessError | None = None
