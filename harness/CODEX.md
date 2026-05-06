# CODEX.md

HSA 프로젝트 Codex 전용 행동 지침.
Codex는 대화형 AI가 아니라 코드 생성/편집 도구이므로, Claude와 다른 방식으로 작동한다.
이 파일은 그 차이를 보완하기 위한 Codex 전용 기준을 정의한다.
공통 규칙은 AGENTS.md를 따른다.

---

## Codex와 Claude의 차이

| 항목 | Claude | Codex |
|---|---|---|
| 컨텍스트 로딩 | 대화 중 문서 참조 가능 | 작업 전 파일을 직접 읽어야 함 |
| 작업 단위 | 대화 흐름 기반 | 함수/파일 단위 |
| 출력 형식 | 대화 + 코드 혼합 가능 | 코드 중심 |
| 검증 방법 | 대화 중 즉시 확인 가능 | 별도 실행/테스트로 확인 |

이 차이 때문에 Codex 사용 시 아래 원칙을 추가로 따른다.

---

## 1. 작업 전 컨텍스트 로딩
 
Codex는 대화 중 문서를 참조하기 어렵기 때문에 작업 전 직접 파일을 읽어야 한다.
 
### 읽어야 할 파일
 
```
schemas/base.py               ← BaseHsaModel (camelCase 변환 기반)
schemas/inquiry.py            ← CustomerInquiry (api-contract Request 매핑)
schemas/classification.py     ← ClassificationResult
schemas/auto_reply.py         ← AutoReplyDecision (filled_answer 포함)
schemas/rag_draft.py          ← RagDraftAnswer
schemas/process_result.py     ← InquiryProcessResult (통합 응답)
docs/api-contract-v2.md       ← 외부 계약 single source of truth
harness/AGENTS.md             ← 내부 인터페이스 규칙, 함수 호출 경계
```
 
스키마를 읽기 전에 코드를 작성하지 않는다.
특히 출력 타입 힌트를 직접 타이핑하지 말고, 반드시 `schemas/`에서 import해서 사용한다.

```python
# 올바른 패턴
from schemas.classification import ClassificationResult
 
def classify(inquiry: CustomerInquiry) -> ClassificationResult:
    ...
 
# 잘못된 패턴 - 스키마를 읽지 않고 직접 작성
def classify(content: str) -> dict:
    return {"category": "배송 문의", "confidence": 0.9}
```

---

## 2. 함수 단위 작업 기준

Codex는 함수 단위로 작업한다. 하나의 함수는 하나의 AI 출력 단계만 처리한다.
함수 시그니처와 호출 경계는 AGENTS.md "함수 시그니처" 및 "함수 호출 경계" 섹션을 따른다.

### HSA AI 파트 함수
 
```python
# 0. orchestrator (api-contract-v2.md POST /api/v1/inquiries/process의 진입점)
def process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    ...
 
# 1. 문의 분류
def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    ...
 
# 2. 자동응답 판단
def decide_auto_reply(
    inquiry: CustomerInquiry,
    classification: ClassificationResult,
) -> AutoReplyDecision:
    ...
 
# 3. RAG 초안 생성 (근거 부족 시 None 반환)
def generate_rag_draft(inquiry: CustomerInquiry) -> RagDraftAnswer | None:
    ...
```
 
각 함수는:
- 반환 타입을 Pydantic 모델(또는 `Optional`)로 명시한다.
- 내부에서 LLM 출력을 Pydantic 모델로 파싱한다.
- 파싱 실패 시 예외를 발생시키고 호출부(`process_inquiry`)에서 처리하게 한다.
`usedSources`, `needsAdminReview`, `riskTags`를 결정하는 일은 `process_inquiry`만 한다.

---

## 3. Pydantic 파싱 패턴

Codex가 LLM 출력을 처리할 때 반드시 따르는 패턴.

```python
from pydantic import ValidationError
from schemas.classification import ClassificationResult
 
def parse_classification(llm_output: str) -> ClassificationResult:
    try:
        return ClassificationResult.model_validate_json(llm_output)
    except ValidationError as e:
        # JSON 파싱 실패와 스키마 검증 실패를 모두 잡는다 (Pydantic v2)
        raise ValueError(f"LLM output validation failed: {e}")
```
 
`model_validate_json`은 JSON 파싱과 스키마 검증을 한 번에 수행하므로
`json.loads(...) + Model(**data)` 패턴은 사용하지 않는다.
 
파싱 실패를 조용히 무시하지 않는다.
실패 로그를 남기고 호출부에서 `status="error"` 또는 `needs_review` 상태로 전환하게 한다.

---

## 4. 작업 범위 제한

Codex가 코드를 생성할 때 넘지 말아야 할 경계.

**스키마 수정 금지:**
`schemas/`의 파일을 수정하려면 백엔드 팀과 협의가 필요하다.
필드 추가는 가능하지만, 아래 경우는 반드시 팀 협의 후 `!BREAKING CHANGE` 커밋으로 처리한다.
- 기존 필드 삭제
- 필드 타입 변경
- 필수 필드로 변경 (Optional 제거)

**자동 처리 범위 제한:**
```python
# 올바른 패턴 - 애매한 경우 available=False가 기본값
decision = AutoReplyDecision(
    available=False,
    filled_answer=None,
    reason="DB 조회 결과가 불명확하여 관리자 검토 필요",
)
 
# 잘못된 패턴 - DB 확인 없이 추측으로 true
decision = AutoReplyDecision(
    available=True,
    filled_answer="...",  # context 없이 추측한 응답
    reason="배송 문의이므로 자동응답 가능할 것으로 판단",
)
```
 
`AutoReplyDecision`은 model validator를 가진다:
- `available=True`인데 `filled_answer=None` → 검증 실패.
- `available=False`인데 `filled_answer`가 채워져 있음 → 검증 실패.

**RAG 초안 생성 금지 조건:**
`usedSources`가 비어 있으면(검색 결과 없음 또는 relevance threshold 미달) `RagDraftAnswer`를 반환하지 않는다.
이 경우 `generate_rag_draft`는 `None`을 반환하고, `process_inquiry`가 `status="needs_review"`로 처리한다.

**함수 호출 경계**
→ AGENTS.md "함수 호출 경계" 섹션을 따른다. 작업 전 반드시 읽는다.

---

## 5. 실행 후 검증

코드 작성 후 반드시 수행:

1. 테스트 실행
2. Pydantic 검증 확인
3. 최소 1개 이상의 실패 케이스 테스트

검증 없이 완료 처리 금지

---

## 6. 변경 영향 범위 제한

- 하나의 함수 수정 시 다른 함수 동작을 변경하지 않는다.
- 영향 범위가 2개 이상으로 확장되면 작업을 중단하고 분리한다.

---

## 7. Eval 연동

모든 코드 변경 후 evals를 실행한다. 평가 지표와 목표치는 AGENTS.md "Eval 실행 의무" 섹션을 참조한다.
 
- 실패 시 코드 수정 우선.
- 해결되지 않으면 규칙 추가.
- eval 실패 상태에서 PR 금지.

---

## 8. 실패 기록 규칙

- 동일 유형 실패가 반복되면 → 이 문서 또는 AGENTS.md에 규칙으로 승격.
- 단발성 실패 → 하단 "실패 기록"에 추가.

---

## 9. 브랜치 / PR / 커밋 규칙

공통 규칙은 AGENTS.md "브랜치 / PR / 커밋 규칙" 섹션을 따른다.
 
Codex 특이사항:
- 커밋 메시지 자동 생성 시 첫 줄에 `Type` 태그를 반드시 포함한다.
- 스키마 필드 삭제·타입 변경은 항상 `!BREAKING CHANGE` 태그를 사용하고, 영향받는 필드를 본문에 명시한다.

---

## 10. 실패 기록
 
Codex 사용 중 발생한 실수와 대응 기준을 이 섹션에 쌓는다.
패턴이 반복되면 위 섹션의 규칙으로 승격한다.
 
| 날짜 | 실수 내용 | 대응 |
|---|---|---|
| - | - | - |
 
> 실패가 생기면 이 표에 추가한다. 처음부터 완벽할 필요 없다.
 
---
 
*이 파일은 Codex 사용자만 적용한다. 공통 규칙은 AGENTS.md를 따른다.*
