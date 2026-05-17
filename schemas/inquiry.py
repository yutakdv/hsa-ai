"""
schemas/inquiry.py

백엔드로부터 받는 고객 문의 입력 모델.
api-contract-v2.md "Request" 섹션의 매핑.
"""

from enum import Enum
from typing import Any

from pydantic import Field

from schemas.base import BaseHsaModel


class Channel(str, Enum):
    EMAIL = "email"
    KAKAO = "kakao"
    INSTAGRAM = "instagram"


class CustomerInquiry(BaseHsaModel):
    """
    POST /api/v1/inquiries/process Request body.

    JSON으로 직렬화 시 키는 camelCase로 변환된다:
      inquiry_id -> inquiryId
    """

    inquiry_id: str = Field(..., min_length=1, description="백엔드 문의 고유 ID")
    channel: Channel | None = Field(default=None, description="유입 채널")
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="고객 문의 원문",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "답변 작성에 필요한 운영 데이터 맥락. "
            "키는 camelCase여야 한다 (예: orderStatus, trackingNumber)."
        ),
    )
