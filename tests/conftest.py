import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def minimal_inquiry_payload() -> dict[str, object]:
    return {
        "inquiryId": "inq_test_001",
        "message": "제 주문 언제 오나요?",
    }


@pytest.fixture
def inquiry_with_context_payload() -> dict[str, object]:
    return {
        "inquiryId": "inq_test_002",
        "message": "제 주문 언제 오나요?",
        "channel": "kakao",
        "context": {
            "orderStatus": "배송 중",
            "trackingNumber": "1234-5678",
        },
    }
