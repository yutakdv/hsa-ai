# 프레임워크 결정 문서

상태: decision

## 목적

이 문서는 HSA AI 파트에서 사용할 주요 프레임워크와 도구를 간단히 정리한다.

세부 schema, endpoint, 함수명, 평가 샘플 수는 이 문서에서 다루지 않는다.
그 내용은 API 계약 문서나 구현 단계에서 별도로 정한다.

## 최종 선택

초기 AI 파트는 다음 조합으로 시작한다.

```text
Python 3.10+
FastAPI
Pydantic AI
Pydantic v2
LlamaIndex
pytest
```

## Python 3.10+

AI 서비스 구현 언어로 Python을 사용한다.

선택 이유:

- AI/LLM 관련 라이브러리 생태계가 좋다.
- FastAPI, Pydantic AI, pytest와 잘 맞는다.
- 팀원이 빠르게 이해하고 구현하기 쉽다.

## FastAPI

Backend가 AI 서비스를 호출할 HTTP API 서버로 사용한다.

FastAPI의 역할:

- Backend 요청 수신
- request/response validation 연결
- API 문서 제공
- 내부 AI workflow 호출
- 결과 반환

FastAPI route 안에서 직접 LLM 호출이나 복잡한 답변 생성 로직을 구현하지 않는다.

## Pydantic AI

AI 답변 생성을 위한 중심 프레임워크로 사용한다.

Pydantic AI의 역할:

- LLM agent 구성
- model/provider 연결
- dependency 주입
- structured output 생성
- 테스트 가능한 agent 경계 제공

이 프로젝트에서는 단순히 `pydantic`만 쓰는 것이 아니라, Pydantic 팀에서 제공하는 `pydantic_ai`를 AI workflow의 중심 도구로 사용한다.

## Pydantic v2

데이터 검증과 구조화된 결과 표현에 사용한다.

Pydantic v2의 역할:

- Backend-AI 요청/응답 데이터 검증
- Pydantic AI 결과 구조화
- FastAPI request/response model과 연계
- 테스트와 평가 데이터 검증

## LlamaIndex

정책 문서 검색과 RAG 구현 부담을 줄이기 위해 사용한다.

LlamaIndex의 역할:

- Markdown 정책 문서 로딩
- 문서 chunking과 indexing
- 문의와 관련된 정책 문서 조각 검색
- LLM reranker를 통한 근거 후보 재정렬
- 답변 생성에 사용할 source/citation 후보 제공

이 프로젝트에서 RAG를 처음부터 직접 구현하지 않는다.
초기에는 Markdown 정책 문서와 LlamaIndex 기반 검색으로 시작하고, Pydantic AI는 검색된 근거를 사용해 답변 초안과 구조화된 결과를 생성한다.

## pytest

테스트 도구로 사용한다.

pytest의 역할:

- service/workflow 단위 테스트
- Pydantic AI agent 결과 검증
- mock/fake model 기반 테스트
- 회귀 테스트

## 후속 검토 도구

다음 도구들은 초기 필수 도구가 아니라, 필요가 생기면 검토한다.

| 도구 | 상태 | 검토 조건 |
| --- | --- | --- |
| LangGraph / LangChain | 보류 | Pydantic AI와 순수 Python workflow만으로 흐름 관리가 어려워질 때 |
| Chroma / Qdrant / pgvector | 보류 | 정책 문서가 많아지고 별도 VectorDB, metadata filter, 검색 persistence가 필요할 때 |
| Docker Compose | 보류 | 로컬에서 여러 서비스를 함께 실행해야 할 때 |
| GitHub Actions | 보류 | 테스트/평가 자동화가 필요할 때 |
| OpenAI Agents SDK / Google ADK | 보류 | multi-agent 구조가 실제로 필요할 때 |
| MCP | 보류 | 여러 외부 tool/resource를 표준 방식으로 연결해야 할 때 |

## 현재 기준

현재는 무거운 multi-agent framework를 먼저 도입하지 않는다.

초기 방향은 다음과 같다.

```text
FastAPI API 경계
-> Pydantic v2 데이터 검증
-> LlamaIndex 정책 문서 검색
-> Pydantic AI 답변 생성 agent
-> pytest 기반 테스트
```

이 조합은 HSA AI가 “고객에게 직접 응답하는 자동화 시스템”이 아니라 “Backend가 사용할 답변 초안 생성 서비스”라는 현재 책임 범위에 맞다.
