# 아키텍처 문서

상태: decision

## 전체 연결 방향

HSA 서비스의 기본 연결 방향은 다음과 같다.

```text
Frontend <-> Backend <-> AI
```

AI 파트는 백엔드 뒤에 있는 보조 서비스다.
프론트엔드, 고객 채널, 실제 응답 전송은 AI가 직접 처리하지 않는다.
정책 문서와 답변 생성 지식은 AI 파트가 관리한다.

## 아키텍처 결정

HSA AI 파트는 초기 PoC에서 `Lightweight Layered Architecture`를 사용한다.

하나의 FastAPI 서비스 안에서 다음 계층만 가볍게 분리한다.

```text
api -> schemas -> workflow -> services -> boundaries
```

이 방식은 과한 Clean Architecture나 Microservice 구조를 피하면서도,
백엔드와의 API 계약과 AI 내부 책임을 명확히 나누기 위한 선택이다.

## 기본 의존성 방향

AI 내부의 의존성은 위에서 아래로만 흐른다.

```text
api
  └─ workflow
       └─ services
            └─ boundaries/adapters
                   └─ external systems (LLM, LlamaIndex)

schemas ← 모든 계층이 공유. 루트 레벨에 위치.
```

- `service`가 FastAPI route를 직접 호출하지 않는다.
- `service`가 LLM SDK나 LlamaIndex를 직접 호출하지 않는다. `boundaries`를 통해서만 접근한다.
- RAG boundary가 실제 검색 source를 계산하고, `workflow`가 외부 `usedSources`로 집약한다.
- `workflow`가 `needsAdminReview`, `riskTags`를 결정한다. `service`는 하지 않는다.

## 계층별 역할

### api

역할:
- 백엔드 요청 수신
- `CustomerInquiry` Pydantic 검증
- `process_inquiry` (workflow) 호출
- `InquiryProcessResult` 반환

포함하지 않는 것:
- 판단 로직
- LLM 호출
- 프론트엔드 직접 연결

### workflow

orchestrator 역할. `process_inquiry` 함수가 아래 3개 service를 순서대로 호출하고 결과를 집약한다.

```text
1. CustomerInquiry Pydantic 검증
2. classify_inquiry     : LLM으로 문의 유형 분류
   └ 기타 문의          → status: needs_review, reason: [Complex]
3. decide_auto_reply    : context + classification 기반 자동응답 판단
   ├ available=true     → 템플릿에 context 값 삽입 (RAG 생략)
   └ available=false    → generate_rag_draft 호출
4. generate_rag_draft   : LlamaIndex로 정책 문서 검색 후 LLM reranker로 근거 선택
   └ usedSources 빈 배열 → status: needs_review, reason: [No_Context]
5. usedSources / riskTags / needsAdminReview 집약
6. InquiryProcessResult 반환
```

함수 시그니처:

```python
def process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """단일 진입점. 아래 3개 함수를 순서대로 호출하고 통합 응답을 반환한다."""
```

### services

각 함수는 단일 책임을 가진다. 호출 경계를 엄격히 지킨다.

| 함수 | 허용 외부 호출 | 금지 |
| --- | --- | --- |
| `classify_inquiry` | LLM만 | RAG, DB 조회 |
| `decide_auto_reply` | context + classification, LLM 선택적 | DB 조회 |
| `generate_rag_draft` | LlamaIndex 검색만 | LLM 직접 호출, DB 조회 |

함수 시그니처:

```python
def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    ...

def decide_auto_reply(
    inquiry: CustomerInquiry,
    classification: ClassificationResult,
) -> AutoReplyDecision:
    ...

def generate_rag_draft(
    inquiry: CustomerInquiry,
) -> tuple[RagDraftAnswer | None, list[RiskTag]]:
    """근거 부족 시 (None, ...) 반환. 정책 충돌 감지 시 risk_tags에 policy_conflict 포함."""
```

### boundaries/adapters

외부 시스템 연결부를 감싼다. 외부 시스템이 바뀌어도 service 로직 변경을 최소화한다.

| 파일 | 역할 |
| --- | --- |
| `llm_client.py` | LLM SDK 연결 |
| `policy_retriever.py` | LlamaIndex 기반 정책 문서 검색, threshold 필터, LLM reranker, RAG 답변 합성 |
| `document_loader.py` | Markdown 정책 문서 로딩 |

### schemas

모든 계층이 공유하는 Pydantic 데이터 계약. 루트 레벨에 위치하며 구현 단계 이전에 이미 확정됨.

| 파일 | 클래스 | 역할 |
| --- | --- | --- |
| `base.py` | `BaseHsaModel` | camelCase 자동 변환 기반 클래스 |
| `inquiry.py` | `CustomerInquiry` | 백엔드 요청 입력 (api 계층 수신) |
| `classification.py` | `ClassificationResult` | `classify_inquiry` 반환 타입 |
| `auto_reply.py` | `AutoReplyDecision` | `decide_auto_reply` 반환 타입 |
| `rag_draft.py` | `RagDraftAnswer` | `generate_rag_draft` 반환 타입 |
| `process_result.py` | `InquiryProcessResult` | 백엔드 최종 응답 (api 계층 반환) |

## 폴더 구조

아래 구조는 구현 시작 시점의 기준이다. `schemas/`는 초기 세팅 단계에서 이미 생성됨.

```text
hsa-AI/
├── schemas/
│   ├── base.py
│   ├── inquiry.py
│   ├── classification.py
│   ├── auto_reply.py
│   ├── rag_draft.py
│   └── process_result.py
├── app/
│   ├── main.py
│   ├── api/
│   │   └── routes.py            ← POST /api/inquiries/process
│   ├── workflow/
│   │   └── process_inquiry.py   ← orchestrator
│   ├── services/
│   │   ├── classify_inquiry.py
│   │   ├── decide_auto_reply.py
│   │   └── generate_rag_draft.py
│   ├── boundaries/
│   │   ├── llm_client.py
│   │   ├── policy_retriever.py
│   │   └── document_loader.py
│   └── docs/
│       └── policies/            ← AI 파트 관리 Markdown 정책 문서
│           ├── shipping.md
│           ├── exchange-refund.md
│           ├── product.md
│           └── response-tone.md
├── tests/                       ← 루트 레벨
├── evals/                       ← 루트 레벨 (python evals/main.py)
│   ├── tasks.json
│   ├── runner.py
│   ├── grader.py
│   ├── report.py
│   └── main.py
├── harness/
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   └── CODEX.md
└── docs/
```
