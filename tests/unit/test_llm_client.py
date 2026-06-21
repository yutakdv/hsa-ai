"""
llm_client boundary 단위 테스트.

목표:
- 서비스 계층은 schema를 인자로 넘겨 구조화된 LLM 출력을 요청한다.
- llm_client는 프로젝트에서 정한 Pydantic AI만 사용해 structured output을 반환한다.
- 단위 테스트에서는 실제 LLM provider를 호출하지 않는다.
"""

from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError

from app.boundaries import llm_client


class SampleOutput(BaseModel):
    label: str
    score: float


class FakeRunResult:
    def __init__(self, output: Any) -> None:
        self.output = output


class FakeAgent:
    created_with: dict[str, Any] = {}
    run_prompt: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.__class__.created_with = {"args": args, "kwargs": kwargs}

    def run_sync(self, prompt: str) -> FakeRunResult:
        self.__class__.run_prompt = prompt
        return FakeRunResult({"label": "ok", "score": 0.95})


def test_generate_structured_returns_validated_schema_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "Agent", FakeAgent, raising=False)

    result = llm_client.generate_structured(
        prompt="분류 결과를 반환해줘.",
        output_schema=SampleOutput,
        model="test-model",
        system_prompt="Return structured data only.",
    )

    assert result == SampleOutput(label="ok", score=0.95)
    assert FakeAgent.created_with["kwargs"]["output_type"] is SampleOutput
    assert FakeAgent.created_with["kwargs"]["model"] == "test-model"
    assert FakeAgent.created_with["kwargs"]["system_prompt"] == "Return structured data only."
    assert FakeAgent.run_prompt == "분류 결과를 반환해줘."


def test_generate_structured_rejects_invalid_schema_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidOutputAgent(FakeAgent):
        def run_sync(self, prompt: str) -> FakeRunResult:
            return FakeRunResult({"label": "ok", "score": "not-a-float"})

    monkeypatch.setattr(llm_client, "Agent", InvalidOutputAgent, raising=False)

    with pytest.raises(ValidationError):
        llm_client.generate_structured(
            prompt="잘못된 구조를 반환하는 fake 호출",
            output_schema=SampleOutput,
            model="test-model",
        )


def test_generate_structured_appends_strict_directive_when_contextvar_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STRICT_OUTPUT_FORMAT가 True면 AGENTS.md 계약 문구 전체가 system_prompt 끝에 붙는다."""
    monkeypatch.setattr(llm_client, "Agent", FakeAgent, raising=False)
    token = llm_client.STRICT_OUTPUT_FORMAT.set(True)
    try:
        llm_client.generate_structured(
            prompt="분류 결과를 반환해줘.",
            output_schema=SampleOutput,
            model="test-model",
            system_prompt="Return structured data only.",
        )
    finally:
        llm_client.STRICT_OUTPUT_FORMAT.reset(token)

    final_system_prompt = FakeAgent.created_with["kwargs"]["system_prompt"]
    assert final_system_prompt == (
        "Return structured data only. Return JSON only. No prose, no markdown fences."
    )


def test_generate_structured_omits_strict_directive_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STRICT_OUTPUT_FORMAT가 기본값(False)이면 강제 지시어를 덧붙이지 않는다."""
    monkeypatch.setattr(llm_client, "Agent", FakeAgent, raising=False)

    llm_client.generate_structured(
        prompt="분류 결과를 반환해줘.",
        output_schema=SampleOutput,
        model="test-model",
        system_prompt="Return structured data only.",
    )

    assert (
        FakeAgent.created_with["kwargs"]["system_prompt"]
        == "Return structured data only."
    )


def test_generate_structured_requires_pydantic_model_schema() -> None:
    with pytest.raises(TypeError):
        llm_client.generate_structured(
            prompt="plain dict는 출력 schema로 허용하지 않는다.",
            output_schema=cast(Any, dict),
            model="test-model",
        )
