# 정책 문서 사용 기준

상태: decision

## 목적

이 문서는 HSA AI 파트가 정책 문서를 답변 생성에 어떻게 사용할지 간단히 정리한다.

## 기본 방향

초기 PoC에서는 정책 문서를 Markdown으로 관리하고, 필요한 문서 내용을 검색해 답변 생성에 사용한다.

```text
Markdown 정책 문서
-> 문서 검색
-> 벡터 유사도 threshold 필터
-> LLM reranker로 근거 재정렬
-> Pydantic AI 답변 생성
-> 구조화된 결과 반환
```

## 왜 LlamaIndex를 사용하는가

정책 문서를 직접 검색하도록 구현하면 문서 로딩, 분리, 검색, 출처 관리 코드를 직접 만들어야 한다.
초기 PoC에서는 이 부분에 시간을 많이 쓰기보다, 문서 기반 답변 흐름을 빠르게 검증하는 것이 더 중요하다.

LlamaIndex는 Markdown 문서를 읽고 관련 내용을 찾는 기본 기능을 제공하므로, HSA AI는 답변 생성 로직과 백엔드 계약에 더 집중할 수 있다.

## 역할 분리

| 영역 | 역할 |
| --- | --- |
| Backend | 문의 저장, 주문/배송 등 운영 데이터 조회, AI 호출, 응답 전송 |
| AI | 정책 문서 관리, 관련 근거 검색, 답변 초안 생성, 검토 필요 여부 반환 |
| LlamaIndex | Markdown 정책 문서 검색 |
| Pydantic AI | 검색된 근거와 백엔드 context를 바탕으로 답변 생성 |
| Pydantic v2 | 요청/응답 데이터와 결과 형식 검증 |

## 답변 생성 원칙

- 정책 문서에 없는 내용을 확정적으로 말하지 않는다.
- 백엔드 context에 없는 주문, 배송, 고객 상태를 추측하지 않는다.
- 교환, 환불, 클레임, 정책 충돌 문의는 관리자 검토 필요로 표시한다.
- 답변에 사용한 정책 문서 또는 context 출처를 반환한다.
- 근거가 부족하면 답변을 지어내지 않고 검토 필요 사유를 반환한다.

## 현재 결정

초기에는 복잡한 RAG 인프라보다 다음 흐름을 우선한다.

```text
Backend가 문의와 context 전달
-> AI가 정책 문서 근거 확인
-> LLM reranker가 답변에 사용할 근거 선택
-> Pydantic AI가 답변 초안 생성
-> Backend에 답변 초안과 판단 메타데이터 반환
```

## Reranker 초기 설정

PoC 검색 품질 개선을 위해 벡터 검색 뒤에 LlamaIndex `LLMRerank`를 사용한다.
복합 문의는 분류 단계에서 관리자 검토로 전환하므로, RAG 답변 생성에는 rerank 1위 정책 파일과
같은 source의 chunk만 사용한다. 이를 통해 서로 다른 정책의 조건부 규칙이 섞이는 것을 막는다.

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `RAG_RELEVANCE_THRESHOLD` | `0.4` | 벡터 후보 relevance threshold |
| `RAG_TOP_K` | `6` | 벡터 검색 후보 수 |
| `RAG_RERANK_TOP_N` | `3` | reranker 최종 선택 수 |
| `RAG_RERANK_MODEL` | `gpt-5-nano` | OpenAI reranker 모델 |

초기 측정값과 품질 관리 담당자 인계 기준은 `rag-quality-handoff.md`를 따른다.
