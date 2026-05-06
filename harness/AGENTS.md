# AGENTS.md

HSA (Hanyang Support Agent) AI 파트 공통 진입 가이드.
작업 시작 전 반드시 이 파일을 먼저 읽는다.

---

## 프로젝트 한 줄 요약

고객 문의를 자동 분류하고, DB 조회로 확정 가능한 문의는 자동응답하며,
정책/상품 판단이 필요한 문의는 RAG 기반 초안을 생성해 관리자 검토를 보조하는 Agent 시스템.

---

## 문서 읽기 순서

작업 전 아래 순서대로 로드한다.

```
1. harness/AGENTS.md         ← 지금 이 파일 (내부 구현 규칙)
2. docs/api-contract-v2.md   ← 외부 계약 single source of truth
3. schemas/                  ← Pydantic 모델 정의 (출력 스키마 계약)
4. harness/CLAUDE.md         ← Claude 사용자만
   harness/CODEX.md          ← Codex 사용자만
```

---

## 실행 흐름 (Execution Flow)

모든 작업은 아래 순서를 따른다:

1. AGENTS.md 로드
2. docs/api-contract-v2.md 확인
3. schemas/로 출력 구조 확정
4. (Claude / Codex) 전용 가이드 로드
5. 작업 수행
6. Pydantic 검증
7. evals 테스트 실행
8. 실패 시 수정 후 재시도 (최대 2회)
9. 반복 실패 시 `needs_review` 처리

---

## AI 역할 범위

AI가 하는 일:
- 고객 문의 유형 분류
- 자동응답 가능 여부 판단
- RAG 기반 답변 초안 생성

AI가 하지 않는 일:
- 환불/교환/클레임 최종 판단
- DB나 문서에 없는 내용 추측
- 정책 해석이 필요한 답변 자동 발송
- 관리자 검토 없이 임의 자동 처리
- 고객에게 추가 정보를 직접 요청

---

## 절대 하면 안 되는 것

- `schemas/`의 Pydantic 모델을 백엔드 협의 없이 수정하지 않는다.
- `usedSources`가 비었을 때 RAG 초안을 생성하지 않는다. → `needs_review` 처리.
- `AutoReplyDecision.available: true` 판단을 DB 조회 확인 없이 내리지 않는다.
- 복합 문의를 억지로 세부 분류하지 않는다. → `기타 문의` 처리.
- 스키마 필드 삭제 또는 타입 변경 시 반드시 `!BREAKING CHANGE` 커밋으로 명시한다.
- 자동응답을 LLM이 자유 문장으로 생성하지 않는다. → 반드시 아래 템플릿에 context값을 삽입하는 방식으로만 처리한다.

```
현재 고객님의 주문은 {orderStatus} 상태이며, 예상 도착일은 {expectedDeliveryDate}입니다.
송장번호는 {trackingNumber}입니다.
```

---

## 내부 인터페이스 규칙

외부 JSON 계약은 `docs/api-contract-v2.md`를 따른다. 이 섹션은 AI 파트 내부 구현이 외부 계약을 어떻게 풀어내는지만 다룬다.

이중 컨벤션 규칙
1. **내부 Python 코드:** 함수명·변수명·필드 정의 모두 `snake_case`
2. **외부 JSON:** Request/Response의 모든 필드명은 `camelCase`
   - `context` 안의 사용자 정의 필드도 camelCase 유지 (예: `order_status`가 아닌 `orderStatus`)
3. 자동 변환: `schemas/base.py`의 `BaseHsaModel`이 `alias_generator=to_camel`을 통해 처리한다. 모든 Pydantic 모델은 `BaseHsaModel`을 상속한다.

함수 시그니처
api-contract-v2.md의 단일 endpoint(URL은 api-contract-v2.md를 단일 출처로 한다)는 내부적으로 아래 orchestrator를 호출한다.

``` python
def process_inquiry(inquiry: CustomerInquiry) -> InquiryProcessResult:
    """단일 진입점. 아래 3개 함수를 순서대로 호출하고 통합 응답을 반환한다."""

def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    ...

def decide_auto_reply(
    inquiry: CustomerInquiry,
    classification: ClassificationResult,
) -> AutoReplyDecision:
    ...

def generate_rag_draft(inquiry: CustomerInquiry) -> RagDraftAnswer | None:
    """근거 부족 시 None 반환. usedSources는 process_inquiry가 관리한다."""
```

### 함수 호출 경계
 
- `classify_inquiry`: LLM만 호출. RAG·DB 조회 금지.
- `decide_auto_reply`: `context`와 `classification`만 본다. LLM 호출은 선택적.
- `generate_rag_draft`: LlamaIndex 검색만 사용. DB 조회 금지.
- 결과를 묶고 `usedSources`/`needsAdminReview`/`riskTags`를 결정하는 일은 `process_inquiry`만 한다.
### 자동응답 책임 경계
 
- **AI:** 자동응답 가능 여부 판단 + 템플릿에 `context` 값 삽입까지 수행.
- **백엔드:** 채워진 응답을 받아 고객 채널로 전송.
따라서 `AutoReplyDecision`은 다음 필드를 포함한다.
 
- `available: bool`
- `filled_answer: Optional[str]` (`available=True`일 때만 채움)
- `reason: str`

### `process_inquiry` 집약 규칙

`process_inquiry`는 내부 처리 결과를 `InquiryProcessData`의 플랫 필드로 집약한다.

| `InquiryProcessData` 외부 필드 | 소스 | 조건 |
|---|---|---|
| `auto_reply_available` | `AutoReplyDecision.available` | 항상 |
| `draft_answer` | `AutoReplyDecision.filled_answer` | `available=True` |
| `draft_answer` | `RagDraftAnswer.draft_answer` | `available=False`, 근거 있음 |
| `draft_answer` | `None` | 근거 없음 |
| `reason` | `AutoReplyDecision.reason` | `available=True` |
| `reason` | `RagDraftAnswer.reason` | RAG 초안 생성 시 |
| `reason` | `[No_Context]` / `[Complex]` 태그 문자열 | `needs_review` 시 |

---

## 실패 처리 및 재시도 규칙

다음 상황에서는 반드시 실패로 처리한다.
 
| 상황 | 처리 |
|---|---|
| JSON 파싱 실패 | `status = error` |
| Pydantic 검증 실패 | `status = error` |
| LLM 호출 timeout / 외부 시스템 실패 | `status = error` |
| RAG 근거 부족 (`usedSources`가 빈 배열) | `status = needs_review` |
| 복합 문의 (분류 결과가 `기타 문의`) | `status = needs_review` |
| `riskTags`에 `refund` 또는 `claim` 포함 | `needsAdminReview = true` (status는 success일 수 있음) |
| `riskTags`에 `policy_conflict` 포함 | `needsAdminReview = true` (status는 success일 수 있음) |
 
재시도 정책:
- **1차 실패:** 동일 프롬프트로 단순 재실행 (일시적 모델 생성 오류 대응).
- **2차 실패:** 출력 형식 강제 지시 추가 (`"Return JSON only. No prose, no markdown fences."`).
- **최종 실패:** 2회 재시도 후에도 오류 시 `status: "error"` 또는 `status: "needs_review"` 처리.

---

## Eval 실행 의무

> **현재 상태:** `evals/` 폴더는 구현 단계에서 생성한다. 초기 세팅 단계에서는 아래 기준을 목표 사양으로 확정하고, 실제 코드 작성 시 이 기준에 맞는 eval을 함께 구현한다.

모든 변경은 evals를 통과해야 한다.
 
평가 지표는 4가지를 사용한다.
 
| 지표 | 목표 |
|---|---|
| 분류 정확도 | 80% 이상 |
| 자동응답 분기 정확도 | 85% 이상 |
| Pydantic 검증 통과율 | 95% 이상 |
| RAG 근거 일치율 | 80% 이상 |
 
PR 통과 조건 (구현 단계 이후 적용):
- 위 4개 지표 모두 목표치 이상.
- 실패 태스크가 1개라도 있으면 PR 금지.
- GitHub Actions에서 자동 실행되며 미달 시 merge 차단.

실행 방법 (구현 단계 이후 적용):
- 로컬: PR 생성 전 `python evals/main.py` 수행하여 검증 완료.
- `evals/main.py`는 `runner.py`(테스트 실행)와 `grader.py`(채점)를 통합 호출하여 최종 리포트를 생성한다.

구현 시 생성할 파일:
```text
evals/
  tasks.json    ← 평가용 골든 데이터셋
  runner.py     ← 테스트 실행 엔진
  grader.py     ← 응답 채점 로직
  report.py     ← 리포트 생성
  main.py       ← 전체 평가 통합 실행
```

---

## Reasoning 작성 표준 가이드

PoC 단계에서는 아래 2개 태그만 사용한다.
 
| 상황 | 템플릿 | 예시 |
|---|---|---|
| 복합 문의 | `[Complex] {주제1}와 {주제2} 혼재 (키워드: {핵심단어})` | `[Complex] 배송과 환불 혼재 (키워드: '도착', '반품')` |
| 근거 부족 | `[No_Context] 관련 근거 문서 없음 (검색어: {검색어})` | `[No_Context] HSA-v2 정보 없음 (검색어: v2 출시일)` |
 
v2에서 추가 검토: `[Conflict]`, `[Low_Confidence]`.
 
작성 원칙:
1. `[Tag]`를 사용하여 관리자가 필터링하기 쉽게 한다.
2. 판단의 근거가 된 핵심 키워드를 반드시 포함한다.
3. 간결하게 사실 위주로만 기술한다.

---

## 브랜치 / PR / 커밋 규칙
 
### 브랜치 네이밍
 
```
{type}/{issue number}
예: feat/#5, fix/#11
```
 
- 작업 시작 전 이슈를 먼저 생성하고, 이슈 번호로 브랜치를 만든다.
- 브랜치 생성 전 `develop` 브랜치를 pull 받는다.
- 작업 완료 후 `develop` 브랜치로 PR을 올린다.
### PR 규칙
 
- Assignee: 본인 지정.
- Reviewers: 본인 제외 팀원 전원 지정.
- PR 생성 후 카카오톡으로 공유.
- 팀원 1명 이상 코멘트 후 PR 작성자가 직접 승인하여 merge.
- merge된 브랜치는 자동 삭제 (필요 시 복구 가능).
### 커밋 메시지 형식
 
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
| `Style` | 코드 formatting 등 코드 자체 변경이 없는 경우 |
| `Chore` | 패키지, `.gitignore` 등 설정 파일 변경 |
| `Comment` | 주석 추가/변경 |
| `Rename` | 파일/폴더명 수정/이동만인 경우 |
| `Remove` | 파일 삭제 작업만인 경우 |
| `Init` | 프로젝트 초기 세팅 |
| `Merge` | 브랜치 merge |
| `!BREAKING CHANGE` | 스키마 필드 삭제, 타입 변경 등 인터페이스 변경 |
| `!HOTFIX` | 치명적 버그 즉시 수정 |
 
`!BREAKING CHANGE`는 변경 내용과 영향받는 필드를 커밋 본문에 명시한다.
 
---
 
## 하네스 진화 규칙
 
- 동일 유형 실패 2회 이상 발생 시 → AGENTS.md 또는 모델별 문서에 규칙 추가.
- 새로운 edge case 발견 시 → evals에 테스트 케이스 추가.
- 규칙은 처음부터 완벽할 필요 없다. 실패 기반으로 점진적으로 개선한다.

---
 
## 작업 시작 전 체크리스트
 
```
[ ] 관련 Pydantic 스키마를 확인했는가 (schemas/)
[ ] 이 변경이 백엔드 인터페이스에 영향을 주는가 (api-contract-v2.md 갱신 필요 여부)
[ ] 모델이 BaseHsaModel을 상속하는가 (camelCase 자동 변환 보장)
[ ] AI 출력이 Pydantic 검증을 통과할 수 있는 형태인가
[ ] 자동응답 판단 근거가 DB 조회 결과인가 (정책 해석 포함 시 초안으로 전환)
[ ] 함수명이 snake_case인가 (Python 내부 코드 기준)
[ ] JSON 응답이 status / data / error 래퍼 구조를 따르며 모든 필드가 camelCase인가
```
 
---
 
*이 파일은 항상 적용되는 규칙만 포함한다. 도구별 세부 지침은 CLAUDE.md / CODEX.md에서 관리한다.*