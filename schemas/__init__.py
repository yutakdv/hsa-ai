"""
schemas/

HSA AI 파트의 Pydantic 모델 모음.
모든 모델은 BaseHsaModel을 상속하며, JSON 직렬화 시 camelCase로 자동 변환된다.

"""

from schemas.auto_reply import AutoReplyDecision
from schemas.base import BaseHsaModel
from schemas.classification import ClassificationResult, InquiryCategory
from schemas.inquiry import Channel, CustomerInquiry
from schemas.process_result import (
    InquiryProcessData,
    InquiryProcessResult,
    ProcessError,
    ProcessStatus,
    RiskTag,
)
from schemas.rag_draft import RagDraftAnswer

__all__ = [
    "BaseHsaModel",
    "Channel",
    "CustomerInquiry",
    "InquiryCategory",
    "ClassificationResult",
    "AutoReplyDecision",
    "RagDraftAnswer",
    "ProcessStatus",
    "ProcessError",
    "RiskTag",
    "InquiryProcessData",
    "InquiryProcessResult",
]
