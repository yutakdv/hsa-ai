# RAG rerank latency 최적화 — 비교 보고서 (Phase 4)

상태: review (병합 승인 대기)
작성: 2026-06-18
브랜치: `feat/rag-rerank-latency` (base `feat/rag-quality-improvement`)
측정 로그: `/tmp/ab_results.log` (corrected run), `/tmp/ab_results_purevector.log` (초기 오설정 run)

---

## 1. 배경·목표

RAG 경로 지연의 41~44%(8~16s)가 **LLM(reasoning 모델)으로 재정렬(rerank)** 하는 비용에서 발생.
목표는 **검색 정확도(RAG 근거 일치율)는 유지**하면서 rerank 지연을 줄이는 것. 실제 제약은 BE→AI **timeout 60s**, eval `p95<30s`는 보수적 경고선.

수용 기준: **RAG 근거 일치율 ≥ 90% 유지** AND **latency 하락**, 자동응답·Pydantic 회귀 없음.

---

## 2. 평가 셋

골든 케이스를 **10 → 25개로 확장**(`evals/tasks.json`)해 RAG 적합성을 충분히 판단할 수 있게 함.
- 배송(shipping) RAG 6, 교환/환불(exchange-refund) RAG 6, 상품(product) RAG 5
- 무관(unrelated) 3, injection 3 (순수 차단 1 + 정상+injection 혼합 2)
- 자동응답(auto-reply) 2 + decide 1 (기존)

각 설정 **3회 반복**(LLM 비결정성 대응). 동일 25셋.

---

## 3. 후보 접근

| 접근 | 내용 | 의존성 |
|---|---|---|
| **baseline** | 현행. 모든 RAG 케이스를 LLM(gpt-5-nano)으로 rerank | 없음 |
| **(B) reasoning 낮추기** | rerank LLM의 `reasoning_effort`를 minimal/low로 | 없음 |
| **(C) 조건부 rerank** | 벡터 score에서 단일 정책이 마진(0.05)↑ 압도 시 rerank skip, 경합 시에만 LLM rerank | 없음 |
| **(A) cross-encoder** | LLMRerank → `SentenceTransformerRerank`(`BAAI/bge-reranker-v2-m3`) 로컬 추론 | torch+sentence-transformers (~2GB+), 모델 ~2.3GB |

---

## 4. 측정 결과

### 4.1 (B) reasoning 낮추기 — 기각 (초기 10셋 측정)

| 설정 | RAG 근거 일치율 | p95 |
|---|---|---|
| baseline(default) | 90% | 33.1s |
| minimal | **76.7%** ❌ | 20.2s |
| low | **86.7%** ❌ | 29.5s |

reasoning을 낮추면 reranker가 엉뚱한 정책을 골라(예: 환불 케이스가 정책 누락) 정확도가 90% 아래로. **정확도↔reasoning 트레이드오프로 기각**, 코드 revert 완료.

### 4.2 baseline vs (C) vs (A) — 확장 25셋, 각 3회

| 설정 | RAG 근거 일치율 | 자동응답 | Pydantic | **p95 (avg)** | **RAG-경로 평균** | 전체 평균 | 케이스 |
|---|---|---|---|---|---|---|---|
| **baseline** (항상 LLM rerank) | **100%** (3회) | 100% | 100% | **35.8s** ❌ | 29.1s | 24.3s | 25/25 |
| **(C)** (LLM + 조건부 skip) | **100%** (3회) | 100% | 100% | **23.7s** ✅ | 19.0s | 16.4s | 25/25 |
| **(A)** (cross-encoder) | **100%** (3회) | 100% | 100% | **22.7s** ✅ | 19.1s | 16.3s | 25/25 |

- **세 설정 모두 정확도 100%·25/25 통과.** 차이는 오직 latency.
- **baseline은 항상 rerank → p95 35.8s로 30s gate 초과**(60s timeout 내이긴 함).
- **(C)·(A) 모두 RAG-경로 평균 ~19s (baseline 29.1s 대비 −34%), p95 ~23s로 gate 통과.**
- **(C)와 (A)는 latency 사실상 동률** (RAG-경로 19.0 vs 19.1s, p95 23.7 vs 22.7s — A가 1s 우위, 노이즈 범위).

---

## 5. 부수 발견 (확장 셋 덕분에 포착)

1. **`_detect_policy_conflict` 오탐 (pure-vector 경로)**: rerank를 전혀 안 하면(초기 오설정) product 질의에서 shipping과 벡터 score가 근소차(예: shipping 0.424 vs product 0.413)로 1·2위 distinct source가 되어 `policy_conflict`가 **오탐**, riskTags에 잘못 추가됨 → 정확도 96%로 하락. **rerank(baseline/C/A)는 같은 source를 상위로 묶어 오탐을 없앤다** → 100%. 즉 rerank는 latency 비용뿐 아니라 **충돌 오탐 억제** 역할도 함. (단일 정책 압도 케이스는 (C)가 skip해도 안전 — 마진이 커서 오탐 없음.)
2. **skip 노브 의미**: `RAG_RERANK_SKIP_MARGIN <= 0` = 조건부 skip 비활성화(**항상 rerank**, baseline 동작). 0.05 = 기본(경합 시에만 rerank). 초기 측정에서 이 의미를 반대로 설정해 baseline/A가 사실상 pure-vector로 측정됐던 것을 발견·수정 후 재측정함.

---

## 6. (A) cross-encoder 채택 시 비용 (latency 이득이 동률이라 비용이 결정 요인)

- **무거운 의존성**: `torch`(수백 MB~2GB) + `sentence-transformers` + bge-reranker-v2-m3 모델 **~2.3GB** → Docker 이미지·배포 artifact 급증.
- **콜드스타트/다운로드**: 첫 사용 시 HF에서 모델 ~2GB 다운로드. ECS는 이미지에 굽거나(거대 이미지) 시작 시 다운로드(느린 콜드스타트+네트워크 의존).
- **메모리**: 568M cross-encoder resident ~1.5~2.5GB RAM → ECS task 메모리 상향.
- **CI**: GitHub Actions eval이 모델 다운로드 필요(캐시 구성 필요).
- score 스케일: cross-encoder는 sigmoid [0,1] 출력. `CONFLICT_SCORE_EPSILON=0.05`는 6케이스·25셋 회귀에서 오탐 없음 확인(재보정 불필요).

---

## 7. 권장안 — **(C) 조건부 rerank 채택**

(C)와 (A)는 **정확도(100%)·latency(~34% 단축) 모두 동률**이다. 그렇다면 **의존성 비용이 0인 (C)가 우월**하다(Simplicity First):
- (C): 코드 한 함수(`_single_policy_dominates`) + 조건 분기. 신규 의존성·모델·메모리·콜드스타트·CI 부담 **전혀 없음**. 결정적 skip 휴리스틱. 어려운(경합) 케이스는 기존 LLMRerank 품질 그대로.
- (A): 동일 이득에 ~2GB+ 의존성·메모리·콜드스타트·CI 비용. **이득 대비 비용 불균형.**

> (A+C 결합도 가능하나, (C) 단독으로 목표를 이미 달성하므로 불필요.)

### 병합 시 반영
- 기본값 유지: `RAG_RERANK_SKIP_MARGIN=0.05`(조건부), `RAG_RERANK_BACKEND=llm`.
- **cross-encoder 백엔드 코드 처리(승인 시 결정 필요)**: 현재 env-gated + lazy import로 dormant 상태. (a) Simplicity 위해 제거 / (b) 실험 옵션으로 유지 중 택1. 권장은 (a) 제거(미채택 접근).
- ECS 환경변수 권장: 별도 추가 없음(기본값으로 (C) 동작).

---

## 8. 회귀·검증 요약

- 단위 테스트 **19 passed** (`tests/unit/test_policy_retriever.py`): `_single_policy_dominates`(단일/마진/경합/비활성화) + 조건부 skip 경로 + 기존 conflict/전파 테스트.
- `check_retriever.py` **6/6** (LLM·cross-encoder 백엔드 모두), 전 케이스 `policy_conflict=False`.
- eval 25셋: baseline/C/A 각 3회 전부 25/25 통과, 정확도 100%.
- 변경은 **RAG 초안 경로에만** 영향(자동응답 경로 불변, eval 100% 유지).
