"""
schemas/inquiry.py

백엔드로부터 받는 고객 문의 입력 모델.
api-contract-v2.md "Request" 섹션의 매핑.
"""

from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from schemas.base import BaseHsaModel


class Channel(str, Enum):
    # 백엔드 ChannelType(KAKAO/WEB/MAIL)에 정렬. (hsa-server domain/channel/ChannelType.java)
    # 백엔드가 .name() 대문자로 보내므로 _normalize_channel가 소문자로 변환해 매칭한다.
    KAKAO = "kakao"
    WEB = "web"
    MAIL = "mail"


class CustomerInquiry(BaseHsaModel):
    """
    POST /api/inquiries/process Request body.

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

    @field_validator("channel", mode="before")
    @classmethod
    def _normalize_channel(cls, value: Any) -> Any:
        """백엔드가 대문자 enum("KAKAO")을 보내도 파싱되도록 대소문자를 무시한다.

        알 수 없는 값은 정규화하지 않고 그대로 흘려 Channel enum 검증에서 거부된다.
        """
        if isinstance(value, str):
            return value.lower()
        return value
