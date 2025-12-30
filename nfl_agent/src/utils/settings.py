from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic import SecretStr, Field
from typing import TypeVar, Type
from functools import lru_cache

TypeSetting = TypeVar("TypeSetting", bound=PydanticBaseSettings)


class LLMSettings(PydanticBaseSettings):
    llm_model_name: str = "gpt-4.1-2025-04-14"
    temperature: float = 0.1

    llm_api_key: SecretStr = Field(..., exclude=True, validation_alias="OPENAI_API_KEY")

    model_config = {
        "extra": "ignore",
    }


class ArticleAnalyzerSettings(LLMSettings):
    max_iterations: int = 5
    max_execution_time: float = 60.0


@lru_cache
def get_setting(setting_class: Type[TypeSetting]) -> TypeSetting:
    """helper to cache the PydanticSettings classes"""
    return setting_class()
