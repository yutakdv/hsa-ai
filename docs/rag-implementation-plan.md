# RAG 구현 계획

> 문서 상태: archived baseline. 아래 상세 코드는 초기 구현 당시 기록이다.
> 구현 상태: 기본 RAG와 LLM reranker 도입 완료. 최신 검색 품질 설정과 담당자 인계 기준은
> `rag-quality-handoff.md`, `workflow-handoff.md`, `quality-handoff.md`를 따른다.

상태: decision
작성일: 2026-05-18
참조: architecture.md, api-contract-v2.md, framework-decision.md, policy-rag-strategy.md

---

## 목적

`generate_rag_draft()`는 현재 항상 `None`을 반환하는 stub 상태다.
자동응답 불가 판단 이후 정책 문서 기반 초안 생성 경로가 없어,
모든 자동응답 불가 문의가 `[No_Context] … RAG 초안 생성 미구현`으로 `needs_review` 처리된다.

이 문서는 LlamaIndex를 사용해 `app/docs/policies/`의 Markdown 정책 문서를
벡터 인덱스로 로드하고, 유사도 검색 → 답변 초안 생성까지 연결하는 구현 계획을 정의한다.

---

## 전체 판별 흐름

```
                ┌─────────────────────────────┐
                │  백엔드 (AI 범위 밖)          │
                │  문의 수집 · 저장             │
                │  채널 / 고객 정보 / 접수 시각  │
                └──────────────┬──────────────┘
                               │
                               │  POST /api/inquiries/process
                               │  { inquiryId, message }
                               ▼
                ┌─────────────────────────────────────────────────────┐
                │  AI (FastAPI)                                        │
                │                                                      │
                │  [1] classify_inquiry  ← Pydantic AI (llm_client.generate_structured) │
                │       │                                              │
                │       ├─ 기타 문의 ──────────────────────────────┐   │
                │       │                                          │   │
                │       └─ 배송 / 교환·환불 / 상품                  │   │
                │               │                                  │   │
                │               ▼                                  │   │
                │  [2] rds_reader.lookup_order_context()           │   │
                │      ← classify 이후 무조건 실행, 읽기 전용        │   │
                │       ├─ 조회 결과 있음 → inquiry.context 구성    │   │
                │       └─ 조회 결과 없음 → inquiry.context = None  │   │
                │               │                                  │   │
                │               ▼                                  │   │
                │  [3] decide_auto_reply (DB 조회로 응답 가능?)      │   │
                │       ├─ YES: DELIVERY + context 충분             │   │
                │       │   (orderStatus, expectedDeliveryDate,    │   │
                │       │    trackingNumber, matchedOrderCount==1) │   │
                │       │   → autoReplyAvailable: true             │   │
                │       │                                          │   │
                │       └─ NO: REFUND_EXCHANGE / PRODUCT /         │   │
                │              context 없음                         │   │
                │               │                                  │   │
                │               ▼                                  │   │
                │  [4] generate_rag_draft  ←──────────────────────┘   │
                │      LlamaIndex 검색 → Pydantic AI 답변 합성         │
                │       ├─ 근거 있음 → RAG 초안 (needsAdminReview: true)│
                │       └─ 근거 없음 → needs_review [No_Context]        │
                │                                                      │
                └──────────────────────────┬──────────────────────────┘
                                           │  HTTP 응답 (JSON)
                                           ▼
                ┌─────────────────────────────┐
                │  백엔드 (AI 범위 밖)          │
                │  autoReplyAvailable: true   │
                │    → 고객에게 답변 발송       │
                │  autoReplyAvailable: false  │
                │    → 관리자 검토 큐 등록      │
                │  status: needs_review       │
                │    → 관리자 직접 답변 작성    │
                │  로그 기록                   │
                └─────────────────────────────┘
```

---

## 역할 분리

`framework-decision.md` 기준.

| 도구 | 이번 구현에서의 역할 |
|---|---|
| LlamaIndex | 정책 문서 로딩, SentenceSplitter chunking, 벡터 인덱싱, 유사도 검색, source 후보 추출 |
| Pydantic AI (`llm_client.generate_structured`) | 검색된 근거 + inquiry.context 기반 `RagDraftAnswer` 생성 |
| Pydantic v2 | 입출력 스키마 검증, camelCase 변환 |
| VectorDB | 보류 — 문서 수 증가 시 후속 검토 |

---

## 인덱스 저장 전략

`storage/` 폴더를 git에 포함해 Docker 이미지에 바로 반영한다.

**이유**: ECR → ECS 배포 구조에서 `storage/`를 git에서 제외하면
컨테이너 시작마다 OpenAI Embedding API를 새로 호출하게 된다.
PoC 규모(정책 문서 4개)에서 벡터 파일 크기는 수백 KB 수준으로 부담 없음.

동작 방식:
- `storage/` 폴더가 있으면 → 디스크에서 로드 (OpenAI Embedding API 호출 없음)
- `storage/` 폴더가 없으면 → 문서 임베딩 후 `storage/`에 저장

정책 문서 변경 시 워크플로우:
```
1. app/docs/policies/ 문서 수정
2. storage/ 폴더 삭제
3. 로컬에서 서버 1회 실행 → storage/ 재생성
4. storage/ + 변경된 정책 문서 함께 커밋
5. ECR 빌드 → ECS 배포
```

---

## Swagger UI 접근 방법

FastAPI는 Swagger UI를 자동 제공한다. 서버 기동 후 브라우저에서 접근한다.

| URL | 용도 |
|---|---|
| `http://localhost:8000/docs` | Swagger UI — 직접 요청 송신 가능, 개발 중 주요 확인 도구 |
| `http://localhost:8000/redoc` | ReDoc — 읽기 전용 API 문서 |
| `http://localhost:8000/openapi.json` | OpenAPI JSON 스키마 원본 |

Swagger UI에서 RAG 기능 테스트하는 방법:

1. `uvicorn app.main:app --reload` 로 서버 기동
2. 브라우저에서 `http://localhost:8000/docs` 접속
3. `POST /api/inquiries/process` 클릭 → "Try it out" 클릭
4. Request body 입력 후 "Execute":

```json
{
  "inquiryId": "test-001",
  "message": "반품 가능 기간이 얼마나 되나요?"
}
```

5. Response body에서 `status`, `data.draftAnswer`, `data.usedSources` 확인

`app/api/routes.py`에 `response_model_by_alias=True`가 설정되어 있어
Swagger UI Schema 탭에서도 camelCase 필드 이름으로 표시된다.

---

## 백엔드 ↔ AI 응답 전송 흐름

AI는 HTTP 동기 응답 방식으로 백엔드에 결과를 반환한다. 별도 콜백이나 웹훅 없음.

```
백엔드 서버
  │
  │  POST /api/inquiries/process
  │  Content-Type: application/json
  │  Body: { "inquiryId": "...", "message": "..." }
  │        (context 없음 — AI가 RDS에서 직접 조회)
  ▼
AI FastAPI 서버 (app/api/routes.py → app/workflow/process_inquiry.py)
  │
  │  [1] classify_inquiry            ← Pydantic AI
  │  [2] rds_reader.lookup_order_context() — classify 이후 무조건 실행
  │  [3] decide_auto_reply
  │  [4] generate_rag_draft          ← LlamaIndex 검색 + Pydantic AI (필요 시)
  ▼
  HTTP 200 OK
  Content-Type: application/json
  Body: {
    "status": "success" | "needs_review" | "error",
    "data": {
      "inquiryId": "...",
      "autoReplyAvailable": true | false,
      "draftAnswer": "..." | null,   ← AI가 생성만 함. 발송은 백엔드 담당
      "needsAdminReview": true | false,
      "reason": "...",
      "riskTags": [],
      "usedSources": ["policy.exchange-refund", ...]
    },
    "error": null
  }
  │
  ▼
백엔드 서버  (이후 처리는 AI 범위 밖)
  ├─ autoReplyAvailable: true  → 고객 채널로 draftAnswer 즉시 발송
  ├─ autoReplyAvailable: false → 관리자 검토 큐에 draftAnswer 등록
  └─ status: needs_review      → 관리자가 직접 답변 작성
```

코드 경로:
```
POST /api/inquiries/process
  → app/api/routes.py: process()
  → app/workflow/process_inquiry.py: process_inquiry()
  → InquiryProcessResult (schemas/)
  → FastAPI가 camelCase JSON으로 직렬화 (BaseHsaModel alias_generator)
  → HTTP 응답
```

---

## 파일 변경 목록

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `pyproject.toml` | 수정 | `llama-index-embeddings-openai` 의존성 추가 |
| `.env` | 수정 | `RAG_RELEVANCE_THRESHOLD`, `RAG_STORAGE_DIR` 항목 추가 |
| `app/boundaries/document_loader.py` | 신규 | 정책 문서 로드 + chunking + 디스크 저장/로드 |
| `app/boundaries/policy_retriever.py` | 신규 | LlamaIndex 검색 + Pydantic AI 답변 합성 + source 추출 |
| `app/services/generate_rag_draft.py` | 수정 | stub → `policy_retriever` boundary만 호출, 반환 타입 변경 |
| `app/workflow/process_inquiry.py` | 수정 | tuple unpacking으로 `used_sources` 실제 값 채우기 |
| `app/main.py` | 수정 | FastAPI lifespan으로 앱 시작 시 인덱스 빌드/로드 |
| `tests/unit/test_process_inquiry.py` | 수정 | RAG 성공 케이스 테스트 추가 |
| `tests/conftest.py` | 수정 | `HSA_TEST_MODE=true` 환경변수로 테스트 시 API 호출 방지 |
| `scripts/check_index.py` | 신규 (개발용) | Step 3 인덱스 빌드 확인 스크립트 |
| `scripts/check_retriever.py` | 신규 (개발용) | Step 4 검색 + 응답 생성 확인 스크립트 |

boundary 파일명 근거: `architecture.md` 폴더 구조에 `policy_retriever.py`, `document_loader.py`가 명시되어 있으므로 그대로 따른다.

---

## 구현 진행 체크리스트

완료된 항목은 `- [x]`로 표시한다.

### Step 1 — 의존성
- [ ] `pyproject.toml`에 `llama-index-embeddings-openai>=0.3.0` 추가
- [ ] `pip install -e .` 후 import 검증 통과

### Step 2 — 환경 변수
- [ ] `.env`에 `RAG_RELEVANCE_THRESHOLD=0.4` 추가
- [ ] `.env`에 `RAG_STORAGE_DIR=./storage` 추가
- [ ] `.env`에 `RDS_READ_URL=` 추가
- [ ] 로컬 `.env` 파일에 위 값 복사 후 적용

### Step 3 — `app/boundaries/document_loader.py`
- [ ] 파일 신규 생성
- [ ] `build_index()` 구현 (`storage/` 있으면 로드, 없으면 임베딩 후 저장)
- [ ] `get_index()` 구현
- [ ] `HSA_TEST_MODE=true` guard 포함 확인
- [ ] `scripts/check_index.py` 실행 → 노드 수 > 0, `storage/` 파일 생성 확인

### Step 4 — `app/boundaries/policy_retriever.py`
- [ ] 파일 신규 생성
- [ ] `RetrievalResult` NamedTuple 정의
- [ ] `retrieve_and_generate()` 구현
- [ ] `_node_to_source_id()` 구현 (file_name → `policy.{stem}`)
- [ ] `_build_prompt()` 구현 (`inquiry.context` 포함)
- [ ] `scripts/check_retriever.py` 실행 → 관련 문의 hit, 무관 문의 None 확인
- [ ] 응답 품질 확인 (한국어, 추측 없음, `used_sources` 정확)

### Step 5 — `app/services/generate_rag_draft.py`
- [ ] 반환 타입 `tuple[RagDraftAnswer, list[str]] | None` 으로 변경
- [ ] `policy_retriever.retrieve_and_generate()` 호출로 교체 (LLM 직접 호출 없음)
- [ ] Python 스크립트로 tuple 반환 타입 확인

### Step 6 — `app/workflow/process_inquiry.py` (RAG 경로)
- [ ] `rag_result` tuple unpacking 적용
- [ ] `used_sources=rag_sources` 실제 값 채우기
- [ ] Python 스크립트로 전체 흐름 검증 (success / needs_review 케이스)

### Step 7 — `app/main.py` lifespan
- [ ] `lifespan` 함수 추가
- [ ] `document_loader.build_index()` lifespan 내 호출
- [ ] 서버 기동 확인 (`uvicorn app.main:app --reload`)
- [ ] Swagger UI (`http://localhost:8000/docs`) 접속 확인
- [ ] curl 3케이스 통과 (RAG / 자동응답 / needs_review)

### Step 8 — `tests/conftest.py`
- [ ] 최상단에 `os.environ.setdefault("HSA_TEST_MODE", "true")` 추가
- [ ] `pytest tests/ -x --tb=short -q` 전체 통과 확인

### Step 9 — `tests/unit/test_process_inquiry.py`
- [ ] `test_process_inquiry_aggregates_rag_draft_success` 테스트 추가
- [ ] `pytest tests/unit/test_process_inquiry.py -v` 통과 확인

### storage/ 빌드 & 커밋
- [ ] 로컬에서 서버 1회 실행해 `storage/` 폴더 생성
- [ ] `storage/` + 정책 문서 함께 git 커밋

### RDS 접근 프레임워크 (stub)
- [ ] `app/boundaries/rds_reader.py` stub 파일 생성
- [ ] `process_inquiry.py`에 RDS 조회 삽입 (classify_inquiry 이후, decide_auto_reply 이전)
- [ ] stub 상태에서 기존 테스트 전체 통과 확인

---

## 구현 상세

### Step 1 — `pyproject.toml` 의존성 추가

```toml
"llama-index-embeddings-openai>=0.3.0",
```

추가 이유: LlamaIndex 0.10+ 모듈형 아키텍처에서 OpenAI 임베딩은 별도 패키지.
`text-embedding-3-small` 사용을 위해 필수.

**구현 검증**

```bash
pip install -e .
python -c "from llama_index.embeddings.openai import OpenAIEmbedding; print('OK')"
```

기대 출력: `OK` / 실패 시: `pyproject.toml` 의존성 재확인

---

### Step 2 — `.env` 수정

```env
# RAG 유사도 임계값 (0.0~1.0, 기본 0.4)
RAG_RELEVANCE_THRESHOLD=0.4

# 인덱스 디스크 저장 경로 (기본 ./storage)
RAG_STORAGE_DIR=./storage
```

---

### Step 3 — `app/boundaries/document_loader.py`

역할: 정책 문서 로드 → chunking → 디스크 저장/로드. `policy_retriever`에 인덱스를 제공하는 유일한 책임.

```python
import os
from pathlib import Path

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

POLICIES_DIR = Path(__file__).parent.parent / "docs" / "policies"
STORAGE_DIR = Path(os.getenv("RAG_STORAGE_DIR", "./storage"))

_index: VectorStoreIndex | None = None


def build_index() -> None:
    """
    앱 시작 시 1회 호출.
    storage/ 폴더가 있으면 로드, 없으면 임베딩 후 저장.
    """
    global _index
    if os.getenv("HSA_TEST_MODE") == "true":
        return  # 테스트 환경에서 OpenAI API 호출 방지

    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = None  # LlamaIndex 내부 LLM 사용 안 함 — Pydantic AI만 사용

    if STORAGE_DIR.exists() and any(STORAGE_DIR.iterdir()):
        storage_context = StorageContext.from_defaults(persist_dir=str(STORAGE_DIR))
        _index = load_index_from_storage(storage_context)
    else:
        docs = SimpleDirectoryReader(str(POLICIES_DIR)).load_data()
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
        _index = VectorStoreIndex.from_documents(docs, transformations=[splitter])
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _index.storage_context.persist(persist_dir=str(STORAGE_DIR))


def get_index() -> VectorStoreIndex:
    if _index is None:
        raise RuntimeError("Document index not initialized. Call build_index() first.")
    return _index
```

설계 포인트:
- `storage/` 있으면 OpenAI Embedding API 호출 없이 로드 → 서버 재시작 비용 없음
- `HSA_TEST_MODE=true`: 테스트에서 `build_index()` skip
- `Settings.llm = None`: 실수로 QueryEngine 호출 시 LlamaIndex 내부 LLM 호출 방지
- `SentenceSplitter(chunk_size=512, chunk_overlap=50)`: 절 단위 분할, 섹션 경계 넘어서도 의미 단위 유지

**구현 검증** — `scripts/check_index.py`

```python
import os
os.environ["HSA_TEST_MODE"] = "false"
from app.boundaries.document_loader import build_index, get_index
build_index()
index = get_index()
node_count = len(list(index.docstore.docs.values()))
print(f"노드 수: {node_count}")
assert node_count > 0
print("storage/ 파일:", sorted(os.listdir("storage")))
print("✓ document_loader OK")
```

```bash
python scripts/check_index.py
```

기대 출력:
```
노드 수: 12
storage/ 파일: ['default__vector_store.json', 'docstore.json', ...]
✓ document_loader OK
```

---

### Step 4 — `app/boundaries/policy_retriever.py`

역할: 인덱스 검색 → threshold 필터 → LLM reranker → Pydantic AI 답변 합성 → source 추출.
`generate_rag_draft` service의 유일한 외부 의존성.

`inquiry.context`를 프롬프트에 포함하는 이유 (`policy-rag-strategy.md`):
"백엔드 context에 없는 주문, 배송, 고객 상태를 추측하지 않는다"
→ context가 있으면 프롬프트에 포함해 AI가 추측하지 않도록 한다.

```python
import os
from pathlib import Path
from typing import Any, NamedTuple

from app.boundaries import document_loader
from app.boundaries.llm_client import generate_structured
from schemas.rag_draft import RagDraftAnswer

RELEVANCE_THRESHOLD = float(os.getenv("RAG_RELEVANCE_THRESHOLD", "0.4"))


class RetrievalResult(NamedTuple):
    draft_answer: str
    reason: str
    used_sources: list[str]  # ["context.orderStatus", "policy.shipping", ...]


def retrieve_and_generate(
    query: str,
    inquiry_context: dict[str, Any] | None,
) -> RetrievalResult | None:
    """
    정책 문서 검색 후 Pydantic AI로 답변 합성.
    threshold 미달 시 None 반환 → process_inquiry가 needs_review 처리.
    """
    index = document_loader.get_index()
    nodes = index.as_retriever(similarity_top_k=3).retrieve(query)
    relevant = [n for n in nodes if (n.score or 0.0) >= RELEVANCE_THRESHOLD]
    if not relevant:
        return None

    policy_sources = list(
        dict.fromkeys(_node_to_source_id(n) for n in relevant)  # 중복 제거, 순서 유지
    )
    context_sources = (
        [f"context.{k}" for k in inquiry_context.keys()] if inquiry_context else []
    )
    used_sources = context_sources + policy_sources

    context_text = "\n\n---\n\n".join(n.get_content() for n in relevant)
    rag_answer = _generate_answer(query, context_text, inquiry_context)

    return RetrievalResult(
        draft_answer=rag_answer.draft_answer,
        reason=rag_answer.reason,
        used_sources=used_sources,
    )


def _node_to_source_id(node) -> str:
    """file_name 메타데이터 → policy.{stem} 변환 (api-contract-v2.md 접두사 규칙)."""
    stem = Path(node.metadata.get("file_name", "unknown")).stem
    return f"policy.{stem}"


def _generate_answer(
    query: str,
    policy_context: str,
    inquiry_context: dict[str, Any] | None,
) -> RagDraftAnswer:
    return generate_structured(
        _build_prompt(query, policy_context, inquiry_context), RagDraftAnswer
    )


def _build_prompt(
    query: str,
    policy_context: str,
    inquiry_context: dict[str, Any] | None,
) -> str:
    ctx_str = (
        "\n".join(f"- {k}: {v}" for k, v in inquiry_context.items())
        if inquiry_context
        else "(없음)"
    )
    return f"""다음 정책 문서와 운영 데이터를 바탕으로 고객 문의에 대한 답변 초안을 작성하세요.

[고객 문의]
{query}

[백엔드 운영 데이터 (context)]
{ctx_str}

[정책 문서]
{policy_context}

Return JSON only. All keys must be in camelCase.
답변은 한국어로 작성합니다.
정책 문서와 운영 데이터에 명시된 내용만 사용하고, 없는 내용은 추측하지 않습니다."""
```

`RetrievalResult`는 Pydantic 스키마가 아닌 `NamedTuple`. `used_sources`를 service → workflow로 전달하기 위한 내부 전달 타입. `RagDraftAnswer` 스키마 수정 없음.

**구현 검증** — `scripts/check_retriever.py` (가장 중요: 검색 결과와 응답 품질 직접 확인)

```python
import os
os.environ["HSA_TEST_MODE"] = "false"
from app.boundaries.document_loader import build_index
from app.boundaries import policy_retriever

build_index()

CASES = [
    ("반품 기간이 얼마나 되나요?",   None, True,  "교환/환불"),
    ("배송비는 얼마인가요?",         None, True,  "배송"),
    ("제품 사이즈 교환 가능한가요?",  None, True,  "상품"),
    ("오늘 비트코인 시세 알려줘",    None, False, "무관한 문의"),
]

print("=" * 60)
for query, ctx, expect_hit, label in CASES:
    result = policy_retriever.retrieve_and_generate(query, ctx)
    hit = result is not None
    ok = "✓" if hit == expect_hit else "✗ FAIL"
    if hit:
        print(f"{ok}  [{label}]")
        print(f"   used_sources : {result.used_sources}")
        print(f"   draft(80자)  : {result.draft_answer[:80]}")
        print(f"   reason       : {result.reason}")
    else:
        print(f"{ok}  [{label}] → None (no context)")
    print("-" * 60)
```

```bash
python scripts/check_retriever.py
```

응답 품질 체크포인트:
- `draft_answer`가 한국어로 작성됐는가
- `used_sources`가 실제 관련 정책 문서를 가리키는가 (예: `policy.exchange-refund`)
- 정책에 없는 내용을 추측해서 답변하지 않는가
- 무관한 문의("비트코인")가 `None`으로 처리되는가

관련 문의인데 `None`이 반환되면 threshold 조정:
```bash
RAG_RELEVANCE_THRESHOLD=0.3 python scripts/check_retriever.py
```

---

### Step 5 — `app/services/generate_rag_draft.py` 수정

`architecture.md` 제약: LlamaIndex 검색만 허용, LLM 직접 호출 금지.
→ `llm_client` import 없음. `policy_retriever` boundary만 호출.

반환 타입 변경: `RagDraftAnswer | None` → `tuple[RagDraftAnswer, list[str]] | None`

변경 이유: `rag_draft.py` 주석에 "usedSources는 InquiryProcessResult 레벨에서 관리한다"고 명시됨.
`RagDraftAnswer` 스키마를 수정하지 않으면서 `used_sources`를 workflow로 전달하려면 tuple이 불가피.

기존 테스트 영향: fake/fail 함수가 모두 `None`을 반환하거나 예외를 발생시키므로 기존 테스트 그대로 통과.
RAG 성공 케이스(tuple 반환) 테스트만 새로 추가 필요.

```python
from app.boundaries import policy_retriever
from schemas.inquiry import CustomerInquiry
from schemas.rag_draft import RagDraftAnswer


def generate_rag_draft(
    inquiry: CustomerInquiry,
) -> tuple[RagDraftAnswer, list[str]] | None:
    """정책 문서 기반 답변 초안 생성. 근거 없으면 None 반환."""
    result = policy_retriever.retrieve_and_generate(inquiry.message, inquiry.context)
    if result is None:
        return None
    return RagDraftAnswer(
        draft_answer=result.draft_answer,
        reason=result.reason,
    ), result.used_sources
```

**구현 검증**

```python
import os
os.environ["HSA_TEST_MODE"] = "false"
from app.boundaries.document_loader import build_index
build_index()

from schemas.inquiry import CustomerInquiry
from app.services.generate_rag_draft import generate_rag_draft

inquiry = CustomerInquiry(inquiry_id="t001", message="반품 가능 기간이 얼마나 되나요?", context=None)
result = generate_rag_draft(inquiry)

assert isinstance(result, tuple), f"tuple이어야 함, 실제: {type(result)}"
draft, sources = result
print(f"✓ 반환 타입 tuple 확인")
print(f"  draft_answer : {draft.draft_answer[:80]}")
print(f"  used_sources : {sources}")
```

---

### Step 6 — `app/workflow/process_inquiry.py` 수정

RAG 경로(현재 line 101~124)만 변경. 다른 경로 무수정.

```python
# Before
rag_draft = generate_rag_draft(inquiry)
if rag_draft is None:
    ...
return InquiryProcessResult(..., used_sources=[])  # 항상 빈 배열

# After
rag_result = generate_rag_draft(inquiry)
if rag_result is None:
    return InquiryProcessResult(
        status=ProcessStatus.NEEDS_REVIEW,
        data=_needs_review_data(
            inquiry,
            reason=f"[No_Context] 관련 근거 문서 없음 (검색어: {inquiry.message[:50]})",
        ),
        error=None,
    )

rag_draft, rag_sources = rag_result
return InquiryProcessResult(
    status=ProcessStatus.SUCCESS,
    data=InquiryProcessData(
        inquiry_id=inquiry.inquiry_id,
        auto_reply_available=False,
        draft_answer=rag_draft.draft_answer,
        needs_admin_review=True,
        reason=rag_draft.reason,
        risk_tags=[],
        used_sources=rag_sources,  # 실제 source 채움
    ),
    error=None,
)
```

**구현 검증** — 서버 없이 직접 호출

```python
import os
os.environ["HSA_TEST_MODE"] = "false"
from app.boundaries.document_loader import build_index
build_index()

from schemas.inquiry import CustomerInquiry
from app.workflow.process_inquiry import process_inquiry

CASES = [
    ("반품 가능 기간이 얼마나 되나요?", None, "success",      False, "policy."),
    ("오늘 날씨 어때요?",              None, "needs_review", False, None),
]

for msg, ctx, exp_status, exp_auto, src_prefix in CASES:
    inq = CustomerInquiry(inquiry_id="t", message=msg, context=ctx)
    r = process_inquiry(inq)
    assert r.status.value == exp_status, f"[{msg[:20]}] status 불일치: {r.status}"
    assert r.data.auto_reply_available == exp_auto
    if src_prefix:
        assert any(s.startswith(src_prefix) for s in r.data.used_sources), \
            f"used_sources에 {src_prefix}* 없음: {r.data.used_sources}"
    print(f"✓ [{msg[:25]}] status={r.status.value}, sources={r.data.used_sources}")
```

---

### Step 7 — `app/main.py` lifespan 추가

```python
from contextlib import asynccontextmanager
from app.boundaries import document_loader

@asynccontextmanager
async def lifespan(app: FastAPI):
    document_loader.build_index()
    yield

app = FastAPI(title="HSA AI", version="0.1.0", description="...", lifespan=lifespan)
```

**구현 검증** — 서버 기동 후 curl 또는 Swagger UI (`http://localhost:8000/docs`)

```bash
# 교환/환불 문의 (RAG 경로)
curl -s -X POST http://localhost:8000/api/inquiries/process \
  -H "Content-Type: application/json" \
  -d '{"inquiryId":"t001","message":"반품 가능 기간이 얼마나 되나요?"}' | python -m json.tool

# 배송 문의 (자동응답 경로 — context 포함)
curl -s -X POST http://localhost:8000/api/inquiries/process \
  -H "Content-Type: application/json" \
  -d '{
    "inquiryId":"t002",
    "message":"제 주문 언제 오나요?",
    "context":{
      "orderStatus":"배송 중",
      "expectedDeliveryDate":"2026-05-21",
      "trackingNumber":"1234-5678",
      "matchedOrderCount":1
    }
  }' | python -m json.tool

# 무관한 문의 (needs_review)
curl -s -X POST http://localhost:8000/api/inquiries/process \
  -H "Content-Type: application/json" \
  -d '{"inquiryId":"t003","message":"오늘 날씨 어때요?"}' | python -m json.tool
```

기대값:

| 케이스 | status | autoReplyAvailable | usedSources |
|---|---|---|---|
| 교환/환불 문의 | success | false | ["policy.exchange-refund"] |
| 배송 context 있음 | success | true | ["context.*", "policy.shipping"] |
| 무관한 문의 | needs_review | false | [] |

---

### Step 8 — 테스트 환경 설정

`document_loader.build_index()`의 `HSA_TEST_MODE` guard를 활성화한다.

`tests/conftest.py` 최상단에 추가:

```python
import os
os.environ.setdefault("HSA_TEST_MODE", "true")
```

**구현 검증**

```bash
pytest tests/ -x --tb=short -q
```

기대값: 모든 기존 테스트 PASSED, `build_index()`가 OpenAI API 호출 없이 skip됨

---

### Step 9 — `tests/unit/test_process_inquiry.py` 수정

RAG 성공 케이스 테스트 추가:

```python
def test_process_inquiry_aggregates_rag_draft_success(monkeypatch):
    inquiry = _make_inquiry("반품 가능 기간이 얼마나 되나요?")

    def fake_classify_inquiry(inquiry):
        return ClassificationResult(
            category=InquiryCategory.REFUND_EXCHANGE,
            confidence=0.9,
            reason="교환/환불 문의",
        )

    def fake_decide_auto_reply(inquiry, classification):
        return AutoReplyDecision(
            available=False,
            reason="환불/교환은 정책 해석 필요",
        )

    def fake_generate_rag_draft(inquiry):
        from schemas.rag_draft import RagDraftAnswer
        return RagDraftAnswer(
            draft_answer="수령일로부터 7일 이내 반품 가능합니다.",
            reason="policy.exchange-refund 문서 기준",
        ), ["policy.exchange-refund"]

    monkeypatch.setattr(process_module, "classify_inquiry", fake_classify_inquiry)
    monkeypatch.setattr(process_module, "decide_auto_reply", fake_decide_auto_reply)
    monkeypatch.setattr(process_module, "generate_rag_draft", fake_generate_rag_draft)

    result = process_module.process_inquiry(inquiry)

    assert result.status == ProcessStatus.SUCCESS
    assert result.data is not None
    assert result.data.auto_reply_available is False
    assert result.data.draft_answer == "수령일로부터 7일 이내 반품 가능합니다."
    assert result.data.needs_admin_review is True
    assert result.data.used_sources == ["policy.exchange-refund"]
```

**구현 검증**

```bash
pytest tests/unit/test_process_inquiry.py -v
```

기대값: `test_process_inquiry_aggregates_rag_draft_success PASSED`

---

## 데이터 흐름 요약

```
CustomerInquiry { inquiryId, message } (백엔드 JSON)
  │
  ├─ [1] classify_inquiry() ──── Pydantic AI → 배송 / 교환·환불 / 상품 / 기타
  │         └─ 기타 → needs_review [Complex]
  │
  ├─ [2] rds_reader.lookup_order_context(inquiry_id)   ← classify 이후 무조건 실행
  │         ├─ 조회 결과 있음 → inquiry.context 구성
  │         └─ 조회 결과 없음 → inquiry.context = None (stub 단계)
  │
  ├─ [3] decide_auto_reply() ─── inquiry.context(RDS 결과) 확인
  │         └─ DELIVERY + context 충분 → SUCCESS (autoReplyAvailable: true)
  │                                      발송은 백엔드 담당
  │
  └─ [4] generate_rag_draft()
           └─ policy_retriever.retrieve_and_generate(message, context)
                ├─ document_loader.get_index()
                │     └─ storage/ 있으면 로드, 없으면 임베딩 후 저장
                ├─ LlamaIndex 유사도 검색 (text-embedding-3-small)
                ├─ threshold 필터 (RAG_RELEVANCE_THRESHOLD, 기본 0.4)
                ├─ [없음] → None → needs_review [No_Context]
                └─ [있음]
                     ├─ used_sources: context 출처 + policy 출처 (중복 제거)
                     ├─ llm_client.generate_structured(RagDraftAnswer)  ← Pydantic AI
                     └─ (RagDraftAnswer, used_sources)
                          → SUCCESS (autoReplyAvailable: false, needsAdminReview: true)
                          관리자 검토 후 발송 여부 결정은 백엔드 담당
```

---

## 검증 체크리스트

| 단계 | 명령 | 확인 내용 |
|---|---|---|
| 의존성 설치 | `pip install -e .` | `llama-index-embeddings-openai` 포함 확인 |
| 초기 빌드 | `uvicorn app.main:app --reload` | `storage/` 폴더 생성 + 빌드 로그 확인 |
| 재시작 | 서버 재시작 | `storage/` 존재 → 로드만 (API 호출 없음) |
| Swagger UI | `http://localhost:8000/docs` | 브라우저에서 직접 요청 송신 및 응답 확인 |
| API 테스트 1 | context 있는 배송 문의 | `autoReplyAvailable: true`, `usedSources: ["context.*"]` |
| API 테스트 2 | context 없는 교환 문의 | `autoReplyAvailable: false`, `usedSources: ["policy.exchange-refund"]` |
| API 테스트 3 | 정책 무관 문의 | `status: needs_review`, `reason: "[No_Context] ..."` |
| 단위 테스트 | `pytest tests/unit/test_process_inquiry.py` | 기존 + RAG 성공 케이스 통과 |
| 정책 변경 시 | `rm -rf storage/ && uvicorn ...` | 재빌드 후 `storage/` 커밋 |
| ECR 배포 후 | `docker run ... ls storage/` | 이미지 내 `storage/` 포함 확인 |

---

## RDS 읽기 전용 접근 프레임워크 (stub)

### 아키텍처 변경 사항

현재 `api-contract-v2.md`에는 "AI는 백엔드 DB를 직접 조회하지 않는다"고 명시되어 있다.
그러나 실제 구현 방향은 AI가 백엔드 RDS(PostgreSQL)에 **읽기 전용**으로 직접 접근하는 것으로 결정됐다.

변경 전 흐름:
```
백엔드 → inquiry.context에 DB 조회 결과를 담아 AI에 전달
AI → context 값만 확인
```

변경 후 흐름:
```
백엔드 → inquiry_id + message만 전달
AI → RDS 직접 조회 (읽기 전용) → context 구성
    ├─ 조회 결과 있음 → decide_auto_reply (자동응답 판단)
    └─ 조회 결과 없음 → RAG 경로
```

> `api-contract-v2.md`의 "AI는 백엔드 DB를 직접 조회하지 않는다" 항목은
> 이 결정에 맞게 추후 수정이 필요하다.

---

### 새 파일: `app/boundaries/rds_reader.py` (stub)

역할: RDS에서 inquiry_id 기반 주문/배송 정보 조회. 현재는 stub으로 `None`을 반환한다.
실제 연결은 DB 스키마 및 RDS 접근 권한 확정 후 구현한다.

```python
"""
읽기 전용 RDS(PostgreSQL) 클라이언트.
현재 stub 상태 — DB 스키마 및 접근 권한 확정 후 구현.

실제 구현 시 교체할 항목:
- RDS_READ_URL 환경변수로 연결 문자열 관리
- psycopg2 또는 asyncpg 사용
- 반환 딕셔너리 키는 api-contract-v2.md context 필드 규칙(camelCase) 준수
"""
import os
from typing import Any

# RDS_READ_URL = os.getenv("RDS_READ_URL")  # 추후 .env에 추가


def lookup_order_context(inquiry_id: str) -> dict[str, Any] | None:
    """
    inquiry_id로 주문/배송 정보를 RDS에서 조회한다.
    반환 딕셔너리는 inquiry.context 형식과 동일하게 camelCase 키를 사용한다.

    stub: 항상 None 반환 → 상위 로직이 RAG 경로로 진행됨 (현재 동작 유지).

    실제 구현 예시:
        row = db.execute(
            "SELECT order_status, tracking_number, expected_delivery_date, ..."
            " FROM orders WHERE inquiry_id = %s",
            (inquiry_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "orderStatus": row.order_status,
            "trackingNumber": row.tracking_number,
            "expectedDeliveryDate": str(row.expected_delivery_date),
            "matchedOrderCount": 1,
        }
    """
    return None  # stub
```

---

### `process_inquiry.py`에서의 연결 위치

RDS 조회는 `classify_inquiry` **이후**, `decide_auto_reply` **이전**에 삽입한다.
classify는 DB 데이터 없이 LLM으로만 처리하므로 RDS 조회가 필요 없다.
stub 단계에서는 `None`을 반환하므로 기존 동작이 그대로 유지된다.

```python
# process_inquiry.py 내 _process_inquiry() 변경 위치

from app.boundaries import rds_reader  # 추가

def _process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    classification = classify_inquiry(inquiry)  # [1] LLM만 호출

    if classification.category == InquiryCategory.ETC:
        return InquiryProcessResult(
            status=ProcessStatus.NEEDS_REVIEW,
            data=_needs_review_data(inquiry, reason=f"[Complex] {classification.reason}"),
            error=None,
        )

    # ── [2] RDS 조회 — classify 이후 무조건 실행 (stub: 현재 None 반환) ──
    db_context = rds_reader.lookup_order_context(inquiry.inquiry_id)
    if db_context is not None:
        inquiry = inquiry.model_copy(update={"context": db_context})
    # ────────────────────────────────────────────────────────────────────

    auto_reply = decide_auto_reply(inquiry, classification)  # [3]
    ...  # 이하 기존 동일
```

`inquiry.model_copy(update={"context": db_context})`: Pydantic v2 방식으로 inquiry를 변경하지 않고 새 인스턴스를 생성한다.

---

### 환경 변수 추가 (`.env`)

```env
# RDS 읽기 전용 연결 문자열 (stub 단계에서는 비워둠)
# 형식: postgresql://user:password@host:5432/dbname
RDS_READ_URL=
```

---

### 파일 변경 목록 (RDS 프레임워크)

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `app/boundaries/rds_reader.py` | 신규 (stub) | RDS 읽기 전용 조회 인터페이스 — 실제 연결은 추후 구현 |
| `app/workflow/process_inquiry.py` | 수정 | `rds_reader.lookup_order_context()` 호출 삽입 |
| `.env` | 수정 | `RDS_READ_URL` 항목 추가 |

---

### stub 단계 동작 확인

stub 상태에서는 `lookup_order_context()`가 `None`을 반환하므로 현재 흐름과 동일하게 동작한다.

```bash
# stub 상태 확인 — 기존 테스트 전부 통과해야 함
pytest tests/ -x --tb=short -q
```

---

### 실제 구현 시 체크리스트

```
[ ] RDS 읽기 전용 사용자 계정 및 접근 권한 확정 (DBA 협의)
[ ] 조회 대상 테이블 및 컬럼 스키마 확정 (백엔드 협의)
[ ] RDS_READ_URL 환경변수 설정 (로컬 .env, ECS Task Definition)
[ ] psycopg2 또는 asyncpg 의존성 추가 (pyproject.toml)
[ ] lookup_order_context() stub → 실제 쿼리 구현
[ ] HSA_TEST_MODE=true 시 DB 연결 skip 처리 (document_loader.py 패턴 동일)
[ ] 통합 테스트: RDS 조회 성공 케이스 추가
[ ] api-contract-v2.md "AI는 백엔드 DB를 직접 조회하지 않는다" 항목 수정
```

---

## 이번 범위 외 (후속 작업)

| 항목 | 현재 상태 |
|---|---|
| `riskTags` 실제 감지 로직 | `process_inquiry.py`에서 `[]` 하드코딩 상태 |
| VectorDB(Chroma 등) 도입 | `framework-decision.md`: 문서 수 증가 시 후속 검토 |
| evals 구현 | `AGENTS.md`: 구현 단계에서 생성 |
| RDS 읽기 전용 실제 구현 | `rds_reader.py` stub 상태, DB 스키마 확정 후 구현 |
| `api-contract-v2.md` 수정 | "AI는 DB를 직접 조회하지 않는다" → RDS 직접 접근으로 변경 필요 |
