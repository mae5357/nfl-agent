from typing import Any

import httpx
from cachetools import cached
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from nfl_agent.src.utils.cache import teams_cache, standings_cache, roster_cache


class ESPNTeam(BaseModel):
    id: str
    displayName: str
    abbreviation: str
    name: str

    model_config = ConfigDict(extra="ignore")


class ESPNTeamRecord(BaseModel):
    """Extended team info including standings data."""

    id: str
    displayName: str
    abbreviation: str
    name: str
    record: str = "0-0-0"
    rank: int = 0

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def flatten_standing_entry(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Flatten ESPN standings entry: extract team info and parse stats."""
        if "team" not in data:
            return data

        team = data["team"]
        stats = {
            s["name"]: s.get("displayValue", s.get("value"))
            for s in data.get("stats", [])
        }

        return {
            **team,
            "record": stats.get("overall", "0-0-0"),
            "rank": int(stats.get("playoffSeed", 0) or 0),
        }


class ESPNPlayer(BaseModel):
    id: str
    fullName: str
    displayName: str
    position: str
    height: str
    weight: int
    age: int

    model_config = ConfigDict(extra="ignore")

    @field_validator("position", mode="before")
    @classmethod
    def parse_position(cls, v):
        if isinstance(v, dict):
            return v.get("abbreviation", "")
        return v

    @field_validator("height", mode="before")
    @classmethod
    def parse_height(cls, v):
        if isinstance(v, (int, float)):
            feet = int(v) // 12
            inches = int(v) % 12
            return f"{feet}'{inches}\""
        return v


class ESPNClient:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_multiplier: float = 1.0,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_multiplier = backoff_multiplier

    def _make_retry_decorator(self):
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_multiplier, min=1, max=10),
            reraise=True,
        )

    def _get(self, endpoint: str) -> dict[str, Any]:
        @self._make_retry_decorator()
        def _request():
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.BASE_URL}/{endpoint}")
                response.raise_for_status()
                return response.json()

        return _request()

    @cached(teams_cache)
    def get_teams(self) -> list[ESPNTeam]:
        data = self._get("teams")
        raw_teams = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        return [ESPNTeam(**group["team"]) for group in raw_teams]

    @cached(standings_cache)
    def _get_standings_map(self) -> dict[str, ESPNTeamRecord]:
        """Fetch teams with standings data, keyed by lowercase display name."""
        data = self._get("standings")
        return {
            record.displayName.lower(): record
            for group in data.get("children", [])
            for entry in group.get("standings", {}).get("entries", [])
            for record in [ESPNTeamRecord(**entry)]
        }

    def get_team_by_name(self, team_name: str) -> ESPNTeam | None:
        teams = self.get_teams()
        teams_map = {t.displayName.lower(): t for t in teams}
        return teams_map.get(team_name.lower())

    def get_team_with_record_by_name(self, team_name: str) -> ESPNTeamRecord | None:
        return self._get_standings_map().get(team_name.lower())

    def get_team_roster(self, team: ESPNTeam) -> list[ESPNPlayer]:
        return self._fetch_roster(team.id)

    @cached(roster_cache)
    def _fetch_roster(self, team_id: str) -> list[ESPNPlayer]:
        data = self._get(f"teams/{team_id}/roster")
        return [
            self.ESPNPlayer(**player)
            for group in data.get("athletes", [])
            for player in group.get("items", [])
        ]

    def find_player_in_roster(
        self, roster: list[ESPNPlayer], player_name: str
    ) -> ESPNPlayer | None:
        query = player_name.lower()
        exact = next(
            (p for p in roster if query in (p.fullName.lower(), p.displayName.lower())),
            None,
        )
        if exact:
            return exact
        return next(
            (
                p
                for p in roster
                if query in p.fullName.lower() or p.fullName.lower() in query
            ),
            None,
        )
