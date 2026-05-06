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
1. harness/AGENTS.md         ← 지금 이 파일
2. docs/api-contract.md      ← AI 파트 기준 문서 (처리 흐름, 출력 형식, 평가 기준)
3. schemas/                  ← Pydantic 모델 정의 (출력 스키마 계약)
4. harness/CLAUDE.md         ← Claude 사용자만
   harness/CODEX.md          ← Codex 사용자만
```

---

## 실행 흐름 (Execution Flow)

모든 작업은 아래 순서를 따른다:

1. AGENTS.md 로드
2. docs/api-contract.md 확인
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

---

## 절대 하면 안 되는 것

- `schemas/`의 Pydantic 모델을 백엔드 협의 없이 수정하지 않는다.
- `used_documents`가 비었을 때 RAG 초안을 생성하지 않는다. → `직접 응답 필요` 처리.
- `auto_reply_available: true` 판단을 DB 조회 확인 없이 내리지 않는다.
- 복합 문의를 억지로 세부 분류하지 않는다. → `기타 문의` 처리.
- 스키마 필드 삭제 또는 타입 변경 시 반드시 `!BREAKING CHANGE` 커밋으로 명시한다.
- 자동응답을 LLM이 자유 문장으로 생성하지 않는다. → 반드시 아래 템플릿에 DB 조회값을 삽입하는 방식으로만 처리한다.

```
현재 고객님의 주문은 {배송상태} 상태이며, 예상 도착일은 {예상도착일}입니다.
송장번호는 {송장번호}입니다.
```

---

## 백엔드 인터페이스 규칙

백엔드 팀과의 데이터 매핑 편의성과 Python 코드 품질을 위해 아래의 **이중 컨벤션 규칙**을 엄격히 준수한다.

1. **내부 로직 (Python):** 모든 함수명, 변수명, 필드 정의는 `snake_case`를 사용한다. (PEP 8 준수)
2. **외부 인터페이스 (JSON):** API 응답 및 요청 JSON의 필드명은 `camelCase`를 사용한다.
3. **자동 변환:** Pydantic의 `alias_generator=to_camel` 설정을 통해 수동 변환 없이 처리한다.

### 함수명 규칙
1. `classify_inquiry(inquiry: CustomerInquiry) -> ClassificationResult`
2. `decide_auto_reply(inquiry: CustomerInquiry, classification: ClassificationResult) -> AutoReplyDecision`
3. `generate_rag_draft(inquiry: CustomerInquiry) -> RagDraftAnswer`

### JSON 응답 형식 (일관된 구조 고정)

백엔드로 반환하는 모든 JSON은 아래 래퍼 구조를 따르며, 내부 데이터(`data`)는 반드시 `camelCase`로 직렬화되어야 한다.

```json
{
  "status": "success" | "error" | "needs_review",
  "data": { 
    "inquiryCategory": "배송 문의",  // 내부 필드명 inquiry_category가 자동 변환됨
    "confidenceScore": 0.86,
    "reasoningDetail": "..."
  },
  "error": null | "에러 메시지"
}
```

**`status` 값 기준:**

| status | 사용 조건 |
|---|---|
| `success` | Pydantic 검증 통과, 정상 처리 완료 |
| `error` | 파싱 실패, 검증 오류, 예외 발생 |
| `needs_review` | 근거 문서 없음, 복합 문의, 문서 충돌 등 관리자 검토 필요 |

**응답 예시:**

```json
// 정상 분류
{
  "status": "success",
  "data": {
    "category": "배송 문의",
    "confidence": 0.86,
    "reason": "배송 예정일을 묻는 문의입니다."
  },
  "error": null
}

// 검증 실패
{
  "status": "error",
  "data": null,
  "error": "Schema validation failed: confidence must be between 0.0 and 1.0"
}

// 관리자 검토 필요
{
  "status": "needs_review",
  "data": {
    "category": "기타 문의",
    "confidence": 0.41,
    "reason": "배송과 환불이 복합된 문의입니다."
  },
  "error": null
}
```

---

## 실패 처리 및 재시도 규칙

다음 상황에서는 반드시 실패로 처리한다:

- JSON 파싱 실패 → `status = error`
- Pydantic 검증 실패 → `status = error`
- RAG 근거 부족 (`used_documents` 비어 있음) → `status = needs_review`
- 복합 문의 → `status = needs_review`

재시도 정책:
- **1차 실패:** 동일 프롬프트로 단순 재실행 (일시적 모델 생성 오류 대응)
- **2차 실패:** 출력 형식 강제 지시 추가 ("반드시 JSON만 반환하고 부연 설명을 생략하라")
- **최종 실패:** 2회 재시도 후에도 오류 시 `status: "error"` 또는 `status: "needs_review"` 처리

---

## Eval 실행 의무

모든 변경은 evals를 통과해야 한다.

1. 실행 방법
- 로컬 실행: PR 생성 전 반드시 아래 명령어를 수행하여 로컬 검증을 마친다.
- 환경 구성: evals/main.py는 runner.py(테스트 실행)와 grader.py(채점)를 통합 호출하여 최종 리포트를 생성한다.

2. 통과 기준
- 평균 점수: 0.85 이상 달성 필수.
- Fail Task: 실패한 태스크가 하나라도 존재할 경우 PR 제출 금지.
- CI/CD: GitHub Actions 연동을 통해 PR 시 자동 실행되며, 기준 미달 시 Merge가 차단됨.

---

## Reasoning 작성 표준 가이드

`status: "needs_review"` 처리 시, 관리자가 상황을 즉시 파악할 수 있도록 `data.reason` 필드에 아래 대괄호 태그 형식을 준수하여 작성한다.

| 상황 | 템플릿 형식 | 예시 |
| :--- | :--- | :--- |
| **복합 문의** | `[Complex] {주제1}와 {주제2} 혼재 (키워드: {핵심단어})` | `[Complex] 배송과 환불 혼재 (키워드: '도착', '반품')` |
| **문서 충돌** | `[Conflict] {문서A}와 {문서B} 내용 상충 (지점: {내용})` | `[Conflict] 배송정책.md와 FAQ.md 상충 (지점: 무료배송 금액)` |
| **근거 부족** | `[No_Context] 관련 근거 문서 없음 (검색어: {검색어})` | `[No_Context] HSA-v2 정보 없음 (검색어: v2 출시일)` |
| **저신뢰도** | `[Low_Confidence] 분류 확신도 {값}%로 기준치 미달` | `[Low_Confidence] 분류 확신도 41%로 기준치 미달` |

**작성 원칙:**
1. **[Tag]**를 사용하여 관리자가 필터링하기 쉽게 한다.
2. 판단의 근거가 된 **핵심 키워드**를 반드시 포함한다.
3. 간결하게 사실 위주로만 기술한다.

---

### 💡 활용 예시 (JSON)

```json
{
  "status": "needs_review",
  "data": {
    "category": "기타 문의",
    "confidence": 0.41,
    "reason": "[Complex] 배송 상태 확인과 환불 규정이 혼재됨 (키워드: '언제오나요', '환불조건')"
  },
  "error": null
}
```

---

## 하네스 진화 규칙

- 동일 유형 실패 2회 이상 발생 시:
  → AGENTS.md 또는 모델별 문서에 규칙 추가

- 새로운 edge case 발견 시:
  → evals에 테스트 케이스 추가

- 규칙은 처음부터 완벽할 필요 없다.
  → 실패 기반으로 점진적 개선

---

## 작업 시작 전 체크리스트

```
[ ] 관련 Pydantic 스키마를 확인했는가 (schemas/)
[ ] 이 변경이 백엔드 인터페이스에 영향을 주는가
[ ] AI 출력이 Pydantic 검증을 통과할 수 있는 형태인가
[ ] 자동응답 판단 근거가 DB 조회 결과인가 (정책 해석 포함 시 초안으로 전환)
[ ] 함수명이 snake_case인가 (Python 내부 코드 기준)
[ ] JSON 응답이 status / data / error 래퍼 구조를 따르는가
```

---

## 평가 기준 (초기 목표)

| 지표 | 목표 |
|---|---|
| 분류 정확도 | 80% 이상 |
| 자동응답 분기 정확도 | 85% 이상 |
| Pydantic 검증 통과율 | 95% 이상 |
| RAG 근거 일치율 | 80% 이상 |

---

*이 파일은 항상 적용되는 규칙만 포함한다. 세부 지침은 각 AI별 파일에서 관리한다.*
