from nfl_agent.src.tools.article_fetcher.state import TeamArticleQueryState
from nfl_agent.src.tools.article_fetcher.utils import (
    fetch_articles_for_team,
    select_relevant_article,
    fetch_article_content,
    summarize_article_content,
    combine_team_info_logic,
)

MIN_ARTICLES_TO_READ = 5
MAX_ARTICLES_TO_READ = 10


def node_get_list_of_articles(state: TeamArticleQueryState) -> dict:
    if state.get("articles") is not None:
        return {
            "articles": state["articles"],
            "articles_read_count": state.get("articles_read_count", 0),
        }
    articles = fetch_articles_for_team(state["team_id"])
    return {
        "articles": articles,
        "articles_read_count": state.get("articles_read_count", 0),
    }


def node_get_article_relevance(state: TeamArticleQueryState) -> dict:
    selected_article = select_relevant_article(state["team_name"], state["articles"])
    remaining_articles = (
        [a for a in state["articles"] if a.id != selected_article.id]
        if selected_article
        else state["articles"]
    )
    return {"selected_article": selected_article, "articles": remaining_articles}


def should_fetch_article(state: TeamArticleQueryState) -> str:
    if state["selected_article"] is None:
        return "skip"
    return "fetch"


def node_fetch_article_content(
    state: TeamArticleQueryState, max_length: int = 5000
) -> dict:
    article = state["selected_article"]
    article_url = article.get_web_url()
    content = fetch_article_content(article_url, max_length)
    return {"article_content": content}


def node_summarize_article_content(state: TeamArticleQueryState) -> dict:
    result = summarize_article_content(state["team_name"], state["article_content"])
    return {"new_team_info": result}


def node_combine_team_info(state: TeamArticleQueryState) -> dict:
    old_team_info = state["team_info"]
    new_team_info = state["new_team_info"]
    articles_read_count = state["articles_read_count"] + 1

    updated_team_info = combine_team_info_logic(old_team_info, new_team_info)
    print(
        f"updated team info for {state['team_name']}. Articles read: {articles_read_count}"
    )
    return {"team_info": updated_team_info, "articles_read_count": articles_read_count}


def should_continue(state: TeamArticleQueryState) -> str:
    articles_read_count = state["articles_read_count"]

    if articles_read_count < MIN_ARTICLES_TO_READ:
        return "continue"

    if articles_read_count > MAX_ARTICLES_TO_READ:
        return "end"

    team_info = state["team_info"]
    if team_info is None:
        return "continue"

    if team_info.coaching_summary is None:
        return "continue"
    if team_info.injuries is None or len(team_info.injuries) == 0:
        return "continue"
    if team_info.strengths is None or len(team_info.strengths) == 0:
        return "continue"
    if team_info.problem_areas is None or len(team_info.problem_areas) == 0:
        return "continue"
    if team_info.relevant_players is None or len(team_info.relevant_players) == 0:
        return "continue"

    return "end"
