# API 계약 수정안 (v2)

상태: decision
원본: docs/api-contract.md (deprecated → 이 문서로 대체됨)

## 변경 요약

| 항목 | 기존 | 수정 |
| --- | --- | --- |
| 엔드포인트 | `POST /api/v1/answers/draft` | `POST /api/inquiries/process` |
| 필드 컨벤션 | snake_case | camelCase (AGENTS.md 이중 컨벤션 준수) |
| 응답 구조 | flat | `status / data / error` 래퍼 |
| 응답 필드 추가 | — | `autoReplyAvailable` |
| 관리자 검토 조건 | — | `policy_conflict` 추가, LLM 실패 처리 정정 |
| 에러 응답 | 미정의 | 구조 신규 정의 |

---

## 목적

이 문서는 백엔드와 AI 파트가 어떤 데이터를 주고받을지 합의하기 위한 계약이다.

## 연결 방향

전체 서비스 연결 방향은 다음과 같다.

```text
Frontend <-> Backend <-> AI
```

AI는 백엔드하고만 통신한다.
프론트엔드 표시, 고객 응답 전송, 문의 저장, 주문/배송 DB 조회, 처리 상태 관리는 백엔드가 담당한다.
정책 문서와 답변 생성 지식은 AI 파트가 관리한다.

## API 계약의 핵심 전제

AI는 문의 데이터를 직접 수집하거나 저장하지 않는다.
AI는 백엔드가 넘겨준 문의 내용과 백엔드 보유 데이터 맥락을 보고, AI가 관리하는 Markdown 정책 문서와 LlamaIndex 검색 결과를 사용해 답변 초안을 생성한다.

따라서 Request는 "고객 문의 생성 요청"이 아니라 "이미 백엔드에 저장된 문의에 대한 처리 요청"이다.

## 역할 분리

| 영역 | 담당 |
| --- | --- |
| Backend | 문의 저장, 주문/배송 DB 조회, 고객/문의 상태 관리, AI 호출, 응답 전송 |
| AI | 정책 문서 관리, Markdown/LlamaIndex 기반 근거 조회, 문의 분류, 자동응답 판단, 답변 초안 생성, 검토 필요 여부 반환 |

## 기본 원칙

- AI는 백엔드가 제공한 문의 원문과 운영 데이터 맥락에 의존한다.
- AI는 백엔드 DB를 직접 조회하지 않는다.
- AI는 정책 문서를 자체적으로 관리한다.
- AI는 프론트엔드나 고객 채널을 직접 호출하지 않는다.
- AI는 고객에게 응답을 직접 전송하지 않는다.
- AI는 고객에게 추가 정보를 직접 요청하지 않는다.
- AI는 답변 초안과 최소한의 판단 메타데이터만 반환한다.
- 백엔드 제공 맥락 또는 AI 측 정책 근거가 부족하면 답변을 지어내지 않고 관리자 검토가 필요하다고 반환한다.

## Endpoint

```text
POST /api/inquiries/process
```

백엔드가 이미 저장한 문의와 필요한 운영 데이터 맥락을 AI에 전달하면,
AI가 문의를 분류하고 자동응답 가능 여부를 판단하며, 필요 시 정책 문서 기반 답변 초안을 생성해 반환하는 endpoint다.

> 기존 후보 URL `/api/v1/answers/draft`는 AGENTS.md 내부 규칙과 불일치하여 수정.
> `/v1` 접두사는 백엔드(AiInquiryClient) 호출 spec(`/api/inquiries/process`)에 맞춰 제거(2026-06-17).
> endpoint URL은 이 문서를 단일 출처로 한다.

## Request

모든 필드명은 camelCase를 사용한다. `context` 안의 사용자 정의 필드도 camelCase를 유지한다.

```json
{
  "inquiryId": "inq_001",
  "message": "제 주문 언제 오나요?",
  "context": {
    "orderStatus": "배송 중",
    "trackingNumber": "1234-5678"
  }
}
```

## Request 필드 설명

| 필드 | 설명 | 필수 여부 | 소유 주체 |
| --- | --- | --- | --- |
| `inquiryId` | 백엔드에 저장된 문의 고유 ID | 필수 | Backend |
| `message` | 백엔드가 저장한 고객 문의 원문. 최대 2,000자 | 필수 | Backend |
| `channel` | 유입 채널. `"kakao"` \| `"web"` \| `"mail"` (백엔드 `ChannelType` 정렬, 대문자 enum 수신 시 소문자 정규화) | 선택 | Backend |
| `context` | 답변 작성에 필요한 주문, 배송, 고객 상태 등 백엔드 제공 운영 데이터 맥락 | 선택 | Backend |

## Request에 넣지 않는 것

초기 AI 계약에서는 다음 정보를 필수로 요구하지 않는다.
필요한 경우 백엔드가 `context` 안에 포함해서 전달한다.

- `customerId`
- `orderId`
- `createdAt`
- 백엔드 내부 DB schema 필드
- 고객 개인정보 원문
- 응답 전송 대상 정보

정책 관련 정보는 백엔드가 넘기지 않는다. AI 파트가 자체적으로 관리한다.

- `policySummary`
- 정책 문서 원문
- 정책 문서 검색 결과
- RAG 검색 결과

## context 사용 방식

`context`는 백엔드가 AI에게 제공하는 운영 데이터 맥락이다.
정책 정보가 아니라 백엔드 DB 또는 백엔드 상태 관리에서 확인한 사실을 담는다.

예시:

```json
{
  "orderStatus": "배송 중",
  "trackingNumber": "1234-5678",
  "paymentStatus": "결제 완료"
}
```

초기에는 `context`의 세부 schema를 너무 빨리 확정하지 않는다.
먼저 백엔드가 어떤 운영 데이터를 안정적으로 제공할 수 있는지 확인한 뒤 세부 필드를 확정한다.

## AI 측 정책 문서 사용 방식

정책 문서는 AI 파트에서 관리한다.
초기 구현은 Markdown 정책 문서와 LlamaIndex 기반 검색으로 시작한다.

```text
AI/app/docs/policies/
  shipping.md
  exchange-refund.md
  product.md
  response-tone.md
```

초기 흐름은 다음과 같다.

```text
Markdown 정책 문서
-> LlamaIndex 문서 로딩/검색
-> Pydantic AI 답변 생성 agent
-> 답변 초안과 사용 근거 반환
```

`usedSources` 필드의 접두사 규칙:

| 접두사 | 의미 | 예시 |
| --- | --- | --- |
| `context.{필드명}` | 백엔드가 제공한 운영 데이터 맥락 필드 | `context.orderStatus` |
| `policy.{파일명}` | AI 파트 관리 Markdown 정책 문서 | `policy.shipping` |
| `faq.{문서ID}` | 후속 도입 예정인 FAQ 문서 (PoC에서는 미사용) | `faq.return-period-001` |

초기에는 별도 VectorDB를 필수로 두지 않는다.
문서 수가 늘어나고 검색 persistence나 metadata filter가 필요해지면 Chroma, Qdrant, pgvector 같은 저장소를 후속 검토한다.

## Response 구조

모든 응답은 `status / data / error` 래퍼 구조를 사용한다.
모든 필드명은 camelCase를 사용한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `status` | string | `"success"` \| `"needs_review"` \| `"error"` |
| `data` | object \| null | 처리 결과 본문. `status: "error"`일 때 `null` |
| `error` | object \| null | 오류 정보. `status: "error"`일 때만 채워짐. 정상 응답 시 `null` |

### HTTP 상태 코드 정책 (확정, 2026-06-20)

**AI는 `success`/`needs_review`/`error` 모든 응답을 HTTP `200 OK`로 반환한다.** 성공·실패 분기는 오직 body의 `status` 필드로만 한다. HTTP 상태 코드로 처리 결과를 분기하지 않는다.

근거 (백엔드 `hsa-server` 구현 대조):

- 백엔드 `AiInquiryClient`는 `RestTemplate.postForObject`를 사용하며, **non-2xx 응답에서 예외를 던진다.** `AiInquiryProcessingService.requestSafely`는 그 예외를 잡아 body를 읽지 않고 **무조건 `EXTERNAL_SYSTEM_ERROR`로 덮어쓴다.**
- 따라서 AI가 `error`를 5xx로 반환하면 body의 실제 `code`(예: 비재시도 `LLM_PARSE_FAILED`)가 소실되고, 백엔드가 이를 재시도 가능한 `EXTERNAL_SYSTEM_ERROR`로 오인해 **잘못된 재시도**를 한다(재시도 정책은 `AiInquiryRetryPolicy` 참조).
- `needs_review`는 근거 부족·복합 문의 등 **정상적인 업무 결과**이지 전송 실패가 아니므로 5xx 대상이 아니다.

> **5xx 전환은 협의된 v2 변경**: AI 장애를 HTTP 5xx로 노출(관측성/알람)하려면, 백엔드가 `ResponseErrorHandler`로 에러 body의 `code`를 파싱하도록 함께 변경해야 한다. AI 단독으로 코드를 바꾸지 않는다. 현재 백엔드→AI 경로는 ALB가 아니라 Cloud Map 직통이라 status code를 소비하는 인프라가 RestTemplate 외엔 없다.

### 성공 응답 예시

```json
{
  "status": "success",
  "data": {
    "inquiryId": "inq_001",
    "autoReplyAvailable": false,
    "draftAnswer": "고객님, 현재 주문은 배송 중이며 송장번호는 1234-5678입니다. 일반 배송은 결제 후 평균 2~3일 소요됩니다.",
    "needsAdminReview": false,
    "reason": "배송 상태와 AI 측 배송 정책 문서를 근거로 답변 초안을 작성했습니다.",
    "riskTags": [],
    "usedSources": ["context.orderStatus", "context.trackingNumber", "policy.shipping"]
  },
  "error": null
}
```

### 검토 필요 응답 예시

```json
{
  "status": "needs_review",
  "data": {
    "inquiryId": "inq_001",
    "autoReplyAvailable": false,
    "draftAnswer": null,
    "needsAdminReview": true,
    "reason": "[No_Context] 관련 정책 문서 없음 (검색어: 반품 기간)",
    "riskTags": [],
    "usedSources": []
  },
  "error": null
}
```

### 오류 응답 예시

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "LLM 호출 시간 초과"
  }
}
```

## Response data 필드 설명

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `inquiryId` | string | 원본 문의 ID |
| `autoReplyAvailable` | bool | 자동응답 즉시 발송 가능 여부. `true`이면 백엔드가 `draftAnswer`를 고객에게 즉시 발송한다 |
| `draftAnswer` | string \| null | 답변 내용. 자동응답 시 완성 문자열, RAG 초안 시 검토용 문자열, 근거 없음 시 `null` |
| `needsAdminReview` | bool | 관리자 검토 필요 여부 |
| `reason` | string | 답변 생성 또는 관리자 검토 판단 이유 |
| `riskTags` | string[] | 위험 태그. 현재 후보: `"refund"`, `"claim"`, `"policy_conflict"` |
| `usedSources` | string[] | 답변 초안에 사용한 context 키 또는 정책 문서 식별자 |

## `autoReplyAvailable`과 `draftAnswer` 관계

`autoReplyAvailable`은 AI 내부의 `AutoReplyDecision`을 외부에 노출하는 필드다.

| `autoReplyAvailable` | `draftAnswer` | 백엔드 처리 |
| --- | --- | --- |
| `true` | 완성된 응답 문자열 (템플릿에 context 값이 삽입된 상태) | 고객에게 즉시 발송 가능 |
| `false` | 초안 문자열 | 관리자 검토 후 발송 여부 판단 |
| `false` | `null` | 근거 없음. 관리자가 직접 답변 작성 필요 |

AI 내부 구현과의 매핑 (AGENTS.md "자동응답 책임 경계" 참조):

- `AutoReplyDecision.filled_answer` → `draftAnswer` (`autoReplyAvailable: true` 시)
- `RagDraftAnswer.answer` → `draftAnswer` (`autoReplyAvailable: false`, 초안 존재 시)
- 두 경우의 조립은 `process_inquiry` orchestrator가 담당한다.

## Response에서 제외하는 것

초기 AI 응답에서는 다음을 반환하지 않는다.

- 실제 고객 응답 전송 결과
- 백엔드 저장 성공 여부
- 프론트엔드 표시 상태
- 주문/배송 DB 조회 결과 원본
- 고객 개인정보

이유: 전송, 저장, 조회, 화면 표시는 백엔드 책임이다. AI 응답은 처리 결과에 집중한다.

## 관리자 검토가 필요한 경우

다음 경우에는 `needsAdminReview: true`로 반환한다.

| 조건 | `status` | 설명 |
| --- | --- | --- |
| RAG 근거 없음 (`usedSources` 빈 배열) | `needs_review` | 정책 문서 검색 결과 없음 또는 relevance threshold 미달 |
| 복합 문의 (분류 결과: `기타 문의`) | `needs_review` | 단일 유형으로 분류 불가 |
| `riskTags`에 `refund` 또는 `claim` 포함 | `success` 가능 | 환불·클레임 최종 판단은 관리자 권한 |
| `riskTags`에 `policy_conflict` 포함 | `success` 가능 | 정책 문서 간 내용 충돌 감지 |
| 백엔드 운영 데이터 맥락만으로 답변 불가 | `needs_review` | context 미제공 또는 불충분 |

> LLM 또는 외부 시스템 호출 실패는 `status: "error"`로 반환한다.  
> 기존 초안에서 이 경우를 `needs_admin_review: true`로 처리했으나, AGENTS.md 실패 처리 테이블과 통일하여 `"error"`로 수정한다.

## 오류 코드 (확정 필요)

| code | 설명 |
| --- | --- |
| `LLM_TIMEOUT` | LLM 호출 시간 초과 |
| `LLM_PARSE_FAILED` | LLM 출력 파싱·검증 실패 (2회 재시도 후 최종 실패) |
| `EXTERNAL_SYSTEM_ERROR` | 외부 시스템(LlamaIndex 등) 호출 실패 |

## 백엔드 inquiry 도메인 정합 합의 (Phase 0.3, 2026-06-17)

백엔드 `inquiry` 도메인 API spec(2026-06-17 수령)과 대조한 결과 확정한 결정.
기본 원칙: **백엔드 spec에 AI가 맞춘다** (백엔드가 AI를 호출하는 쪽).

### ① 자동응답 context 필드 — 백엔드 신규 필드 없이 정합 (확정)

백엔드 context는 `orderStatus`·`deliveryStatus`·`currentLocation`·`carrier`·`productName`·`trackingNumber`·`customerId`를 제공한다. 기존 AI 자동응답이 요구하던 `expectedDeliveryDate`·`matchedOrderCount`는 **백엔드 신규 필드로 요구하지 않고, AI 측 로직을 백엔드 제공 필드에 맞춰 재설계한다.**

- **자동응답(즉시 발송) = 배송 중 하드 사실만**: `deliveryStatus`가 배송 중인 경우, `carrier`·`trackingNumber`·`currentLocation`을 템플릿에 삽입해 즉시 발송한다. 영문 enum → 한글 표현 매핑은 **AI 측이** 관리하며, 백엔드 `deliveryStatus` 값에 정렬한다.
- **예상 도착일("언제 와요?") = RAG 초안**: 배송 소요일은 AI 정책 문서 지식(`policy.shipping`, 예: "결제 후 평균 2~3일")이므로 `autoReplyAvailable: false` 검토 초안으로 처리한다(본 문서 성공 응답 예시와 일치). 별도 `expectedDeliveryDate` 필드는 두지 않는다.
- **단일 주문 전제**: 백엔드는 inquiry당 단일 주문 context를 제공하므로, AI 측 `matchedOrderCount == 1` 안전핀은 **제거**한다. (다건 매칭 분기는 백엔드 책임)

### ② riskTags 어휘 — AI 검토 트리거 축으로 유지 (확정)

`riskTags`(`refund`·`claim`·`policy_conflict`)는 **AI의 관리자 검토 트리거 어휘**다. 백엔드 예시 `DELIVERY_DELAY`는 배송 상태 알림 축으로 의미가 다르며, 백엔드 status mapper는 riskTags를 소비하지 않는다(spec 7.4). → AI 어휘를 그대로 유지하고 혼용하지 않는다.

### ③ category — AI 내부 enum, 응답 미노출 (확정)

분류 `category`는 AI 내부 분류용 enum이며 응답 `data`에 노출하지 않는다. 백엔드 `InquiryResult.category`는 현재 소비처가 없어(`OTHER` 저장만) 노출은 추측성 확장이 된다. 백엔드가 실제 소비처(관리자 분류 필터 등)를 만들면 그때 `!BREAKING CHANGE`로 노출을 재검토한다.

## 아직 확정하지 않은 것

- `context`의 세부 schema
- 정책 문서 저장 방식
- VectorDB 도입 여부와 source 표기 형식
- 오류 코드 전체 목록
