# Workflow 담당자 인계 문서

상태: handoff

## 목적

RAG reranker 도입에 따라 workflow와 배포 설정에서 반영해야 할 작업을 정리한다.
RAG public interface는 변경되지 않았다.

```python
def generate_rag_draft(
    inquiry: CustomerInquiry,
) -> tuple[RagDraftAnswer | None, list[RiskTag]]:
    ...
```

## 필수 작업

| 우선순위 | 작업 | 권장 기준 |
| --- | --- | --- |
| P1 | BE → AI HTTP timeout 합의 | 초기값 `60s` 권장 |
| P1 | ECS 환경변수 반영 | `RAG_TOP_K=6`, `RAG_RERANK_TOP_N=3`, `RAG_RERANK_MODEL=gpt-5-nano` |
| P1 | RDS 책임 경계 문서 갱신 | AI ECS가 private subnet RDS에 read-only로 접근하는 팀 결정 반영 |
| P2 | `usedSources` 소유권 문서 정리 | RAG boundary가 실제 검색 source를 계산하고 workflow가 외부 응답으로 집약 |
| P2 | RAG `None` 경로 유지 | 검색 근거 없음 또는 reranker 선택 없음 → `needs_review` |
| P2 | 오류 매핑 확인 | embedding, reranker, 답변 생성 provider 실패 → `EXTERNAL_SYSTEM_ERROR` 또는 합의한 세부 코드 |

## Timeout 권장값

2026-05-31 반복 라이브 측정에서 검색 + rerank 최대 지연은 `18.88s`였다.
답변 생성까지 포함한 RAG boundary 최대 관측 지연은 `28.66s`였다.
이 값에는 workflow의 분류 LLM 시간이 포함되지 않는다.

초기 운영값:

| 항목 | 권장값 | 이유 |
| --- | --- | --- |
| BE → AI 전체 요청 timeout | `60s` | RAG boundary 최대 `28.66s`에 분류, 네트워크 변동 여유 포함 |
| 모니터링 경고 기준 | `30s` | 정상 요청 지연 증가를 timeout 전에 감지 |
| 재조정 시점 | 운영 요청 `p95`, `p99` 수집 후 | `p99 + 20%`를 기준으로 timeout 재검토 |

timeout이 지나치게 길면 BE 재시도가 늦어지고, 지나치게 짧으면 정상 RAG 요청이 실패한다.
초기에는 `60s`로 시작하고 운영 로그를 기반으로 조정한다.

## RDS 문서 갱신 대상

현재 아래 문서는 여전히 Backend가 주문/배송 DB 조회를 담당한다고 설명한다.
팀 결정에 맞게 AI ECS의 read-only RDS 접근을 반영한다.

- `docs/api-contract-v2.md`
- `docs/project-overview.md`
- `docs/policy-rag-strategy.md`
- `docs/development-guide.md`

실제 SQL 구현은 DB schema와 읽기 전용 계정 확정 후 별도 이슈로 진행한다.

## Workflow 검증 체크리스트

- [ ] RAG가 `None`을 반환하면 `status="needs_review"`와 `[No_Context]` reason을 반환한다.
- [ ] RAG 성공 시 `RagDraftAnswer.used_sources`가 외부 `usedSources`에 포함된다.
- [ ] reranker provider 실패가 성공 응답으로 처리되지 않는다.
- [ ] BE timeout `60s` 설정과 ECS 환경변수 반영 여부를 확인한다.
