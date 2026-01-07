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
class Stat(BaseModel):
    """Individual stat with all ESPN metadata."""

    display_name: str = Field(description="Human-readable stat name")
    description: str = Field(description="Stat description")
    value: float = Field(description="Stat value")
    per_game_value: Optional[float] = Field(
        default=None, description="Per-game stat value"
    )
    rank: Optional[int] = Field(default=None, description="League rank for this stat")


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

    # Volume stats
    passing_yards: Stat
    passing_attempts: Stat
    completions: Stat

    # Efficiency stats
    completion_pct: Stat
    passer_rating: Stat
    net_yards_per_pass_attempt: Stat

    # Scoring + mistakes
    passing_touchdowns: Stat
    interceptions: Stat

    # Ball security
    fumbles_lost: Stat

    # Pressure context
    sacks_taken: Stat


class SkillPlayer(Player):
    position_class: Literal["SKILL"] = Field(default="SKILL")

    games_played: int = 0

    # Opportunity / usage
    targets: int = 0
    receptions: int = 0
    rushing_attempts: int = 0
    touches: int = 0  # receptions + rushing_attempts

    # Production
    receiving_yards: int = 0
    rushing_yards: int = 0
    yards_from_scrimmage: int = 0

    # Scoring + ball security
    total_touchdowns: int = 0
    fumbles_lost: int = 0


class DefPlayer(Player):
    position_class: Literal["DEF"] = Field(default="DEF")

    games_played: Optional[int] = None

    # Tackle stats
    total_tackles: Optional[float] = None
    solo_tackles: Optional[float] = None

    # Pass rush stats
    sacks: Optional[float] = None
    qb_hits: Optional[float] = None

    # Coverage/disruption stats
    passes_defended: Optional[float] = None

    # Takeaway stats
    interceptions: Optional[float] = None
    forced_fumbles: Optional[float] = None

    # Derived convenience field
    takeaways: Optional[float] = None


class InjuredPlayer(Player):
    injury: str = Field(description="injury description")
    injury_status: Literal["out", "questionable", "doubtful", "active"] = Field(
        description="injury status"
    )
    # Stats fields - populated based on position
    general_stats: List[ESPNStat] = Field(default_factory=list)
    # Position-specific stats (optional, populated based on position_class)
    passing_stats: Optional[List[ESPNStat]] = Field(
        default=None, description="QB stats"
    )
    rushing_stats: Optional[List[ESPNStat]] = Field(
        default=None, description="QB/SKILL stats"
    )
    receiving_stats: Optional[List[ESPNStat]] = Field(
        default=None, description="SKILL stats"
    )
    scoring_stats: Optional[List[ESPNStat]] = Field(
        default=None, description="QB/SKILL stats"
    )
    defensive_stats: Optional[List[ESPNStat]] = Field(
        default=None, description="DEF stats"
    )


class Team(BaseModel):
    name: str
    abbreviation: str
    # pick the most important players for each team
    qb_player: QbPlayer
    skill_stats: List[SkillPlayer]
    def_players: List[DefPlayer]
    injured_players: List[InjuredPlayer]
