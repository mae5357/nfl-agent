from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from nfl_agent.src.tools.article_fetcher.state import TeamArticleQueryState
from nfl_agent.src.tools.article_fetcher.nodes import (
    node_get_list_of_articles,
    node_get_article_relevance,
    node_fetch_article_content,
    node_summarize_article_content,
    node_combine_team_info,
    should_fetch_article,
    should_continue,
)
from nfl_agent.src.models.espn_search import TeamInfo
from nfl_agent.src.utils.espn_client import ESPNClient


def create_team_article_query_graph():
    workflow = StateGraph(TeamArticleQueryState)

    workflow.add_node("get_articles", node_get_list_of_articles)
    workflow.add_node("select_article", node_get_article_relevance)
    workflow.add_node("fetch_content", node_fetch_article_content)
    workflow.add_node("summarize_content", node_summarize_article_content)
    workflow.add_node("combine_team_info", node_combine_team_info)

    workflow.set_entry_point("get_articles")
    workflow.add_edge("get_articles", "select_article")

    workflow.add_conditional_edges(
        "select_article",
        should_fetch_article,
        {
            "fetch": "fetch_content",
            "skip": END,
        },
    )

    workflow.add_edge("fetch_content", "summarize_content")
    workflow.add_edge("summarize_content", "combine_team_info")

    workflow.add_conditional_edges(
        "combine_team_info",
        should_continue,
        {
            "continue": "get_articles",
            "end": END,
        },
    )

    return workflow.compile()


_team_article_query_graph = create_team_article_query_graph()


@tool
def search_nfl(team_name: str) -> TeamInfo:
    """
    Use the ESPN search to find insightful articles about the upcoming match. Read the articles and pull out the most relevant facts.

    Args:
        team_name: The name of the team to search for articles about.
    Returns:
        TeamInfo: The team information including the articles and the most relevant facts.
    """
    client = ESPNClient()
    team_id = client.get_team_id(team_name)
    initial_state: TeamArticleQueryState = {
        "team_name": team_name,
        "team_id": team_id,
        "team_info": None,
        "articles": None,
        "selected_article": None,
        "article_content": None,
        "new_team_info": None,
        "articles_read_count": 0,
    }

    final_state = _team_article_query_graph.invoke(
        initial_state,
        # high recursion limit because we ar querying two teams at once
        {"recursion_limit": 100},
    )

    return final_state["team_info"]


if __name__ == "__main__":
    graph = create_team_article_query_graph()
    print(graph.get_graph().draw_mermaid())
