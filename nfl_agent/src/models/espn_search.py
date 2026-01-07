from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ESPNSearchArticle(BaseModel):
    """Individual article from ESPN search."""

    id: int
    type: str  # "Story", "Recap", "Media"
    headline: str
    description: Optional[str] = None
    published: datetime
    lastModified: datetime
    links: Dict[str, Any]
    categories: List[Dict[str, Any]] = Field(
        default_factory=list
    )  # Teams, players, events

    def get_web_url(self) -> str:
        return self.links.get("web", {}).get("href", "")

    def get_related_teams(self) -> List[str]:
        teams = []
        for category in self.categories:
            if category.get("type") == "team":
                team_desc = category.get("description", "")
                if team_desc:
                    teams.append(team_desc)
        return teams

    def get_related_players(self) -> List[str]:
        players = []
        for category in self.categories:
            if category.get("type") == "athlete":
                player_desc = category.get("description", "")
                if player_desc:
                    players.append(player_desc)
        return players

    def get_descriptions(self) -> str:
        return f"Article ID: {self.id}, Headline: {self.headline}, Description: {self.description}, Published: {self.published}"


class ESPNSearchResponse(BaseModel):
    header: str
    articles: List[ESPNSearchArticle]


class TeamInfo(BaseModel):
    name: str
    coaching_summary: Optional[str] = Field(
        None, description="Summary of the team's coaching strategy"
    )
    injuries: Optional[List[str]] = Field(
        None, description="List of injuries for the team"
    )
    strengths: Optional[List[str]] = Field(
        None, description="List of strengths for the team"
    )
    problem_areas: Optional[List[str]] = Field(
        None, description="List of problem areas for the team"
    )
    relevant_players: Optional[List[str]] = Field(
        None, description="List of relevant players for the team"
    )


class GameOutcomeInsight(BaseModel):
    home_team_info: TeamInfo
    away_team_info: TeamInfo
    kickoff_timestamp: str
    weather_conditions: Optional[str] = Field(
        None, description="Weather conditions for the game"
    )
    home_away_context: Optional[str] = Field(
        None, description="Location advantage for the game"
    )
    matchup_info: Optional[List[str]] = Field(
        None, description="Things to watch for in the matchup"
    )
