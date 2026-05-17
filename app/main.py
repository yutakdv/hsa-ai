from fastapi import FastAPI

from app.api.routes import router as api_router

app = FastAPI(
    title="HSA AI",
    version="0.1.0",
    description="HSA AI 파트의 FastAPI 서버",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    # HTTP 상태코드는 항상 200. 성공/실패 분기는 응답 body의 status 필드로 처리 (백엔드 협의 사항)
    # 추후 개발 진행에 따라 status 필드에 세부 상태 코드나 메시지를 추가할 수 있음
    return {"status": "OK"}


app.include_router(api_router, prefix="/api/v1")
