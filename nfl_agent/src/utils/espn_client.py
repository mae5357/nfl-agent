"""ESPN API client for fetching NFL team and player data."""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


from nfl_agent.src.models.espn_responses import (
    ESPNAthleteResponse,
    ESPNStatisticsResponse,
    ESPNTeamResponse,
    ESPNDepthChartResponse,
    ESPNScoreboardResponse,
    ESPNScheduleResponse,
    NormalizedGame,
)
from nfl_agent.src.models.espn_search import ESPNSearchResponse, ESPNSearchArticle
from nfl_agent.src.utils.client_protocol import StatsClientProtocol


class ESPNClient(StatsClientProtocol):
    """Client for ESPN Core API endpoints."""

    CORE_API_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    SITE_API_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    SEARCH_API_URL = "https://site.web.api.espn.com/apis/search/v2"
    CDN_API_URL = "https://cdn.espn.com/core/nfl"

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
        self._team_name_to_id: Optional[Dict[str, str]] = None

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

    def _get_cdn_api(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the CDN API."""

        @self._make_retry_decorator()
        def _request():
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self.CDN_API_URL}/{endpoint}"
                response = client.get(url, params=params or {})
                response.raise_for_status()
                return response.json()

        return _request()

    def get_team_info(self, team_id: str) -> ESPNTeamResponse:
        endpoint = f"seasons/{self.season}/teams/{team_id}"
        data = self._get_core_api(endpoint)
        return ESPNTeamResponse(**data)

    def get_team_depth_chart(self, team_id: str) -> ESPNDepthChartResponse:
        endpoint = f"seasons/{self.season}/teams/{team_id}/depthcharts"
        data = self._get_core_api(endpoint)
        return ESPNDepthChartResponse(**data)

    def _load_team_mapping(self) -> Dict[str, str]:
        """
        Fetch and cache the mapping of team display names to IDs.

        Uses endpoint: https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
        """
        if self._team_name_to_id is not None:
            return self._team_name_to_id

        data = self._get_site_api("teams")

        team_mapping: Dict[str, str] = {}

        # Navigate: sports[0].leagues[0].teams[].team
        sports = data.get("sports", [])
        if sports:
            leagues = sports[0].get("leagues", [])
            if leagues:
                teams = leagues[0].get("teams", [])
                for team_entry in teams:
                    team = team_entry.get("team", {})
                    team_id = team.get("id")
                    display_name = team.get("displayName")
                    if team_id and display_name:
                        team_mapping[display_name] = team_id

        self._team_name_to_id = team_mapping
        return team_mapping

    def get_team_id(self, team_name: str) -> Optional[str]:
        """
        Get the ESPN team ID for a given team display name.

        Args:
            team_name: Full team name (e.g., "Arizona Cardinals", "Philadelphia Eagles")

        Returns:
            Team ID string (e.g., "22", "10") or None if not found

        Example:
            client.get_team_id("Arizona Cardinals")  # Returns "22"
            client.get_team_id("Philadelphia Eagles")  # Returns "21"
        """
        team_mapping = self._load_team_mapping()
        return team_mapping.get(team_name)

    async def get_athlete_info_async(self, athlete_id: str) -> ESPNAthleteResponse:
        endpoint = f"seasons/{self.season}/athletes/{athlete_id}"
        data = await self._get_core_api_async(endpoint)
        return ESPNAthleteResponse(**data)

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

    def get_athlete_info(self, athlete_id: str) -> ESPNAthleteResponse:
        return asyncio.run(self.get_athlete_info_async(athlete_id))

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
        self,
        team_id: Optional[int] = None,
        max_articles: int = 50,
        content_types: Optional[List[str]] = None,
        search_before: Optional[datetime] = None,
    ) -> ESPNSearchResponse:
        """
        Get NFL news articles from ESPN, optionally filtered by team.

        Args:
            team_id: ESPN team ID to filter articles (e.g., 10 for Eagles)
                     If None, returns latest NFL news across all teams
            max_articles: Maximum number of articles to fetch from API (default: 50)
            content_types: Filter by content type(s), e.g., ["Story", "Recap", "Media"]

        Returns:
            ESPNSearchResponse with header and filtered articles

        Example:
            # Get Eagles news
            client.search_nfl(team_id=10)

            # Get all NFL news
            client.search_nfl()
        """

        @self._make_retry_decorator()
        def _search():
            params = {
                "limit": max_articles,
            }
            if team_id is not None:
                params["team"] = team_id

            with httpx.Client(timeout=self.timeout) as client:
                # ESPN NFL News API endpoint
                url = f"{self.SITE_API_URL}/news"
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Parse articles from response
                articles_data = data.get("articles", [])

                # Exclude "Media" type articles by default
                articles_data = [a for a in articles_data if a.get("type") != "Media"]
                # if search_before is provided, filter articles before that date
                if search_before:

                    def _is_before_search_before(article):
                        published = article.get("published")
                        if not published:
                            return False
                        dt = datetime.fromisoformat(published)
                        # Make both datetimes naive (UTC) or both aware (UTC)
                        if dt.tzinfo is not None and search_before.tzinfo is None:
                            dt = dt.astimezone(tz=None).replace(tzinfo=None)
                        elif dt.tzinfo is None and search_before.tzinfo is not None:
                            # Assume published is UTC if it's naive
                            dt = dt.replace(tzinfo=search_before.tzinfo)
                        return dt < search_before

                    articles_data = [
                        a for a in articles_data if _is_before_search_before(a)
                    ]
                # Parse into Pydantic models
                articles = [ESPNSearchArticle(**a) for a in articles_data]

                return ESPNSearchResponse(
                    header=data.get("header", "NFL News"), articles=articles
                )

        return _search()

    def get_weekly_games(
        self,
        year: Optional[str] = None,
        week: Optional[int] = None,
        season_type: Optional[str] = None,
    ) -> List[NormalizedGame]:
        """
        Get all games for a specific week of a season.

        Tries the site.api scoreboard endpoint first (Option A).
        Falls back to cdn schedule endpoint if that fails (Option B).

        Args:
            year: Season year (defaults to client's season)
            week: Week number (1-18 for regular season)
            season_type: Season type (1=preseason, 2=regular, 3=postseason)
                        Defaults to client's season_type

        Returns:
            List of normalized games

        Examples:
            # Get week 16 of 2025 regular season
            games = client.get_weekly_games(year="2025", week=16, season_type="2")

            # Use defaults from client initialization
            games = client.get_weekly_games(week=16)
        """
        year = year or self.season
        season_type = season_type or self.season_type
        week = week or 1

        # Try Option A: site.api scoreboard
        try:
            games = self._get_games_from_scoreboard(year, week, season_type)
            if games:
                return games
        except Exception as e:
            print(
                f"Scoreboard endpoint failed: {e}. Falling back to schedule endpoint."
            )

        # Fallback to Option B: cdn schedule
        try:
            games = self._get_games_from_schedule(year, week)
            return games
        except Exception as e:
            print(f"Schedule endpoint also failed: {e}")
            raise Exception(
                "Failed to fetch games from both scoreboard and schedule endpoints"
            ) from e

    def _get_games_from_scoreboard(
        self, year: str, week: int, season_type: str
    ) -> List[NormalizedGame]:
        """
        Get games from the site.api scoreboard endpoint.

        Endpoint: https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
        """
        params = {
            "limit": 1000,
            "dates": year,
            "seasontype": season_type,
            "week": week,
        }

        data = self._get_site_api("scoreboard", params=params)
        scoreboard = ESPNScoreboardResponse(**data)

        return self._normalize_games_from_scoreboard(scoreboard)

    def _get_games_from_schedule(self, year: str, week: int) -> List[NormalizedGame]:
        """
        Get games from the cdn schedule endpoint.

        Endpoint: https://cdn.espn.com/core/nfl/schedule
        """
        params = {
            "xhr": 1,
            "year": year,
            "week": week,
        }

        data = self._get_cdn_api("schedule", params=params)
        schedule = ESPNScheduleResponse(**data)

        return self._normalize_games_from_schedule(schedule)

    def _normalize_games_from_scoreboard(
        self, scoreboard: ESPNScoreboardResponse
    ) -> List[NormalizedGame]:
        """Normalize scoreboard response into standard game format."""
        games = []

        for event in scoreboard.events:
            home_team = event.get_home_team()
            away_team = event.get_away_team()

            if not home_team or not away_team:
                continue

            normalized = NormalizedGame(
                event_id=event.get_event_id(),
                kickoff_utc=event.get_kickoff_datetime(),
                home_team_id=home_team.get_team_id(),
                home_team_name=home_team.get_team_name(),
                home_team_abbr=home_team.get_team_abbr(),
                home_score=home_team.score,
                away_team_id=away_team.get_team_id(),
                away_team_name=away_team.get_team_name(),
                away_team_abbr=away_team.get_team_abbr(),
                away_score=away_team.score,
                venue=event.get_venue_name(),
                status=event.status.get_state() if event.status else "scheduled",
            )

            games.append(normalized)

        return games

    def _normalize_games_from_schedule(
        self, schedule: ESPNScheduleResponse
    ) -> List[NormalizedGame]:
        """Normalize schedule response into standard game format."""
        games = []

        for game in schedule.get_games():
            home_team = game.get_home_team()
            away_team = game.get_away_team()

            if not home_team or not away_team:
                continue

            normalized = NormalizedGame(
                event_id=game.get_event_id(),
                kickoff_utc=game.get_kickoff_datetime(),
                home_team_id=home_team.get_team_id(),
                home_team_name=home_team.get_team_name(),
                home_team_abbr=home_team.get_team_abbr(),
                home_score=home_team.score,
                away_team_id=away_team.get_team_id(),
                away_team_name=away_team.get_team_name(),
                away_team_abbr=away_team.get_team_abbr(),
                away_score=away_team.score,
                venue=None,  # Schedule endpoint doesn't include venue
                status="scheduled",  # Schedule endpoint doesn't include status
            )

            games.append(normalized)

        return games

    def get_game_summary(self, event_id: str) -> Dict[str, Any]:
        """
        Get detailed game summary for a specific event.

        Endpoint: https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary

        Args:
            event_id: ESPN event/game ID

        Returns:
            Raw game summary data (boxscore, plays, etc.)
        """
        params = {"event": event_id}
        return self._get_site_api("summary", params=params)

    def get_game_odds(
        self, event_id: str, provider_id: str = "38"
    ) -> Optional[Dict[str, Any]]:
        """
        Get betting odds for a specific game.

        Endpoint: https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event_id}/competitions/{event_id}/odds

        Args:
            event_id: ESPN event/game ID
            provider_id: Odds provider ID (default "38" = Caesars)
                - "38": Caesars
                - "1002": teamrankings
                - "1003": numberfire (ESPN BPI)

        Returns:
            Dict with spread and odds data, or None if not found:
            {
                "provider": "Caesars",
                "spread": -1.0,  # Home team spread (negative = home favored)
                "over_under": 50.5,
                "home_spread_odds": -110,
                "away_spread_odds": -110,
                "home_moneyline": -120,
                "away_moneyline": 100,
            }
        """
        endpoint = f"events/{event_id}/competitions/{event_id}/odds"

        @self._make_retry_decorator()
        def _request():
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self.CORE_API_URL}/{endpoint}"
                response = client.get(url)
                response.raise_for_status()
                return response.json()

        try:
            data = _request()
        except Exception as e:
            print(f"Failed to fetch odds for event {event_id}: {e}")
            return None

        # Find the requested provider in the items list
        items = data.get("items", [])
        provider_data = None

        for item in items:
            provider = item.get("provider", {})
            if provider.get("id") == provider_id:
                provider_data = item
                break

        if not provider_data:
            # Fallback to first available provider
            if items:
                provider_data = items[0]
            else:
                return None

        # Extract odds data
        result = {
            "provider": provider_data.get("provider", {}).get("name", "Unknown"),
            "spread": provider_data.get("spread"),
            "over_under": provider_data.get("overUnder"),
            "details": provider_data.get("details"),  # e.g., "TEN -1"
        }

        # Extract home team odds
        home_odds = provider_data.get("homeTeamOdds", {})
        result["home_spread_odds"] = home_odds.get("spreadOdds")
        result["home_moneyline"] = home_odds.get("moneyLine")
        result["home_favorite"] = home_odds.get("favorite", False)

        # Extract away team odds
        away_odds = provider_data.get("awayTeamOdds", {})
        result["away_spread_odds"] = away_odds.get("spreadOdds")
        result["away_moneyline"] = away_odds.get("moneyLine")
        result["away_favorite"] = away_odds.get("favorite", False)

        return result

    def get_weekly_matchups(
        self,
        year: Optional[str] = None,
        week: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Get simplified matchup list for a specific week.

        Endpoint: https://cdn.espn.com/core/nfl/schedule?xhr=1&year={year}&week={week}

        Args:
            year: Season year (defaults to client's season)
            week: Week number (1-18 for regular season)

        Returns:
            List of matchups with home_team and away_team names

        Example:
            matchups = client.get_weekly_matchups(year="2025", week=18)
            # [{"home_team": "Philadelphia Eagles", "away_team": "New York Giants"}, ...]
        """
        games = self.get_weekly_games(year=year, week=week)

        return [
            {
                "home_team": game.home_team_name,
                "away_team": game.away_team_name,
            }
            for game in games
        ]
