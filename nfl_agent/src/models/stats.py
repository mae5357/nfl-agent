from pydantic import BaseModel
from pydantic import Field
from typing import Literal
from typing import List
from typing import Optional
from nfl_agent.src.models.espn_responses import ESPNStat


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
    general_stats: List[ESPNStat]
    passing_stats: List[ESPNStat]
    rushing_stats: List[ESPNStat]
    scoring_stats: List[ESPNStat]

class SkillPlayer(Player):
    position_class: Literal["SKILL"] = Field(default="SKILL")
    general_stats: List[ESPNStat]
    rushing_stats: List[ESPNStat]
    receiving_stats: List[ESPNStat]
    scoring_stats: List[ESPNStat]



class DefPlayer(Player):
    position_class: Literal["DEF"] = Field(default="DEF")
    general_stats: List[ESPNStat]
    defensive_stats: List[ESPNStat]


class InjuredPlayer(Player):
    injury: str = Field(description="injury description")
    injury_status: Literal["out", "questionable", "doubtful", "active"] = Field(
        description="injury status"
    )


class Team(BaseModel):
    name: str
    abbreviation: str
    rank: int = Field(description="power ranking of team from 1-32")
    record: str = Field(description="record of team in format W-L-T")
    # pick the most important players for each team
    qb_player: QbPlayer
    skill_stats: List[SkillPlayer] = Field(
        description="list of skill players for the team, max 3"
    )
    def_players: List[DefPlayer] = Field(
        description="list of defensive players for the team, max 5"
    )
    # TODO: add injured players
    # injured_players: List[InjuredPlayer] = Field(
    #     description="list of injured players for the team, max 3"
    # )
