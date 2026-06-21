# HSA AI

이 폴더는 HSA(Hanyang Support Agent) 프로젝트의 AI 서비스 코드와 기준 문서를 관리한다.

## 현재 포함 범위

- AI 파트 역할과 책임 범위 정리
- PoC 처리 흐름 기준 정리
- 프레임워크/아키텍처 결정 문서 정리
- 로컬 환경 변수 예시 파일
- 기본 ignore 규칙
- Python 프로젝트 메타데이터와 기본 의존성 설정

## 현재 구현 범위

- FastAPI `POST /api/inquiries/process`
- 문의 분류, 자동응답 판단, RAG 초안 생성 workflow
- Markdown 정책 문서와 LlamaIndex 인덱스
- 벡터 threshold 필터와 LLM reranker
- pytest 기반 단위 및 HTTP 계약 테스트

## 주요 문서

```text
docs/README.md
문서 목록과 각 문서의 역할

docs/project-overview.md
프로젝트 목적, AI 파트 책임, PoC 범위

docs/architecture.md
AI 파트 계층 구조와 의존성 방향

docs/api-contract.md
백엔드와 AI 파트 사이의 API 계약 초안

docs/framework-decision.md
AI 파트에서 사용할 프레임워크와 후속 검토 도구 정리

docs/policy-rag-strategy.md
정책 문서 사용 기준과 답변 생성 원칙

docs/development-guide.md
브랜치, 커밋, PR, secret 관리 규칙

docs/local-setup.md
로컬 환경 세팅과 실행 전 준비 사항
```

## 시스템 연결 방향

HSA 서비스의 기본 연결 방향은 다음과 같다.

```text
Frontend <-> Backend <-> AI
```

AI 파트는 프론트엔드와 직접 통신하지 않는다.
고객 응답 전송, 관리자 화면, 문의 채널 연동, DB 조회와 저장은 모두 백엔드를 통해 처리한다. 정책 문서와 답변 생성 지식은 AI 파트에서 관리한다.

## AI 파트의 역할

AI 파트는 고객에게 직접 응답을 전송하는 시스템이 아니라, 백엔드가 사용할 문의 답변 보조 결과를 생성하는 역할을 가진다.

초기 PoC에서 AI 파트가 담당하는 책임은 다음으로 제한한다.

1. 백엔드가 전달한 문의와 운영 데이터 맥락 기반 답변 초안 생성
2. AI 파트가 관리하는 Markdown 정책 문서와 LlamaIndex 검색 결과 활용
3. 답변 생성에 사용한 근거 또는 이유 반환
4. 관리자 검토 필요 여부 판단
5. 위험 태그와 처리 상태 같은 최소 메타데이터 반환

AI 파트가 직접 담당하지 않는 책임은 다음과 같다.

- 프론트엔드와 직접 통신
- 문의 채널 연동과 원문 수집
- 문의 저장과 상태 관리
- 관리자 화면 구현
- 고객 응답 실제 전송
- 주문/배송 DB 조회 또는 직접 소유
- 백엔드 DB schema 최종 확정
- 배포 인프라 최종 확정

## 초기 PoC 방향

초기 PoC 아키텍처는 `Lightweight Layered Architecture`로 진행한다.

하나의 FastAPI 서비스 안에서 `api / schemas / workflow / services / boundaries` 계층만 가볍게 나누고, Microservice나 multi-agent 구조는 나중에 필요가 생기면 검토한다.

초기 PoC는 무거운 multi-agent framework를 먼저 붙이는 방식이 아니라, FastAPI, Pydantic AI, Pydantic v2, LlamaIndex를 중심으로 작게 시작한다.

현재 구현은 책임 경계, 프레임워크 선택, API 계약 문서를 기준으로 유지한다.

## 다음 단계에서 정할 것

- 백엔드와 주고받을 request/response schema
- 답변 초안 반환 형식
- 관리자 검토 필요 조건
- 정책 문서 세부 내용과 source 표기 방식
- VectorDB 도입 여부
- evaluation sample 기준
- 실제 구현 시작 시 사용할 패키지 관리 방식
