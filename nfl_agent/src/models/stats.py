from pydantic import BaseModel
from pydantic import Field
from typing import Optional


class Player(BaseModel):
    name: str
    team: str
    position: str
    height: int
    weight: float
    age: int
    is_injured: bool = Field(description="whether the player is injured")
    key_stats: Optional[list[str]] = Field(
        description="freeform list of key stats for the player"
    )
    # TODO: add more stats


class Team(BaseModel):
    name: str
    abbreviation: str
    rank: int = Field(description="power ranking of team from 1-32")
    record: str = Field(description="record of team in format W-L-T")
    key_players: list[Player] = Field(description="list of key players for the team")


class Game(BaseModel):
    home_team: Team
    away_team: Team
    home_team_spread: int = Field(description="spread for the home team")
    away_team_spread: int = Field(description="spread for the away team")
    over_under: float = Field(description="over/under for the game")
