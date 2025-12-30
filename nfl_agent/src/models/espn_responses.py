"""Pydantic models for ESPN API responses."""

from typing import Any, List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ESPNPosition(BaseModel):
    """ESPN position nested object."""

    model_config = ConfigDict(extra="ignore")

    abbreviation: str
    name: Optional[str] = None
    displayName: Optional[str] = None


class ESPNInjuryDetails(BaseModel):
    """ESPN injury details."""

    model_config = ConfigDict(extra="ignore")

    type: str  # e.g., "Ankle", "Knee"
    location: Optional[str] = None  # e.g., "Leg"


class ESPNInjuryType(BaseModel):
    """ESPN injury type information."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str  # e.g., "INJURY_STATUS_QUESTIONABLE"
    description: Optional[str] = None
    abbreviation: Optional[str] = None


class ESPNInjury(BaseModel):
    """ESPN injury object."""

    model_config = ConfigDict(extra="ignore")

    status: str  # e.g., "Questionable", "Out"
    type: ESPNInjuryType
    details: Optional[ESPNInjuryDetails] = None
    shortComment: Optional[str] = None


class ESPNAthleteResponse(BaseModel):
    """Response model for ESPN athlete endpoint."""

    model_config = ConfigDict(extra="ignore")

    id: str
    fullName: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    height: float  # in inches
    weight: float  # in lbs
    age: int
    position: ESPNPosition
    team: Dict[str, str] = Field(default_factory=dict)  # Contains $ref
    injuries: List[ESPNInjury] = Field(default_factory=list)

    @field_validator("position", mode="before")
    @classmethod
    def parse_position(cls, v: Any) -> ESPNPosition:
        """Parse position from dict or return as-is."""
        if isinstance(v, dict):
            return ESPNPosition(**v)
        return v

    def get_team_id(self) -> Optional[str]:
        """Extract team ID from team.$ref URL."""
        ref = self.team.get("$ref", "")
        if "/teams/" in ref:
            return ref.split("/teams/")[1].split("?")[0]
        return None


class ESPNStat(BaseModel):
    """Individual stat within a category."""

    model_config = ConfigDict(extra="ignore")

    displayName: str
    description: str
    value: float
    perGameValue: Optional[float] = None
    rank: Optional[int] = None



class ESPNStatCategory(BaseModel):
    """Category of stats (e.g., passing, rushing, defensive)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    displayName: str
    stats: List[ESPNStat]


class ESPNSplits(BaseModel):
    """Splits object containing categories."""

    model_config = ConfigDict(extra="ignore")

    categories: List[ESPNStatCategory]


class ESPNStatisticsResponse(BaseModel):
    """Response model for ESPN athlete statistics endpoint."""

    model_config = ConfigDict(extra="ignore")

    splits: ESPNSplits

    def get_category_stats(self, category_name: str) -> Optional[List[ESPNStat]]:
        """Get a specific category by name."""
        for category in self.splits.categories:
            if category.name == category_name:
                return category.stats
        return None


class ESPNRecordItem(BaseModel):
    """Team record item."""

    model_config = ConfigDict(extra="ignore")

    type: str  # e.g., "total", "home", "away"
    summary: str  # e.g., "4-10"
    stats: List[Dict[str, Any]] = Field(default_factory=list)

    def get_stat_value(self, stat_name: str) -> Optional[Any]:
        """Get a specific stat value from stats list."""
        for stat in self.stats:
            if stat.get("name") == stat_name:
                return stat.get("value") or stat.get("displayValue")
        return None


class ESPNTeamInfo(BaseModel):
    """Team information nested object."""

    model_config = ConfigDict(extra="ignore")

    id: str
    displayName: str
    name: str
    abbreviation: str
    record: Optional[Dict[str, Any]] = None


class ESPNTeamResponse(BaseModel):
    """Response model for ESPN team endpoint."""

    model_config = ConfigDict(extra="ignore")

    team: ESPNTeamInfo

    @model_validator(mode="before")
    @classmethod
    def flatten_if_needed(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle case where team data is at root or nested."""
        if "team" not in data and "displayName" in data:
            return {"team": data}
        return data

    def get_record_summary(self) -> str:
        """Extract record summary (W-L-T format)."""
        if not self.team.record:
            return "0-0"

        items = self.team.record.get("items", [])
        for item in items:
            if item.get("type") == "total":
                return item.get("summary", "0-0")

        # Fallback to first item
        if items:
            return items[0].get("summary", "0-0")

        return "0-0"

    def get_playoff_seed(self) -> int:
        """Extract playoff seed as proxy for rank."""
        if not self.team.record:
            return 0

        items = self.team.record.get("items", [])
        for item in items:
            if item.get("type") == "total":
                stats = item.get("stats", [])
                for stat in stats:
                    if stat.get("name") == "playoffSeed":
                        value = stat.get("value")
                        if value is not None:
                            try:
                                return int(value)
                            except (ValueError, TypeError):
                                pass
        return 0


class ESPNDepthChartAthlete(BaseModel):
    """Athlete entry in depth chart."""

    model_config = ConfigDict(extra="ignore")

    rank: int
    slot: Optional[int] = None
    athlete: Dict[str, str] = Field(default_factory=dict)  # Contains $ref

    def get_athlete_id(self) -> Optional[str]:
        """Extract athlete ID from athlete.$ref URL."""
        ref = self.athlete.get("$ref", "")
        if "/athletes/" in ref:
            parts = ref.split("/athletes/")[1].split("?")[0].split("/")
            return parts[0]
        return None


class ESPNDepthChartPosition(BaseModel):
    """Position entry in depth chart."""

    model_config = ConfigDict(extra="ignore")

    position: Optional[ESPNPosition] = None
    athletes: List[ESPNDepthChartAthlete] = Field(default_factory=list)


class ESPNDepthChartFormation(BaseModel):
    """Formation with positions (e.g., Base 3-4 D, 3WR 1TE)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    positions: Dict[str, ESPNDepthChartPosition] = Field(default_factory=dict)


class ESPNDepthChartResponse(BaseModel):
    """Response model for ESPN depth chart endpoint."""

    model_config = ConfigDict(extra="ignore")

    items: List[ESPNDepthChartFormation] = Field(default_factory=list)

    def get_starter_by_position(self, position_abbr: str, max_starters: int = 1) -> Optional[List[str]]:
        """
        Get the starting player ID for a position abbreviation.

        Args:
            position_abbr: Position like "QB", "RB", "WR", "TE", "DE", "LB", etc.

        Returns:
            List of athlete IDs of the starters, or None if not found
        """
        # iterrate through the items and get the starters up to the max_starters
        starters = []
        for formation in self.items:
            for pos_key, pos_data in formation.positions.items():
                if pos_data.position and pos_data.position.abbreviation == position_abbr:
                    for athlete in pos_data.athletes:
                        if athlete.rank <= max_starters:
                            starters.append(athlete.get_athlete_id())

        if len(starters) == 0:
            print(f"No starters found for position {position_abbr}")
        return starters