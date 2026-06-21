"""
CustomerInquiry 입력 모델 단위 테스트.

백엔드 inquiry 도메인 spec(2026-06-17)은 channel을 대문자 enum("KAKAO")으로 보낸다.
대소문자 무시 파싱을 보장하고, 알 수 없는 값은 여전히 거부하는지 검증한다.
"""

import pytest
from pydantic import ValidationError

from schemas.inquiry import Channel, CustomerInquiry


@pytest.mark.parametrize("raw", ["KAKAO", "Kakao", "kakao", "kAkAo"])
def test_channel_accepts_any_case(raw: str) -> None:
    inquiry = CustomerInquiry(inquiry_id="inq_001", message="안녕하세요", channel=raw)
    assert inquiry.channel is Channel.KAKAO


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("WEB", Channel.WEB),
        ("Mail", Channel.MAIL),
    ],
)
def test_channel_other_enums_case_insensitive(raw: str, expected: Channel) -> None:
    inquiry = CustomerInquiry(inquiry_id="inq_001", message="안녕하세요", channel=raw)
    assert inquiry.channel is expected


def test_channel_none_allowed() -> None:
    inquiry = CustomerInquiry(inquiry_id="inq_001", message="안녕하세요")
    assert inquiry.channel is None


@pytest.mark.parametrize("raw", ["sms", "SMS", "telegram"])
def test_channel_unknown_value_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        CustomerInquiry(inquiry_id="inq_001", message="안녕하세요", channel=raw)


def test_channel_serializes_to_lowercase_value_in_camel_case() -> None:
    """직렬화 시 channel은 소문자 enum value를 유지하고 키는 camelCase."""
    inquiry = CustomerInquiry(inquiry_id="inq_001", message="안녕하세요", channel="KAKAO")
    dumped = inquiry.model_dump(by_alias=True)
    assert dumped["inquiryId"] == "inq_001"
    assert dumped["channel"] == "kakao"
