from pydantic import BaseModel
from pydantic import Field
from typing import Literal
from typing import List

# break out players into separate classes for each position class
# track minimal stats needed to get player value 
# ref: https://www.espn.com/nfl/statistics/glossary.html
# 
class Player(BaseModel):
    name: str
    team: str
    position: str
    position_class: Literal["QB", "SKILL", "OL", "DEF"]
    height: int
    weight: float
    age: int

class QbPlayer(Player):
    position_class: Literal["QB"] = Field(default="QB")
    passing_yards: int
    passing_tds: int
    interceptions: int
    completion_pct: float
    fumbles_lost: int

class SkillPlayer(Player):
    position_class: Literal["SKILL"] = Field(default="SKILL")
    touches: int = Field(description="rushes for RB, targets for WR/TE")
    scrimmage_yards: int = Field(description="total yards from scrimmage")
    touchdowns: int
    yards_per_touch: float
    fumbles_lost: int


class DefPlayer(Player):
    position_class: Literal["DEF"] = Field(default="DEF")
    tackles: int
    sacks: int
    qb_pressures: int
    turnovers: int = Field(description="interceptions + forced fumbles")
    passes_defended: int


class InjuredPlayer(Player):
    injury: str = Field(description="injury description")
    injury_status: Literal["out", "questionable", "doubtful", "active"] = Field(description="injury status")



class Team(BaseModel):
    name: str
    abbreviation: str
    rank: int = Field(description="power ranking of team from 1-32")
    record: str = Field(description="record of team in format W-L-T")
    # pick the most important players for each team
    qb_player: QbPlayer
    skill_stats: List[SkillPlayer] = Field(description="list of skill players for the team, max 3")
    def_player: DefPlayer
    injured_players: List[InjuredPlayer] = Field(description="list of injured players for the team, max 3")
