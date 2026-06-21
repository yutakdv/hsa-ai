"""
schemas/rag_draft.py

RAG 기반 답변 초안 모델.
generate_rag_draft 함수의 반환 타입.

생성 금지 조건 (harness/AGENTS.md 참조):
- 검색 결과가 비어 있거나 relevance threshold 미달인 경우
  RagDraftAnswer를 반환하지 않고 None으로 처리한다.
- 검색 source는 RAG boundary가 계산하고, InquiryProcessResult 레벨에서 집약한다.
"""

from pydantic import Field

from schemas.base import BaseHsaModel


class RagDraftAnswer(BaseHsaModel):
    """
    RAG 기반 답변 초안.

    근거 문서가 없으면 이 모델 자체를 생성하지 않는다.
    근거 출처(usedSources)는 RAG boundary가 계산하고 InquiryProcessResult 레벨에서 집약한다.
    관리자 검토 필요 여부(needsAdminReview)는 InquiryProcessResult 레벨에서 결정한다.
    """

    draft_answer: str = Field(..., min_length=1, description="답변 초안 본문")
    reason: str = Field(..., min_length=1, description="초안 작성 근거 요약")
    used_sources: list[str] = Field(
        default_factory=list,
        description=(
            "답변 생성에 사용한 출처 목록. "
            "process_inquiry가 InquiryProcessData로 집약한다."
        ),
    )
