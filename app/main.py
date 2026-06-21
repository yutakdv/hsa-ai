from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.routes import router as api_router
from app.boundaries import document_loader


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    # build_index는 파일 I/O + OpenAI Embedding API 동기 호출을 포함한다.
    # run_in_threadpool로 이벤트 루프 블로킹을 방지한다.
    # ECS 배포 시 healthCheck.startPeriod를 인덱스 빌드 예상 시간 이상으로 설정해야 한다.
    await run_in_threadpool(document_loader.build_index)
    yield


app = FastAPI(
    title="HSA AI",
    version="0.1.0",
    description="HSA AI 파트의 FastAPI 서버",
    lifespan=lifespan,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    # HTTP 상태코드는 항상 200. 성공/실패 분기는 응답 body의 status 필드로 처리 (백엔드 협의 사항)
    # 추후 개발 진행에 따라 status 필드에 세부 상태 코드나 메시지를 추가할 수 있음
    return {"status": "AI server is healthy"}


# 엔드포인트 경로는 백엔드(AiInquiryClient) 호출 spec에 맞춘다: /api/inquiries/process
app.include_router(api_router, prefix="/api")
