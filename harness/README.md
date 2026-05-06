# HSA Project: AI Harness & Governance

이 폴더는 HSA(Hanyang Support Agent) 프로젝트의 **AI 품질 보증 및 협업 규약**을 관리합니다. 모든 개발자와 AI 에이전트는 코드 작성 및 수정 시 이 가이드라인을 최우선으로 준수해야 합니다.

## 도입 목적 (Harness Objective)
- **인터페이스 계약 준수:** Pydantic 모델 기반의 데이터 정합성을 강제하여 백엔드-AI 간 충돌을 방지합니다.
- **일관된 판단 로직:** AI 도구(Claude/Codex)에 상관없이 동일한 분류 및 응답 기준을 유지합니다.
- **신뢰 기반 자동화:** 근거가 불충분한 경우 무리하게 답변하지 않고 `needs_review`로 넘기는 Fail-Safe 체계를 구축합니다.

---

## 📂 프로젝트 구조 예시 및 Harness 역할
현 레포지토리의 주요 구조와 `harness/` 가이드라인이 적용되는 범위입니다.

```text
root/
├── harness/                # AI Governance & Guides
│   ├── README.md           # 폴더 개요 및 로딩 순서
│   ├── AGENTS.md           # 공통 실행 흐름 및 실패 처리 규칙
│   ├── CLAUDE.md           # Claude 전용 사고 방식 지침
│   └── CODEX.md            # Codex 전용 작업 규정
├── docs/
│   ├── api-contract.md     # AI 처리 로직 및 출력 형식 상세 정의 
│   └── ...
├── schemas/                # Pydantic 데이터 모델
│   ├── classification.py   # 문의 분류 결과 모델
│   ├── auto_reply.py       # 자동응답 결정 모델
│   └── ...
└── evals/                  # 성능 평가 및 데이터셋
    ├── tasks.json          # 평가용 골든 데이터셋 (Test Cases)
    ├── runner.py           # 테스트 실행 엔진
    ├── grader.py           # 응답 채점 로직
    ├── report.py           # 최종 리포트 생성 모듈
    └── main.py             # 전체 평가 프로세스 통합 실행 및 지표 측정
