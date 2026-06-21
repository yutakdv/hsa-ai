from app.boundaries import policy_retriever
from schemas.inquiry import CustomerInquiry
from schemas.process_result import RiskTag
from schemas.rag_draft import RagDraftAnswer


def generate_rag_draft(
    inquiry: CustomerInquiry,
) -> tuple[RagDraftAnswer | None, list[RiskTag]]:
    """정책 문서 기반 답변 초안 생성.

    반환: (답변 초안 | None, 위험 태그). 근거 없으면 (None, ...).
    정책 충돌 감지 시 위험 태그에 policy_conflict가 포함된다.
    """
    return policy_retriever.retrieve_and_generate(inquiry.message, inquiry.context)
