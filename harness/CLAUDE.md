# CLAUDE.md

HSA 프로젝트 Claude 전용 행동 지침.
기본 코딩 원칙(1~4) + HSA 전용 원칙(5~9)으로 구성된다.
공통 규칙은 AGENTS.md를 따른다.

---

## 1. Think Before Coding

**가정하지 말 것. 혼란을 숨기지 말 것. 트레이드오프를 드러낼 것.**

구현 전에:
- 가정을 명시적으로 밝힌다. 불확실하면 질문한다.
- 해석이 여러 가지라면 선택지를 제시한다. 조용히 하나를 고르지 않는다.
- 더 단순한 방법이 있다면 먼저 말한다. 필요하면 반론을 제기한다.
- 무언가 불명확하면 멈춘다. 무엇이 모호한지 명시하고 질문한다.

---

## 2. Simplicity First

**문제를 해결하는 최소한의 코드. 추측성 코드 금지.**

- 요청하지 않은 기능은 추가하지 않는다.
- 단일 사용 코드에 추상화를 만들지 않는다.
- 요청하지 않은 유연성이나 설정 가능성을 추가하지 않는다.
- 불가능한 시나리오에 대한 에러 핸들링을 넣지 않는다.
- 200줄로 작성했는데 50줄로 가능하다면 다시 작성한다.

스스로 물어볼 것: "시니어 엔지니어가 이걸 보면 과도하다고 할까?" 그렇다면 단순화한다.

---

## 3. Surgical Changes

**반드시 필요한 것만 수정한다. 내가 만든 문제만 정리한다.**

기존 코드 수정 시:
- 인접한 코드, 주석, 포맷을 "개선"하지 않는다.
- 동작하는 코드를 리팩토링하지 않는다.
- 나라면 다르게 작성했더라도 기존 스타일을 따른다.
- 관련 없는 dead code를 발견하면 언급만 하고 삭제하지 않는다.

내 변경으로 생긴 orphan은 정리한다:
- 내 변경으로 사용되지 않게 된 import/변수/함수는 제거한다.
- 기존에 있던 dead code는 요청이 없으면 건드리지 않는다.

테스트: 변경된 모든 줄이 사용자 요청으로 직접 추적 가능해야 한다.

---

## 4. Goal-Driven Execution

**성공 기준을 정의한다. 검증될 때까지 반복한다.**

작업을 검증 가능한 목표로 변환한다:
- "검증 추가" → "잘못된 입력에 대한 테스트 작성 후 통과시키기"
- "버그 수정" → "버그를 재현하는 테스트 작성 후 통과시키기"
- "X 리팩토링" → "리팩토링 전후로 테스트가 통과하는지 확인"

멀티스텝 작업은 간단한 계획을 먼저 제시한다:
```
1. [단계] → 검증: [확인 방법]
2. [단계] → 검증: [확인 방법]
3. [단계] → 검증: [확인 방법]
```

---

## 5. HSA 작업 범위 제한

작업 범위 경계와 공통 판단 기준은
**AGENTS.md "AI 역할 범위", "절대 하면 안 되는 것"** 및
**docs/api-contract-v2.md "기본 원칙", "관리자 검토가 필요한 경우"** 를 따른다.

아래는 Claude가 추가로 적용하는 사고 방식이다.

**분류:**
`confidence`가 낮을 때 높은 값처럼 보이도록 이유를 꾸며내지 않는다.

**자동응답 판단:**
- 정책 해석, 예외 상황, 문서 검색이 필요한 경우는 반드시 RAG 초안 생성으로 전환한다.
- 애매한 경우 `available: false`가 기본값이다.

**RAG 초안 생성:**
검색된 문서 간 내용이 충돌하면 `riskTags`에 `policy_conflict`를 포함하고 `needsAdminReview: true`로 처리한다.
(→ AGENTS.md 실패 처리 테이블에도 등재됨)

**신뢰도 대응 수칙:**
PoC에서는 `confidence`를 hard threshold로 사용하지 않는다.
LLM의 self-reported confidence는 실제 정답률과 일치하지 않을 수 있으며,
evals에서 calibration을 측정한 뒤 v2에서 임계값 도입을 재검토한다.

대신 아래의 관찰 가능한 신호를 `needs_review` 기준으로 사용한다.

- 분류 결과가 `기타 문의`인 경우
- `usedSources`가 비어 있는 경우
- `riskTags`에 `refund`, `claim`, `policy_conflict`이 포함된 경우

**정보 부족 시 행동:**
정보가 부족하면 `needs_review`로 처리하고 `reason`에 `[No_Context]` 태그와 함께
관리자가 추가로 확인할 정보를 명시한다. (reasoning 표준은 AGENTS.md "Reasoning 작성 표준 가이드" 참조)

---

## 6. 실행 제한

- 질문/가정 단계는 최대 1회까지만 수행한다.
- 추가 정보 없이 해결 가능하면 즉시 구현한다.
- LLM 재시도는 최대 2회. 2회 실패 시 `status="error"` 또는 `"needs_review"` 반환.

---

## 7. 출력 형식 강제

모든 AI 출력은 `schemas/`의 Pydantic 모델을 통과해야 한다.
명칭 규격은 AGENTS.md "내부 인터페이스 규칙"의 이중 컨벤션을 따른다.

### 코드 패턴 (Pydantic v2)
 
```python
# 올바른 패턴: 내부 로직은 snake_case, 출력은 BaseHsaModel을 통해 camelCase로 변환됨
def classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    raw = call_llm(build_classify_prompt(inquiry))
    return ClassificationResult.model_validate_json(raw)
 
# 잘못된 패턴: 함수명에 camelCase 사용 금지
def classifyInquiry(inquiry: CustomerInquiry) -> ClassificationResult:
    ...
```
 
`model_validate_json`은 JSON 파싱과 스키마 검증을 한 번에 수행하고, 실패 시 `ValidationError`로 통합된다.
`json.loads(...) + Model(**data)` 패턴은 사용하지 않는다.
 
### 프롬프트 작성 규칙
 
- 모든 프롬프트에 다음 지시어를 포함한다:
  `"Return JSON only. All keys must be in camelCase."`
- 2차 재시도 시에는 위 지시어 외에 추가:
  `"No prose, no markdown fences."`
### 파싱 또는 Pydantic 검증 실패 시
 
1. 예외를 잡아 로그에 기록한다.
2. 재시도 로직을 최대 2회까지 수행한다.
3. 그래도 실패하면 `status="error"`로 반환한다.

---

## 8. 출력 안정성

- 동일 입력에 대해 가능한 한 동일한 출력 구조를 유지한다.
- reasoning 과정은 출력에 포함하지 않는다 (`reason` 필드의 한 줄 요약은 예외).
- 반드시 Pydantic 스키마 형태로만 반환한다.
`schemas/base.py`의 `BaseHsaModel`을 상속한다. 자세한 컨벤션은 AGENTS.md "내부 인터페이스 규칙" 참조.

---

## 9. Eval 기준 적용

작업 완료 후 반드시 eval 기준을 확인한다.
 
평가 지표 4가지(분류 정확도, 자동응답 분기 정확도, Pydantic 검증 통과율, RAG 근거 일치율)와
목표치는 AGENTS.md "Eval 실행 의무" 섹션을 참조한다.
 
목표 미달 시:
1. 프롬프트 수정 우선.
2. 그래도 실패하면 모델 변경을 검토한다.
감으로 수정하지 않는다.

---

*이 파일은 Claude 사용자만 적용한다. 공통 규칙은 AGENTS.md를 따른다.*
