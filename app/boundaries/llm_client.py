"""
LLM client boundary.

서비스 계층은 이 boundary에 prompt와 Pydantic output schema를 넘긴다.
이 파일은 프로젝트에서 정한 Pydantic AI 호출 방식만 소유하고,
문의 분류/자동응답/RAG 같은 도메인 규칙은 소유하지 않는다.
"""

import os
from collections.abc import Sequence
from contextvars import ContextVar
from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent

OutputModelT = TypeVar("OutputModelT", bound=BaseModel)

DEFAULT_MODEL_ENV = "HSA_LLM_MODEL"
DEFAULT_MODEL = "openai:gpt-5-nano"
DEFAULT_SYSTEM_PROMPT = (
    "Return only data that satisfies the requested structured output schema. "
    "Do not include markdown fences or extra prose."
)
# orchestrator 2차 재시도 시 True로 설정. AGENTS.md "2차 실패: 출력 형식 강제 지시 추가" 충족용.
STRICT_OUTPUT_FORMAT: ContextVar[bool] = ContextVar("strict_output_format", default=False)
_STRICT_FORMAT_DIRECTIVE = "Return JSON only. No prose, no markdown fences."


def _resolve_model(model: str | None) -> str:
    """명시 model > 환경변수 > 기본 모델 순서로 사용할 모델 이름을 결정한다."""
    return model or os.getenv(DEFAULT_MODEL_ENV) or DEFAULT_MODEL


def generate_structured(
    prompt: str,
    output_schema: type[OutputModelT],
    *,
    model: str | None = None,
    system_prompt: str | Sequence[str] | None = None,
    retries: int = 2,
    output_retries: int = 2,
) -> OutputModelT:
    """
    Pydantic AI로 LLM을 호출하고 output_schema 타입의 구조화 결과를 반환한다.

    Args:
        prompt: LLM에 전달할 사용자 프롬프트.
        output_schema: 반환받을 Pydantic 모델 클래스.
        model: 사용할 Pydantic AI 모델명. 없으면 HSA_LLM_MODEL 또는 기본값 사용.
        system_prompt: 공통 시스템 프롬프트. 없으면 structured output 전용 기본값 사용.
        retries: Pydantic AI agent 실행 재시도 횟수.
        output_retries: 구조화 출력 검증 재시도 횟수.

    Returns:
        output_schema 인스턴스.

    Raises:
        TypeError: output_schema가 Pydantic BaseModel 하위 클래스가 아닌 경우.
        ValueError: prompt가 비어 있는 경우.
        pydantic.ValidationError: LLM 출력이 output_schema 검증을 통과하지 못한 경우.
        pydantic_ai 예외: provider 호출 실패, timeout 등 외부 호출 실패.
    """
    if not isinstance(output_schema, type) or not issubclass(output_schema, BaseModel):
        raise TypeError("output_schema must be a Pydantic BaseModel subclass")

    if not prompt.strip():
        raise ValueError("prompt must not be empty")

    resolved_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    if STRICT_OUTPUT_FORMAT.get():
        if isinstance(resolved_system_prompt, str):
            resolved_system_prompt = f"{resolved_system_prompt} {_STRICT_FORMAT_DIRECTIVE}"
        else:
            resolved_system_prompt = [*resolved_system_prompt, _STRICT_FORMAT_DIRECTIVE]

    agent: Agent[None, OutputModelT] = Agent(
        model=_resolve_model(model),
        output_type=output_schema,
        system_prompt=resolved_system_prompt,
        retries=retries,
        output_retries=output_retries,
    )
    result = agent.run_sync(prompt)

    output = result.output
    if isinstance(output, output_schema):
        return output

    return output_schema.model_validate(output)
