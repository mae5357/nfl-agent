from typing import List, Optional, TypedDict
from nfl_agent.src.models.espn_search import TeamInfo, ESPNSearchArticle


class TeamArticleQueryState(TypedDict):
    team_name: str
    team_id: int
    team_info: TeamInfo
    articles: Optional[List[ESPNSearchArticle]]
    selected_article: Optional[ESPNSearchArticle]
    article_content: Optional[str]
    new_team_info: Optional[TeamInfo]
    articles_read_count: int
