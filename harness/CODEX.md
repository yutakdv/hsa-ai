# CODEX.md

HSA 프로젝트 Codex 전용 행동 지침.
Codex는 대화형 AI가 아니라 코드 생성/편집 도구이므로, Claude와 다른 방식으로 작동한다.
이 파일은 그 차이를 보완하기 위한 Codex 전용 기준을 정의한다.

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

**작업 시작 전 읽어야 할 파일:**

```
schemas/classification.py     ← ClassificationResult 모델
schemas/auto_reply.py         ← AutoReplyDecision 모델
schemas/rag_draft.py          ← RagDraftAnswer 모델
schemas/inquiry.py            ← CustomerInquiry 입력 모델
docs/ai_spec.md               ← 처리 흐름 전체 기준
```

스키마를 읽기 전에 코드를 작성하지 않는다.
특히 출력 타입 힌트를 직접 타이핑하지 말고, 반드시 `schemas/`에서 import해서 사용한다.

```python
# 올바른 패턴
from schemas.classification import ClassificationResult

def classify(content: str) -> ClassificationResult:
    ...

# 잘못된 패턴 - 스키마를 읽지 않고 직접 작성
def classify(content: str) -> dict:
    return {"category": "배송 문의", "confidence": 0.9}
```

---

## 2. 함수 단위 작업 기준

Codex는 함수 단위로 작업한다. 하나의 함수는 하나의 AI 출력 단계만 처리한다.

**HSA AI 파트 함수 3개:**

```python
# 1. 문의 분류
def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    ...

# 2. 자동응답 판단
def decide_auto_reply(inquiry: CustomerInquiry, classification: ClassificationResult) -> AutoReplyDecision:
    ...

# 3. RAG 초안 생성
def generate_rag_draft(inquiry: CustomerInquiry) -> RagDraftAnswer:
    ...
```

각 함수는:
- 반환 타입을 Pydantic 모델로 명시한다.
- 내부에서 LLM 출력을 Pydantic 모델로 파싱한다.
- 파싱 실패 시 예외를 발생시키고 호출부에서 처리하게 한다.

---

## 3. Pydantic 파싱 패턴

Codex가 LLM 출력을 처리할 때 반드시 따르는 패턴.

```python
import json
from pydantic import ValidationError
from schemas.classification import ClassificationResult

def parse_classification(llm_output: str) -> ClassificationResult:
    try:
        data = json.loads(llm_output)
        return ClassificationResult(**data)
    except json.JSONDecodeError:
        # LLM이 JSON이 아닌 텍스트를 반환한 경우
        raise ValueError(f"LLM output is not valid JSON: {llm_output[:100]}")
    except ValidationError as e:
        # 필드 타입 불일치, 필수 필드 누락 등
        raise ValueError(f"Schema validation failed: {e}")
```

파싱 실패를 조용히 무시하지 않는다.
실패 로그를 남기고 호출부에서 `관리자 검토 필요` 상태로 전환하게 한다.

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
# 올바른 패턴 - 애매한 경우 false가 기본값
decision = AutoReplyDecision(
    auto_reply_available=False,
    reason="DB 조회 결과가 불명확하여 관리자 검토 필요",
    required_data=[]
)

# 잘못된 패턴 - 추측으로 true 반환
decision = AutoReplyDecision(
    auto_reply_available=True,  # DB 확인 없이 추측
    reason="배송 문의이므로 자동응답 가능할 것으로 판단",
    required_data=[]
)
```

**RAG 초안 생성 금지 조건:**
`used_documents`가 비어 있으면 `RagDraftAnswer`를 반환하지 않는다.
이 경우 별도 예외 또는 `직접 응답 필요` 상태를 반환하는 함수를 사용한다.

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

모든 코드 변경 후 evals를 실행한다.

- 실패 시:
  → 코드 수정 우선
  → 해결되지 않으면 규칙 추가

eval 실패 상태에서 PR 금지

---

## 8. 실패 기록 규칙

- 동일 유형 실패가 반복되면:
  → 이 문서 또는 AGENTS.md에 규칙으로 승격

- 단발성 실패:
  → 하단 "실패 기록"에 추가

---

## 9. 브랜치 & PR 규칙

**브랜치 네이밍:**
```
{type}/{issue number}
예: feat/#5, fix/#11
```
작업 시작 전 이슈를 먼저 생성하고, 이슈 번호로 브랜치를 만든다.
브랜치 생성 전 develop 브랜치를 pull 받는다.
작업 완료 후 develop 브랜치로 PR을 올린다.

**PR 규칙:**
- Assignee: 본인 지정
- Reviewers: 본인 제외 팀원 전원 지정
- PR 생성 후 카카오톡으로 공유
- 팀원 1명 이상 승인 후 merge
- merge된 브랜치는 자동 삭제 (필요 시 복구 가능)

---

## 10. 커밋 메시지 규칙

Codex가 커밋 메시지를 생성할 때 아래 형식을 따른다.

```
Type: 커밋 제목
```

| Type | 사용 조건 |
|---|---|
| `Feat` | 새로운 기능 추가 |
| `Fix` | 버그 수정 |
| `Refactor` | 동작 변경 없는 코드 구조 개선 |
| `Test` | 테스트 코드 추가/수정 |
| `Docs` | 문서 수정 |
| `Style` | 코드 formatting, 세미콜론 누락 등 코드 자체 변경이 없는 경우 |
| `Chore` | 패키지, `.gitignore` 등 설정 파일 변경 |
| `Design` | CSS 등 사용자 UI 디자인 변경 |
| `Comment` | 필요한 주석 추가 및 변경 |
| `Rename` | 파일 또는 폴더명 수정/이동만인 경우 |
| `Remove` | 파일 삭제 작업만인 경우 |
| `Init` | 프로젝트 초기 세팅 |
| `Merge` | 브랜치 merge |
| `!BREAKING CHANGE` | 스키마 필드 삭제, 타입 변경 등 인터페이스 변경 |
| `!HOTFIX` | 치명적 버그 즉시 수정 |

`!BREAKING CHANGE`는 반드시 변경 내용과 영향받는 필드를 커밋 본문에 명시한다.

---

## 11. 실패 기록

Codex 사용 중 발생한 실수와 대응 기준을 이 섹션에 쌓는다.
패턴이 반복되면 위 섹션의 규칙으로 올린다.

| 날짜 | 실수 내용 | 대응 |
|---|---|---|
| - | - | - |

> 실패가 생기면 이 표에 추가한다. 처음부터 완벽할 필요 없다.

---

*이 파일은 Codex 사용자만 적용한다. 공통 규칙은 AGENTS.md를 따른다.*
