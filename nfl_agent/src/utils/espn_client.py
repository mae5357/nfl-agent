"""ESPN API client for fetching NFL team and player data."""

import asyncio
from typing import Any, Dict, List, Literal, Optional

import httpx
from cachetools import cached, TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from nfl_agent.src.utils.cache_utils import (
    teams_cache,
    depth_cache,
    athlete_cache,
    stats_cache,
)
from nfl_agent.src.models.espn_responses import (
    ESPNAthleteResponse,
    ESPNStatisticsResponse,
    ESPNTeamResponse,
    ESPNDepthChartResponse,
)
from nfl_agent.src.models.espn_search import ESPNSearchResponse, ESPNSearchArticle
from nfl_agent.src.models.stats import (
    QbPlayer,
    SkillPlayer,
    DefPlayer,
    InjuredPlayer,
    Team,
)

# Add cache for search results (15-minute TTL - news is time-sensitive)
search_cache = TTLCache(maxsize=100, ttl=900)


class ESPNClient:
    """Client for ESPN Core API endpoints."""

    CORE_API_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    SITE_API_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    SEARCH_API_URL = "https://site.web.api.espn.com/apis/search/v2"

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_multiplier: float = 1.0,
        season: str = "2025",
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

    async def _get_core_api_async(self, endpoint: str) -> Dict[str, Any]:
        """Make an async request to the Core API."""

        @self._make_retry_decorator()
        async def _request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.CORE_API_URL}/{endpoint}"
                response = await client.get(url)
                response.raise_for_status()
                return response.json()

        return await _request()

    def _get_site_api(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Site API."""

        @self._make_retry_decorator()
        def _request():
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self.SITE_API_URL}/{endpoint}"
                response = client.get(url, params=params or {})
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

    async def get_athlete_info_async(self, athlete_id: str) -> ESPNAthleteResponse:
        endpoint = f"seasons/{self.season}/athletes/{athlete_id}"
        data = await self._get_core_api_async(endpoint)
        return ESPNAthleteResponse(**data)

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
        try:
            endpoint = f"seasons/{self.season}/types/{self.season_type}/athletes/{athlete_id}/statistics/0"
            data = self._get_core_api(endpoint)
            return ESPNStatisticsResponse(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                endpoint = f"athletes/{athlete_id}/statistics/0"
                data = self._get_core_api(endpoint)
                return ESPNStatisticsResponse(**data)
            else:
                raise e

    async def get_athlete_stats_async(self, athlete_id: str) -> ESPNStatisticsResponse:
        try:
            endpoint = f"seasons/{self.season}/types/{self.season_type}/athletes/{athlete_id}/statistics/0"
            data = await self._get_core_api_async(endpoint)
            return ESPNStatisticsResponse(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                endpoint = f"athletes/{athlete_id}/statistics/0"
                data = await self._get_core_api_async(endpoint)
                return ESPNStatisticsResponse(**data)
            else:
                raise e

    def search_athletes(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for athletes by name using the ESPN Search API.

        Endpoint: site.web.api.espn.com/apis/search/v2

        Args:
            query: Player name to search for
            limit: Maximum number of results to return

        Returns:
            List of athlete search results with id, fullName, team, position
        """

        @self._make_retry_decorator()
        def _search():
            params = {
                "query": query,
                "limit": limit,
            }
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self.SEARCH_API_URL, params=params)
                response.raise_for_status()
                return response.json()

        data = _search()

        # Extract athletes from search results
        athletes = []

        # ESPN Search API returns results grouped by type
        results = data.get("results", [])

        for result in results:
            # Look for player results
            if result.get("type") == "player":
                # Each result has a 'contents' array with the actual player data
                contents = result.get("contents", [])

                for player in contents:
                    # Extract athlete ID from uid field (format: "s:20~l:28~a:15847")
                    uid = player.get("uid", "")
                    athlete_id = None

                    if uid:
                        # Parse uid to extract athlete ID
                        parts = uid.split("~")
                        for part in parts:
                            if part.startswith("a:"):
                                athlete_id = part[2:]  # Remove "a:" prefix
                                break

                    # Skip if we couldn't extract an ID
                    if not athlete_id:
                        continue

                    athlete_data = {
                        "id": athlete_id,
                        "fullName": player.get("displayName"),
                        "team": player.get("subtitle"),  # e.g., "Kansas City Chiefs"
                        "position": None,  # Not included in search results
                    }

                    athletes.append(athlete_data)

        return athletes

    def search_nfl(
        self, query: str, limit: int = 10, content_types: Optional[List[str]] = None
    ) -> ESPNSearchResponse:
        """
        Search ESPN for NFL-related content.

        Endpoint: ESPN Site API News endpoint
        Cached: 15 minutes

        Args:
            query: Search query string (not used - gets latest NFL news)
            limit: Max results to return
            content_types: Filter by type ["Story", "Recap", "Media"]

        Returns:
            ESPNSearchResponse with articles
        """

        @self._make_retry_decorator()
        def _search():
            params = {
                "limit": limit,
            }
            with httpx.Client(timeout=self.timeout) as client:
                # Use the NFL News API which returns articles directly
                url = f"{self.SITE_API_URL}/news"
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Parse articles from response
                articles_data = data.get("articles", [])

                # Filter by content type if specified
                if content_types:
                    articles_data = [
                        a for a in articles_data if a.get("type") in content_types
                    ]

                # Parse into Pydantic models
                articles = [ESPNSearchArticle(**a) for a in articles_data[:limit]]

                return ESPNSearchResponse(
                    header=data.get("header", "NFL News"), articles=articles
                )

        return _search()

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
        type_name = (
            injury.type.name.upper()
            if hasattr(injury, "type") and hasattr(injury.type, "name")
            else ""
        )

        # Map to our enum values
        if (
            "OUT" in status.upper()
            or "OUT" in type_name
            or "INJURED RESERVE" in type_name
        ):
            return "out"
        elif "QUESTIONABLE" in status.upper() or "QUESTIONABLE" in type_name:
            return "questionable"
        elif "DOUBTFUL" in status.upper() or "DOUBTFUL" in type_name:
            return "doubtful"
        else:
            return "active"

    # ========================================================================
    # Builder Functions: Transform ESPN Responses to Domain Models
    # ========================================================================

    async def build_qb_player_async(self, athlete_id: str, team_abbr: str) -> QbPlayer:
        athlete, stats = await asyncio.gather(
            self.get_athlete_info_async(athlete_id),
            self.get_athlete_stats_async(athlete_id)
        )

        return QbPlayer(
            name=athlete.fullName,
            team=team_abbr,
            position=athlete.position.abbreviation,
            position_class="QB",
            height=int(athlete.height),
            weight=athlete.weight,
            age=athlete.age,
            general_stats=stats.get_category_stats("general"),
            passing_stats=stats.get_category_stats("passing"),
            rushing_stats=stats.get_category_stats("rushing"),
            scoring_stats=stats.get_category_stats("scoring"),
        )

    async def build_skill_players_async(self, athlete_ids: List[str], team_abbr: str) -> List[SkillPlayer]:
        async def build_single_player(athlete_id: str) -> SkillPlayer:
            athlete, stats = await asyncio.gather(
                self.get_athlete_info_async(athlete_id),
                self.get_athlete_stats_async(athlete_id)
            )
            return SkillPlayer(
                name=athlete.fullName,
                team=team_abbr,
                position=athlete.position.abbreviation,
                position_class="SKILL",
                height=int(athlete.height),
                weight=athlete.weight,
                age=athlete.age,
                general_stats=stats.get_category_stats("general"),
                rushing_stats=stats.get_category_stats("rushing"),
                receiving_stats=stats.get_category_stats("receiving"),
                scoring_stats=stats.get_category_stats("scoring"),
            )

        results = await asyncio.gather(
            *[build_single_player(aid) for aid in athlete_ids],
            return_exceptions=True
        )
        
        skill_players = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Warning: Failed to build skill player {athlete_ids[i]}: {result}")
            else:
                skill_players.append(result)
        
        return skill_players
    
    async def build_def_players_async(self, athlete_ids: List[str], team_abbr: str) -> List[DefPlayer]:
        async def build_single_player(athlete_id: str) -> DefPlayer:
            athlete, stats = await asyncio.gather(
                self.get_athlete_info_async(athlete_id),
                self.get_athlete_stats_async(athlete_id)
            )
            return DefPlayer(
                name=athlete.fullName,
                team=team_abbr,
                position=athlete.position.abbreviation,
                position_class="DEF",
                height=int(athlete.height),
                weight=athlete.weight,
                age=athlete.age,
                general_stats=stats.get_category_stats("general"),
                defensive_stats=stats.get_category_stats("defensive"),
            )

        results = await asyncio.gather(
            *[build_single_player(aid) for aid in athlete_ids],
            return_exceptions=True
        )
        
        def_players = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Warning: Failed to build defensive player {athlete_ids[i]}: {result}")
            else:
                def_players.append(result)
        
        return def_players


    def build_team(self, team_id: str) -> Team:
        return asyncio.run(self.build_team_async(team_id))

    async def build_team_async(self, team_id: str) -> Team:
        team_info = self.get_team_info(team_id)
        team_abbr = team_info.team.abbreviation

        depth_chart = self.get_team_depth_chart(team_id)

        qb_ids = depth_chart.get_starter_by_position("QB")
        if not qb_ids:
            raise ValueError(f"No QB found in depth chart for team {team_id}")
        qb_id = qb_ids[0]

        skill_ids = []
        skill_ids.extend(depth_chart.get_starter_by_position("RB"))
        skill_ids.extend(depth_chart.get_starter_by_position("WR", 3))
        skill_ids.extend(depth_chart.get_starter_by_position("TE"))

        def_ids = []
        def_ids.extend(depth_chart.get_starter_by_position("LDE"))
        def_ids.extend(depth_chart.get_starter_by_position("RDE"))
        def_ids.extend(depth_chart.get_starter_by_position("MLB"))
        def_ids.extend(depth_chart.get_starter_by_position("SLB"))
        def_ids.extend(depth_chart.get_starter_by_position("LCB"))

        qb_player, skill_players, def_players = await asyncio.gather(
            self.build_qb_player_async(qb_id, team_abbr),
            self.build_skill_players_async(skill_ids, team_abbr),
            self.build_def_players_async(def_ids, team_abbr)
        )

        return Team(
            name=team_info.team.displayName,
            abbreviation=team_abbr,
            rank=team_info.get_playoff_seed(),
            record=team_info.get_record_summary(),
            qb_player=qb_player,
            skill_stats=skill_players,
            def_players=def_players,
        )
