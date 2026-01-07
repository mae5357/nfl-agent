from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic import SecretStr, Field
from typing import TypeVar, Type
from functools import lru_cache
import time
import threading


TypeSetting = TypeVar("TypeSetting", bound=PydanticBaseSettings)


class LLMSettings(PydanticBaseSettings):
    llm_model_name: str = "gpt-4.1-2025-04-14"
    temperature: float = 0.1

    llm_api_key: SecretStr = Field(..., exclude=True, validation_alias="OPENAI_API_KEY")

    model_config = {
        "extra": "ignore",
    }


class ArticleRelevanceSettings(LLMSettings): ...


class ArticleAnalyzerSettings(LLMSettings):
    max_iterations: int = 5
    max_execution_time: float = 60.0


class NFLAgentSettings(LLMSettings):
    max_iterations: int = 5
    max_execution_time: float = 60.0


class RateLimitSettings(PydanticBaseSettings):
    """Settings for rate limiting OpenAI API calls."""

    # Minimum delay between API calls in seconds
    # 2 seconds helps stay under 30k TPM limit with typical article requests (~3k tokens each)
    min_request_interval: float = 2.0
    # Maximum retries for rate limit errors
    max_retries: int = 5

    model_config = {
        "extra": "ignore",
    }


class RateLimiter:
    """Thread-safe rate limiter for API calls."""

    def __init__(self, min_interval: float = 0.5):
        self._min_interval = min_interval
        self._last_request_time = 0.0
        self._lock = threading.Lock()

    def wait(self):
        """Wait if necessary to respect rate limits."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                sleep_time = self._min_interval - elapsed
                time.sleep(sleep_time)
            self._last_request_time = time.time()


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_setting(RateLimitSettings)
        _rate_limiter = RateLimiter(min_interval=settings.min_request_interval)
    return _rate_limiter


def get_chat_model(settings: LLMSettings | None = None):
    """
    Create a ChatOpenAI instance with rate limiting and retry configuration.

    Args:
        settings: LLMSettings instance. If None, uses default LLMSettings.

    Returns:
        ChatOpenAI instance configured with rate limiting.
    """
    from langchain_openai import ChatOpenAI

    if settings is None:
        settings = get_setting(LLMSettings)

    rate_limit_settings = get_setting(RateLimitSettings)

    # Apply rate limiting before creating model
    rate_limiter = get_rate_limiter()
    rate_limiter.wait()

    return ChatOpenAI(
        model=settings.llm_model_name,
        temperature=settings.temperature,
        max_retries=rate_limit_settings.max_retries,
        request_timeout=60,
    )


@lru_cache
def get_setting(setting_class: Type[TypeSetting]) -> TypeSetting:
    """helper to cache the PydanticSettings classes"""
    return setting_class()
