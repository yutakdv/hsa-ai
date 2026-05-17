"""
POST /api/v1/inquiries/process 엔드포인트 계약 검증.

이 테스트는 HTTP wrapper와 camelCase 응답 계약만 검증한다.
workflow/service 동작은 unit test에서 별도로 검증하므로 실제 LLM provider를 호출하지 않는다.
"""
import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from schemas import CustomerInquiry, InquiryProcessResult
from schemas.process_result import InquiryProcessData, ProcessStatus


@pytest.fixture(autouse=True)
def fake_process_inquiry(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
        return InquiryProcessResult(
            status=ProcessStatus.SUCCESS,
            data=InquiryProcessData(
                inquiry_id=inquiry.inquiry_id,
                auto_reply_available=False,
                draft_answer="[test] API 계약 검증용 응답입니다.",
                needs_admin_review=True,
                reason="[test] workflow는 endpoint 테스트에서 fake로 대체",
                risk_tags=[],
                used_sources=[],
            ),
            error=None,
        )

    monkeypatch.setattr(routes, "process_inquiry", _fake_process_inquiry)


def test_health_check(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "OK"


def test_process_returns_200(
    client: TestClient,
    minimal_inquiry_payload: dict[str, object],
) -> None:
    res = client.post("/api/v1/inquiries/process", json=minimal_inquiry_payload)
    assert res.status_code == 200


def test_process_response_wrapper_shape(
    client: TestClient,
    minimal_inquiry_payload: dict[str, object],
) -> None:
    """응답이 status / data / error 래퍼 구조를 갖추는지 확인."""
    body = client.post("/api/v1/inquiries/process", json=minimal_inquiry_payload).json()
    assert "status" in body
    assert "data" in body
    assert "error" in body


def test_process_response_camel_case_fields(
    client: TestClient,
    minimal_inquiry_payload: dict[str, object],
) -> None:
    """data 필드의 키가 camelCase인지 확인 (snake_case 유출 방지)."""
    data = client.post("/api/v1/inquiries/process", json=minimal_inquiry_payload).json()["data"]
    assert "inquiryId" in data
    assert "autoReplyAvailable" in data
    assert "needsAdminReview" in data
    assert "usedSources" in data
    assert "riskTags" in data
    # snake_case 키가 유출되지 않아야 함
    assert "inquiry_id" not in data
    assert "auto_reply_available" not in data


def test_process_inquiry_id_echo(
    client: TestClient,
    minimal_inquiry_payload: dict[str, object],
) -> None:
    """응답의 inquiryId가 요청의 inquiryId와 일치하는지 확인."""
    data = client.post("/api/v1/inquiries/process", json=minimal_inquiry_payload).json()["data"]
    assert data["inquiryId"] == minimal_inquiry_payload["inquiryId"]


def test_process_with_context(
    client: TestClient,
    inquiry_with_context_payload: dict[str, object],
) -> None:
    res = client.post("/api/v1/inquiries/process", json=inquiry_with_context_payload)
    assert res.status_code == 200
    assert res.json()["status"] in ("success", "needs_review", "error")


def test_process_missing_required_fields(client: TestClient) -> None:
    """필수 필드 누락 시 422 반환."""
    res = client.post("/api/v1/inquiries/process", json={"message": "문의 내용만 있음"})
    assert res.status_code == 422


def test_process_empty_message(client: TestClient) -> None:
    """빈 message 전송 시 422 반환."""
    res = client.post("/api/v1/inquiries/process", json={"inquiryId": "inq_x", "message": ""})
    assert res.status_code == 422
