import logging
import httpx
import trafilatura
import re
from typing import List, Optional
from nfl_agent.src.models.espn_search import TeamInfo, ESPNSearchArticle
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.utils.settings import get_setting, LLMSettings, get_chat_model
from langchain.messages import SystemMessage, HumanMessage
from nfl_agent.prompts.article_relevance.v2 import (
    ArticleRelevanceResponse,
    SYSTEM_PROMPT as ARTICLE_RELEVANCE_SYSTEM_PROMPT,
    USER_PROMPT as ARTICLE_RELEVANCE_USER_PROMPT,
)
from nfl_agent.prompts.article_summarizer.v2 import (
    SYSTEM_PROMPT as ARTICLE_SUMMARIZER_SYSTEM_PROMPT,
    USER_PROMPT as ARTICLE_SUMMARIZER_USER_PROMPT,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import RateLimitError

logger = logging.getLogger(__name__)


def _clean_article_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)

    boilerplate_patterns = [
        r"Share this article.*?\n",
        r"Follow.*?on Twitter.*?\n",
        r"ESPN\+.*?subscribe.*?\n",
        r"Advertisement\n",
    ]
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def fetch_articles_for_team(team_id: int) -> List[ESPNSearchArticle]:
    client = ESPNClient()
    articles = client.search_nfl(team_id=team_id).articles
    if not articles:
        logger.warning(f"No articles found for team_id={team_id}")
    return articles


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: print(
        f"Rate limited, waiting {retry_state.next_action.sleep:.1f}s before retry {retry_state.attempt_number}/5..."
    ),
)
def select_relevant_article(
    team_name: str, articles: List[ESPNSearchArticle]
) -> ESPNSearchArticle:
    article_relevance_settings = get_setting(LLMSettings)
    article_relevance_model = get_chat_model(article_relevance_settings)
    article_relevance_model = article_relevance_model.with_structured_output(
        ArticleRelevanceResponse
    )
    result = article_relevance_model.invoke(
        [
            SystemMessage(content=ARTICLE_RELEVANCE_SYSTEM_PROMPT),
            HumanMessage(
                content=ARTICLE_RELEVANCE_USER_PROMPT.format(
                    team_name=team_name,
                    articles="\n\n".join(
                        [article.get_descriptions() for article in articles]
                    ),
                )
            ),
        ]
    )
    return next((article for article in articles if article.id == result.article_id))


def fetch_article_content(article_url: str, max_length: int = 5000) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = httpx.get(
        article_url, headers=headers, timeout=10.0, follow_redirects=True
    )
    response.raise_for_status()
    html = response.text

    content = trafilatura.extract(
        html, include_comments=False, include_tables=True, no_fallback=False
    )

    if not content:
        raise ValueError("Failed to extract content from article")

    content = _clean_article_text(content)

    if len(content) > max_length:
        content = (
            content[:max_length] + "\n\n[Article truncated for context management]"
        )

    return content


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: print(
        f"Rate limited, waiting {retry_state.next_action.sleep:.1f}s before retry {retry_state.attempt_number}/5..."
    ),
)
def summarize_article_content(team_name: str, article_content: str) -> TeamInfo:
    article_summarization_settings = get_setting(LLMSettings)
    article_summarization_model = get_chat_model(article_summarization_settings)
    article_summarization_model = article_summarization_model.with_structured_output(
        TeamInfo
    )
    result: TeamInfo = article_summarization_model.invoke(
        [
            SystemMessage(content=ARTICLE_SUMMARIZER_SYSTEM_PROMPT),
            HumanMessage(
                content=ARTICLE_SUMMARIZER_USER_PROMPT.format(
                    team_name=team_name, article_content=article_content
                )
            ),
        ]
    )
    return result


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return True
    return False


def combine_team_info_logic(
    old_team_info: Optional[TeamInfo], new_team_info: TeamInfo
) -> TeamInfo:
    if old_team_info is None:
        return new_team_info

    old_team_info_dict = old_team_info.model_dump()
    new_team_info_dict = new_team_info.model_dump()

    for key, new_value in new_team_info_dict.items():
        if key not in old_team_info_dict:
            continue

        old_value = old_team_info_dict[key]

        if _is_empty(new_value):
            continue

        if _is_empty(old_value):
            old_team_info_dict[key] = new_value
        elif isinstance(new_value, list) and isinstance(old_value, list):
            combined = old_value + [item for item in new_value if item not in old_value]
            old_team_info_dict[key] = combined
        elif isinstance(new_value, dict) and isinstance(old_value, dict):
            merged_dict = old_value.copy()
            merged_dict.update(new_value)
            old_team_info_dict[key] = merged_dict
        elif isinstance(new_value, str) and isinstance(old_value, str):
            if new_value != old_value:
                old_team_info_dict[key] = f"{old_value}\n\n{new_value}"
        else:
            pass

    updated_team_info = TeamInfo.model_validate(old_team_info_dict)
    return updated_team_info
