"""ESPN API client for fetching NFL team and player data."""

from typing import Any, Dict, List, Literal, Optional

import httpx
from cachetools import cached
from tenacity import retry, stop_after_attempt, wait_exponential

from nfl_agent.src.utils.cache_utils import teams_cache, depth_cache, athlete_cache, stats_cache
from nfl_agent.src.models.espn_responses import (
    ESPNAthleteResponse,
    ESPNStatisticsResponse,
    ESPNTeamResponse,
    ESPNDepthChartResponse,
)
from nfl_agent.src.models.stats import (
    Player,
    QbPlayer,
    SkillPlayer,
    DefPlayer,
    InjuredPlayer,
    Team,
)


class ESPNClient:
    """Client for ESPN Core API endpoints."""
    
    CORE_API_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_multiplier: float = 1.0,
        season: str = "2024",
        season_type: str = "2",  # Regular season
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_multiplier = backoff_multiplier
        self.season = season
        self.season_type = season_type

    def _make_retry_decorator(self):
        """Create retry decorator with configured settings."""
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_multiplier, min=1, max=10),
            reraise=True,
        )

    def _get_core_api(self, endpoint: str) -> Dict[str, Any]:
        """Make a request to the Core API."""
        @self._make_retry_decorator()
        def _request():
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self.CORE_API_URL}/{endpoint}"
                response = client.get(url)
                response.raise_for_status()
                return response.json()

        return _request()

    # ========================================================================
    # Core API Endpoint Methods (Cached)
    # ========================================================================

    @cached(teams_cache)
    def get_team_info(self, team_id: str) -> ESPNTeamResponse:
        """
        Fetch team basic info and record from ESPN Core API.
        
        Endpoint: /seasons/{season}/teams/{team_id}
        Cached: 5 minutes
        
        Args:
            team_id: ESPN team ID
            
        Returns:
            ESPNTeamResponse with team info and record
        """
        endpoint = f"seasons/{self.season}/teams/{team_id}"
        data = self._get_core_api(endpoint)
        return ESPNTeamResponse(**data)

    @cached(depth_cache)
    def get_team_depth_chart(self, team_id: str) -> ESPNDepthChartResponse:
        """
        Fetch depth chart for a team from ESPN Core API.
        
        Endpoint: /seasons/{season}/teams/{team_id}/depthcharts
        Cached: 1 week
        
        Args:
            team_id: ESPN team ID
            
        Returns:
            ESPNDepthChartResponse with position rankings
        """
        endpoint = f"seasons/{self.season}/teams/{team_id}/depthcharts"
        data = self._get_core_api(endpoint)
        return ESPNDepthChartResponse(**data)

    @cached(athlete_cache)
    def get_athlete_info(self, athlete_id: str) -> ESPNAthleteResponse:
        """
        Fetch athlete biographical and injury data from ESPN Core API.
        
        Endpoint: /seasons/{season}/athletes/{athlete_id}
        Cached: 1 day
        
        Args:
            athlete_id: ESPN athlete ID
            
        Returns:
            ESPNAthleteResponse with biographical and injury data
        """
        endpoint = f"seasons/{self.season}/athletes/{athlete_id}"
        data = self._get_core_api(endpoint)
        return ESPNAthleteResponse(**data)

    @cached(stats_cache)
    def get_athlete_stats(self, athlete_id: str) -> ESPNStatisticsResponse:
        """
        Fetch athlete statistics for the season from ESPN Core API.
        
        Endpoint: /seasons/{season}/types/{type}/athletes/{athlete_id}/statistics/0
        Cached: 1 hour
        
        Args:
            athlete_id: ESPN athlete ID
            
        Returns:
            ESPNStatisticsResponse with all stat categories
        """
        endpoint = f"seasons/{self.season}/types/{self.season_type}/athletes/{athlete_id}/statistics/0"
        data = self._get_core_api(endpoint)
        return ESPNStatisticsResponse(**data)

    # ========================================================================
    # Helper Methods for Computed Fields
    # ========================================================================

    def _compute_position_class(
        self, position_abbr: str
    ) -> Literal["QB", "SKILL", "OL", "DEF"]:
        """
        Derive position class from position abbreviation.
        
        Args:
            position_abbr: Position abbreviation (e.g., "QB", "WR", "DE")
            
        Returns:
            Position class: "QB", "SKILL", "OL", or "DEF"
        """
        position_upper = position_abbr.upper()
        
        if position_upper == "QB":
            return "QB"
        elif position_upper in ["WR", "RB", "TE", "FB"]:
            return "SKILL"
        elif position_upper in ["C", "LG", "RG", "LT", "RT", "G", "T", "OL"]:
            return "OL"
        else:
            # Default to DEF for defensive positions and special teams
            return "DEF"

    def _map_injury_status(
        self, injuries: List[Any]
    ) -> Literal["out", "questionable", "doubtful", "active"]:
        """
        Map ESPN injury status to our enum values.
        
        Args:
            injuries: List of ESPN injury objects
            
        Returns:
            Mapped injury status
        """
        if not injuries:
            return "active"
        
        # Get first injury (most recent/significant)
        injury = injuries[0]
        status = injury.status.lower() if hasattr(injury, "status") else ""
        type_name = injury.type.name.upper() if hasattr(injury, "type") and hasattr(injury.type, "name") else ""
        
        # Map to our enum values
        if "OUT" in status.upper() or "OUT" in type_name or "INJURED RESERVE" in type_name:
            return "out"
        elif "QUESTIONABLE" in status.upper() or "QUESTIONABLE" in type_name:
            return "questionable"
        elif "DOUBTFUL" in status.upper() or "DOUBTFUL" in type_name:
            return "doubtful"
        else:
            return "active"

    # ========================================================================
    # Builder Methods: Transform ESPN Responses to Domain Models
    # ========================================================================

    def build_qb_player(self, athlete_id: str, team_abbr: str) -> QbPlayer:
        """
        Build QbPlayer domain model from ESPN data.
        
        Args:
            athlete_id: ESPN athlete ID
            team_abbr: Team abbreviation
            
        Returns:
            QbPlayer with all required stats
        """
        # Fetch athlete info and stats
        athlete = self.get_athlete_info(athlete_id)
        stats = self.get_athlete_stats(athlete_id)
        
        # Extract passing stats
        passing_yards = int(stats.get_stat_value("passing", "passingYards") or 0)
        passing_tds = int(stats.get_stat_value("passing", "passingTouchdowns") or 0)
        interceptions = int(stats.get_stat_value("passing", "interceptions") or 0)
        completion_pct = float(stats.get_stat_value("passing", "completionPct") or 0.0)
        
        # Extract general stats
        fumbles_lost = int(stats.get_stat_value("general", "fumblesLost") or 0)
        
        return QbPlayer(
            name=athlete.fullName,
            team=team_abbr,
            position=athlete.position.abbreviation,
            position_class="QB",
            height=int(athlete.height),
            weight=athlete.weight,
            age=athlete.age,
            passing_yards=passing_yards,
            passing_tds=passing_tds,
            interceptions=interceptions,
            completion_pct=completion_pct,
            fumbles_lost=fumbles_lost,
        )

    def build_skill_player(self, athlete_id: str, team_abbr: str) -> SkillPlayer:
        """
        Build SkillPlayer domain model from ESPN data with computed fields.
        
        Args:
            athlete_id: ESPN athlete ID
            team_abbr: Team abbreviation
            
        Returns:
            SkillPlayer with computed touches, yards_per_touch, etc.
        """
        # Fetch athlete info and stats
        athlete = self.get_athlete_info(athlete_id)
        stats = self.get_athlete_stats(athlete_id)
        
        # Extract rushing stats
        rushing_attempts = int(stats.get_stat_value("rushing", "rushingAttempts") or 0)
        rushing_yards = int(stats.get_stat_value("rushing", "rushingYards") or 0)
        rushing_tds = int(stats.get_stat_value("rushing", "rushingTouchdowns") or 0)
        
        # Extract receiving stats
        receiving_targets = int(stats.get_stat_value("receiving", "receivingTargets") or 0)
        receiving_yards = int(stats.get_stat_value("receiving", "receivingYards") or 0)
        receiving_tds = int(stats.get_stat_value("receiving", "receivingTouchdowns") or 0)
        
        # Extract general stats
        fumbles_lost = int(stats.get_stat_value("general", "fumblesLost") or 0)
        
        # Compute derived fields
        touches = rushing_attempts + receiving_targets
        scrimmage_yards = rushing_yards + receiving_yards
        touchdowns = rushing_tds + receiving_tds
        yards_per_touch = scrimmage_yards / touches if touches > 0 else 0.0
        
        return SkillPlayer(
            name=athlete.fullName,
            team=team_abbr,
            position=athlete.position.abbreviation,
            position_class="SKILL",
            height=int(athlete.height),
            weight=athlete.weight,
            age=athlete.age,
            touches=touches,
            scrimmage_yards=scrimmage_yards,
            touchdowns=touchdowns,
            yards_per_touch=yards_per_touch,
            fumbles_lost=fumbles_lost,
        )

    def build_def_player(self, athlete_id: str, team_abbr: str) -> DefPlayer:
        """
        Build DefPlayer domain model from ESPN data with computed fields.
        
        Args:
            athlete_id: ESPN athlete ID
            team_abbr: Team abbreviation
            
        Returns:
            DefPlayer with computed qb_pressures and turnovers
        """
        # Fetch athlete info and stats
        athlete = self.get_athlete_info(athlete_id)
        stats = self.get_athlete_stats(athlete_id)
        
        # Extract defensive stats
        tackles = int(stats.get_stat_value("defensive", "totalTackles") or 0)
        sacks = int(stats.get_stat_value("defensive", "sacks") or 0)
        passes_defended = int(stats.get_stat_value("defensive", "passesDefended") or 0)
        qb_hits = int(stats.get_stat_value("defensive", "QBHits") or 0)
        hurries = int(stats.get_stat_value("defensive", "hurries") or 0)
        
        # Extract interceptions
        interceptions = int(stats.get_stat_value("defensiveInterceptions", "interceptions") or 0)
        
        # Extract forced fumbles
        forced_fumbles = int(stats.get_stat_value("general", "fumblesForced") or 0)
        
        # Compute derived fields
        qb_pressures = sacks + qb_hits + hurries
        turnovers = interceptions + forced_fumbles
        
        return DefPlayer(
            name=athlete.fullName,
            team=team_abbr,
            position=athlete.position.abbreviation,
            position_class="DEF",
            height=int(athlete.height),
            weight=athlete.weight,
            age=athlete.age,
            tackles=tackles,
            sacks=sacks,
            qb_pressures=qb_pressures,
            turnovers=turnovers,
            passes_defended=passes_defended,
        )

    def build_injured_player(self, athlete_id: str, team_abbr: str) -> InjuredPlayer:
        """
        Build InjuredPlayer domain model from ESPN data.
        
        Args:
            athlete_id: ESPN athlete ID
            team_abbr: Team abbreviation
            
        Returns:
            InjuredPlayer with injury info and mapped status
        """
        # Fetch athlete info
        athlete = self.get_athlete_info(athlete_id)
        
        # Extract injury info
        injury_description = "Unknown"
        if athlete.injuries:
            injury = athlete.injuries[0]
            if hasattr(injury, "details") and injury.details:
                injury_description = injury.details.type
            elif hasattr(injury, "shortComment") and injury.shortComment:
                injury_description = injury.shortComment
        
        injury_status = self._map_injury_status(athlete.injuries)
        
        return InjuredPlayer(
            name=athlete.fullName,
            team=team_abbr,
            position=athlete.position.abbreviation,
            position_class=self._compute_position_class(athlete.position.abbreviation),
            height=int(athlete.height),
            weight=athlete.weight,
            age=athlete.age,
            injury=injury_description,
            injury_status=injury_status,
        )

    def build_team(self, team_id: str) -> Team:
        """
        Build complete Team domain model from ESPN data.
        
        This method orchestrates calls in the optimal order:
        1. Get team info (cached)
        2. Get depth chart (cached)
        3. Extract athlete IDs for key positions
        4. Fetch athlete data and stats (cached individually)
        5. Build player domain models
        
        Args:
            team_id: ESPN team ID
            
        Returns:
            Complete Team model with all players
        """
        # Step 1: Get team basic info
        team_info = self.get_team_info(team_id)
        team_abbr = team_info.team.abbreviation
        
        # Step 2: Get depth chart
        depth_chart = self.get_team_depth_chart(team_id)
        
        # Step 3: Extract athlete IDs for key positions
        
        # QB: Get starter (rank 1)
        qb_id = depth_chart.get_starter_by_position("QB")
        if not qb_id:
            raise ValueError(f"No QB found in depth chart for team {team_id}")
        
        # Skill players: Get top 3 across RB, WR, TE
        skill_ids = depth_chart.get_top_n_by_positions(["RB", "WR", "TE"], n=3)
        
        # Defensive player: Get top DE, DT, or LB (prefer DE/LB for sacks)
        def_id = (
            depth_chart.get_starter_by_position("DE")
            or depth_chart.get_starter_by_position("LB")
            or depth_chart.get_starter_by_position("DT")
        )
        
        # Injured players: Get from roster (we'll need to fetch all athletes and filter)
        # For now, we'll build a list after fetching athlete info
        injured_ids: List[str] = []
        
        # Step 4 & 5: Build player models
        
        # Build QB
        qb_player = self.build_qb_player(qb_id, team_abbr)
        
        # Build skill players (up to 3)
        skill_players: List[SkillPlayer] = []
        for skill_id in skill_ids[:3]:
            try:
                skill_player = self.build_skill_player(skill_id, team_abbr)
                skill_players.append(skill_player)
            except Exception as e:
                print(f"Warning: Failed to build skill player {skill_id}: {e}")
                continue
        
        # Build defensive player
        def_player = None
        if def_id:
            try:
                def_player = self.build_def_player(def_id, team_abbr)
            except Exception as e:
                print(f"Warning: Failed to build defensive player {def_id}: {e}")
        
        # Ensure we have a defensive player (create default if needed)
        if def_player is None:

        
        # Build injured players (check all athletes we've fetched)
        injured_players: List[InjuredPlayer] = []
        all_athlete_ids = [qb_id] + skill_ids + ([def_id] if def_id else [])
        for athlete_id in all_athlete_ids:
            try:
                athlete = self.get_athlete_info(athlete_id)
                if athlete.injuries:
                    injured_player = self.build_injured_player(athlete_id, team_abbr)
                    injured_players.append(injured_player)
                    if len(injured_players) >= 3:
                        break
            except Exception as e:
                print(f"Warning: Failed to check injuries for {athlete_id}: {e}")
                continue
        
        # Build Team model
        return Team(
            name=team_info.team.displayName,
            abbreviation=team_abbr,
            rank=team_info.get_playoff_seed() or 16,  # Default to middle rank if no seed
            record=team_info.get_record_summary(),
            qb_player=qb_player,
            skill_stats=skill_players,
            def_player=def_player,
            injured_players=injured_players,
        )
