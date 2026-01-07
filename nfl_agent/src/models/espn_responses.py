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

    def extract_stat(self, category_name: str, display_name: str):
        """
        Extract a specific stat by displayName from a category.

        Args:
            category_name: Category to search (e.g., "passing", "general")
            display_name: The stat's displayName to search for

        Returns:
            Stat object with all metadata, or None if not found
        """
        from nfl_agent.src.models.stats import Stat

        category_stats = self.get_category_stats(category_name)
        if not category_stats:
            return None

        for espn_stat in category_stats:
            if espn_stat.displayName == display_name:
                return Stat(
                    display_name=espn_stat.displayName,
                    description=espn_stat.description,
                    value=espn_stat.value,
                    per_game_value=espn_stat.perGameValue,
                    rank=espn_stat.rank,
                )
        return None

    def extract_stat_with_fallback(self, category_name: str, display_names: List[str]):
        """
        Extract a stat with fallback options.

        Args:
            category_name: Category to search
            display_names: List of possible displayNames (tries in order)

        Returns:
            Stat object, or a default Stat with value 0.0 if not found
        """
        from nfl_agent.src.models.stats import Stat

        for display_name in display_names:
            stat = self.extract_stat(category_name, display_name)
            if stat:
                return stat

        # Return default stat if not found
        return Stat(
            display_name=display_names[0],
            description="Not available",
            value=0.0,
            per_game_value=None,
            rank=None,
        )


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

    def get_starter_by_position(
        self, position_abbr: str, max_starters: int = 1
    ) -> Optional[List[str]]:
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
                if (
                    pos_data.position
                    and pos_data.position.abbreviation == position_abbr
                ):
                    for athlete in pos_data.athletes:
                        if athlete.rank <= max_starters:
                            starters.append(athlete.get_athlete_id())

        return starters


# ========================================================================
# Scoreboard / Schedule Models
# ========================================================================


class ESPNGameCompetitor(BaseModel):
    """Competitor/team in a game."""

    model_config = ConfigDict(extra="ignore")

    id: str
    uid: Optional[str] = None
    type: Optional[str] = None  # "team"
    order: Optional[int] = None  # 1=away, 2=home
    homeAway: Optional[str] = None  # "home" or "away"
    team: Optional[Dict[str, Any]] = None
    score: Optional[str] = None

    def get_team_id(self) -> str:
        """Extract team ID."""
        return self.id

    def get_team_name(self) -> Optional[str]:
        """Extract team display name."""
        if self.team:
            return self.team.get("displayName") or self.team.get("name")
        return None

    def get_team_abbr(self) -> Optional[str]:
        """Extract team abbreviation."""
        if self.team:
            return self.team.get("abbreviation")
        return None


class ESPNGameStatus(BaseModel):
    """Game status information."""

    model_config = ConfigDict(extra="ignore")

    type: Dict[str, Any]

    def get_state(self) -> str:
        """Get status state: scheduled, in, post."""
        return self.type.get("state", "scheduled")

    def is_final(self) -> bool:
        """Check if game is final."""
        return self.get_state() == "post"

    def is_in_progress(self) -> bool:
        """Check if game is in progress."""
        return self.get_state() == "in"


class ESPNGameEvent(BaseModel):
    """Individual game event from scoreboard."""

    model_config = ConfigDict(extra="ignore")

    id: str
    uid: Optional[str] = None
    date: str  # ISO datetime
    name: Optional[str] = None  # e.g., "Team A at Team B"
    shortName: Optional[str] = None
    competitors: List[ESPNGameCompetitor] = Field(default_factory=list)
    status: Optional[ESPNGameStatus] = None
    competitions: Optional[List[Dict[str, Any]]] = None  # Alternative structure
    venue: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def extract_competitors(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract competitors from competitions if not at root."""
        if "competitors" not in data or not data["competitors"]:
            competitions = data.get("competitions", [])
            if competitions:
                # Competitors are nested in competitions[0]
                comp = competitions[0]
                data["competitors"] = comp.get("competitors", [])
                if "status" not in data:
                    data["status"] = comp.get("status")
                if "venue" not in data:
                    data["venue"] = comp.get("venue")
        return data

    def get_event_id(self) -> str:
        """Get event ID."""
        return self.id

    def get_kickoff_datetime(self) -> str:
        """Get kickoff datetime in ISO format."""
        return self.date

    def get_home_team(self) -> Optional[ESPNGameCompetitor]:
        """Get home team competitor."""
        for comp in self.competitors:
            if comp.homeAway == "home" or comp.order == 2:
                return comp
        return None

    def get_away_team(self) -> Optional[ESPNGameCompetitor]:
        """Get away team competitor."""
        for comp in self.competitors:
            if comp.homeAway == "away" or comp.order == 1:
                return comp
        return None

    def get_venue_name(self) -> Optional[str]:
        """Get venue name."""
        if self.venue:
            return self.venue.get("fullName")
        return None


class ESPNScoreboardResponse(BaseModel):
    """Response from scoreboard endpoint."""

    model_config = ConfigDict(extra="ignore")

    events: List[ESPNGameEvent] = Field(default_factory=list)
    week: Optional[Dict[str, Any]] = None
    season: Optional[Dict[str, Any]] = None


class ESPNScheduleGame(BaseModel):
    """Individual game from schedule endpoint."""

    model_config = ConfigDict(extra="ignore")

    id: str
    date: str  # ISO datetime
    name: Optional[str] = None
    shortName: Optional[str] = None
    competitions: List[Dict[str, Any]] = Field(default_factory=list)

    def get_event_id(self) -> str:
        """Get event ID."""
        return self.id

    def get_kickoff_datetime(self) -> str:
        """Get kickoff datetime."""
        return self.date

    def get_competitors(self) -> List[ESPNGameCompetitor]:
        """Extract competitors from competitions."""
        if self.competitions:
            competitors_data = self.competitions[0].get("competitors", [])
            return [ESPNGameCompetitor(**c) for c in competitors_data]
        return []

    def get_home_team(self) -> Optional[ESPNGameCompetitor]:
        """Get home team."""
        for comp in self.get_competitors():
            if comp.homeAway == "home" or comp.order == 2:
                return comp
        return None

    def get_away_team(self) -> Optional[ESPNGameCompetitor]:
        """Get away team."""
        for comp in self.get_competitors():
            if comp.homeAway == "away" or comp.order == 1:
                return comp
        return None


class ESPNScheduleResponse(BaseModel):
    """Response from schedule endpoint (cdn)."""

    model_config = ConfigDict(extra="ignore")

    content: Dict[str, Any] = Field(default_factory=dict)

    def get_games(self) -> List[ESPNScheduleGame]:
        """Extract games from schedule response."""
        games = []
        schedule = self.content.get("schedule", {})

        # Schedule can have different date keys
        for date_key, date_data in schedule.items():
            if isinstance(date_data, dict):
                games_data = date_data.get("games", [])
                for game_data in games_data:
                    games.append(ESPNScheduleGame(**game_data))

        return games


class NormalizedGame(BaseModel):
    """Normalized game data from either scoreboard or schedule endpoint."""

    event_id: str
    kickoff_utc: str  # ISO datetime
    home_team_id: str
    home_team_name: Optional[str] = None
    home_team_abbr: Optional[str] = None
    home_score: Optional[str] = None
    away_team_id: str
    away_team_name: Optional[str] = None
    away_team_abbr: Optional[str] = None
    away_score: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None  # "scheduled", "in", "post"

    def get_summary(self) -> str:
        """Get a human-readable game summary."""
        away = self.away_team_abbr or self.away_team_name or self.away_team_id
        home = self.home_team_abbr or self.home_team_name or self.home_team_id

        if self.status == "post" and self.away_score and self.home_score:
            return f"{away} {self.away_score} @ {home} {self.home_score} (Final)"
        elif self.status == "in" and self.away_score and self.home_score:
            return f"{away} {self.away_score} @ {home} {self.home_score} (In Progress)"
        else:
            return f"{away} @ {home}"
