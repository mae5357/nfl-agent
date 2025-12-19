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
    
    name: str
    displayName: Optional[str] = None
    abbreviation: Optional[str] = None
    value: Optional[float] = None
    displayValue: Optional[str] = None


class ESPNStatCategory(BaseModel):
    """Category of stats (e.g., passing, rushing, defensive)."""
    model_config = ConfigDict(extra="ignore")
    
    name: str
    displayName: Optional[str] = None
    abbreviation: Optional[str] = None
    stats: List[ESPNStat] = Field(default_factory=list)


class ESPNSplits(BaseModel):
    """Splits object containing categories."""
    model_config = ConfigDict(extra="ignore")
    
    categories: List[ESPNStatCategory] = Field(default_factory=list)


class ESPNStatisticsResponse(BaseModel):
    """Response model for ESPN athlete statistics endpoint."""
    model_config = ConfigDict(extra="ignore")
    
    splits: ESPNSplits = Field(default_factory=ESPNSplits)
    
    def get_stat_value(self, category_name: str, stat_name: str) -> Optional[float]:
        """Helper to get a specific stat value."""
        for category in self.splits.categories:
            if category.name == category_name:
                for stat in category.stats:
                    if stat.name == stat_name:
                        return stat.value
        return None
    
    def get_category(self, category_name: str) -> Optional[ESPNStatCategory]:
        """Get a specific category by name."""
        for category in self.splits.categories:
            if category.name == category_name:
                return category
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
    
    def get_starter_by_position(self, position_abbr: str) -> Optional[str]:
        """
        Get the starting player ID for a position abbreviation.
        
        Args:
            position_abbr: Position like "QB", "RB", "WR", "TE", "DE", "LB", etc.
        
        Returns:
            Athlete ID of the starter, or None if not found
        """
        position_abbr_upper = position_abbr.upper()
        
        for formation in self.items:
            for pos_key, pos_data in formation.positions.items():
                # Check if this position matches
                if pos_data.position and pos_data.position.abbreviation == position_abbr_upper:
                    # Get rank 1 athlete
                    for athlete in pos_data.athletes:
                        if athlete.rank == 1:
                            return athlete.get_athlete_id()
                
                # Also check position key mapping (e.g., "qb" -> "QB")
                if pos_key.upper() == position_abbr_upper:
                    for athlete in pos_data.athletes:
                        if athlete.rank == 1:
                            return athlete.get_athlete_id()
        
        return None
    
    def get_top_n_by_positions(self, position_abbrs: List[str], n: int = 3) -> List[str]:
        """
        Get top N players across multiple positions (useful for skill players).
        
        Args:
            position_abbrs: List of positions like ["RB", "WR", "TE"]
            n: Number of top players to return
        
        Returns:
            List of athlete IDs (up to n)
        """
        athlete_ids = []
        
        for position_abbr in position_abbrs:
            position_abbr_upper = position_abbr.upper()
            
            for formation in self.items:
                for pos_key, pos_data in formation.positions.items():
                    # Check if this position matches
                    matches = False
                    if pos_data.position and pos_data.position.abbreviation == position_abbr_upper:
                        matches = True
                    elif pos_key.upper() == position_abbr_upper:
                        matches = True
                    
                    if matches:
                        # Get all athletes from this position, sorted by rank
                        sorted_athletes = sorted(pos_data.athletes, key=lambda a: a.rank)
                        for athlete in sorted_athletes:
                            athlete_id = athlete.get_athlete_id()
                            if athlete_id and athlete_id not in athlete_ids:
                                athlete_ids.append(athlete_id)
                                if len(athlete_ids) >= n:
                                    return athlete_ids
        
        return athlete_ids

