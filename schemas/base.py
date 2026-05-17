"""
schemas/base.py

HSA 프로젝트의 모든 Pydantic 모델이 상속하는 기반 클래스.
내부 snake_case 필드를 외부 JSON에서 camelCase로 자동 변환한다.

"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseHsaModel(BaseModel):
    """
    모든 HSA 스키마의 공통 기반.

    - alias_generator=to_camel: 직렬화 시 snake_case -> camelCase 자동 매핑
    - populate_by_name=True:    역직렬화 시 snake_case 키와 camelCase 키 모두 허용
    - from_attributes=True:     ORM 등 객체 속성으로부터 생성 가능
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
