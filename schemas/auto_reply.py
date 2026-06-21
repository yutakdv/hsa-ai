"""
schemas/auto_reply.py

자동응답 가능 여부와 채워진 응답 본문을 담는 모델.
decide_auto_reply 함수의 반환 타입.

자동응답 책임 경계 (harness/AGENTS.md 참조):
- AI: 자동응답 가능 여부 판단 + 템플릿에 context 값 삽입까지 수행
- 백엔드: 채워진 응답을 받아 고객 채널로 전송
"""

from pydantic import Field, model_validator

from schemas.base import BaseHsaModel
from schemas.process_result import RiskTag


class AutoReplyDecision(BaseHsaModel):
    """
    자동응답 판단 결과.

    available=True인 경우에만 filled_answer가 채워진다.
    LLM이 자유 문장으로 생성하지 않고, 사전에 정의된 템플릿에
    context 값을 삽입하는 방식으로 작성한다.
    """

    available: bool = Field(..., description="자동응답 가능 여부")
    filled_answer: str | None = Field(
        default=None,
        description="템플릿에 context 값을 삽입한 자동응답. available=True일 때만 채움",
    )
    reason: str = Field(..., min_length=1, description="자동응답 가능/불가 판단 근거")
    risk_tags: list[RiskTag] = Field(
        default_factory=list,
        description="위험 태그 목록. available=False일 때 감지된 태그를 담는다.",
    )

    @model_validator(mode="after")
    def _check_filled_answer_consistency(self) -> "AutoReplyDecision":
        """available=True면 filled_answer가 반드시 있어야 하고, False면 None이어야 한다."""
        if self.available and not self.filled_answer:
            raise ValueError(
                "available=True 인 경우 filled_answer가 반드시 채워져야 합니다."
            )
        if not self.available and self.filled_answer is not None:
            raise ValueError(
                "available=False 인 경우 filled_answer는 None이어야 합니다."
            )
        return self
