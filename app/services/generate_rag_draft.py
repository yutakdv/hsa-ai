"""
RAG 기반 답변 초안 생성 service.

현재는 실제 LlamaIndex 검색 연결 전 placeholder다.
process_inquiry orchestrator가 RAG 근거 없음 경로를 집약할 수 있도록 None을 반환한다.
"""

from schemas.inquiry import CustomerInquiry
from schemas.rag_draft import RagDraftAnswer


def generate_rag_draft(inquiry: CustomerInquiry) -> RagDraftAnswer | None:
    """정책 문서 근거가 없거나 RAG 미구현 상태이면 None을 반환한다."""
    return None
