from langchain_core.tools import tool

from nfl_agent.src.models.stats import Team, Player
from nfl_agent.src.utils.cache import get_espn_client
from nfl_agent.src.utils.client import ESPNPlayer


def _parse_height_to_inches(height_str: str) -> int:
    import re

    match = re.match(r"(\d+)'(\d+)\"?", height_str)
    if match:
        feet = int(match.group(1))
        inches = int(match.group(2))
        return feet * 12 + inches
    return 0


def _extract_player_data(player_data: ESPNPlayer, team_name: str) -> Player:
    return Player(
        name=player_data.fullName,
        team=team_name,
        position=player_data.position,
        height=_parse_height_to_inches(player_data.height),
        weight=player_data.weight,
        age=player_data.age,
        is_injured=False,
        key_stats=[],
    )


def _get_key_players(
    roster: list[ESPNPlayer], team_name: str, limit: int = 5
) -> list[Player]:
    """Extract key players from roster (prioritize QB, RB, WR positions)."""
    priority_positions = ["QB", "RB", "WR", "TE", "LB", "CB", "DE"]
    key_players: list[Player] = []

    for position in priority_positions:
        for player in roster:
            if player.position == position and len(key_players) < limit:
                key_players.append(_extract_player_data(player, team_name))
        if len(key_players) >= limit:
            break

    return key_players


@tool
def get_team_info(team_name: str) -> Team:
    """Fetch NFL team information from ESPN by team name.

    team_name is case-insensitive and should be the full team name (e.g. "Kansas City Chiefs")
    """
    client = get_espn_client()
    team_data = client.get_team_with_record_by_name(team_name)
    if not team_data:
        raise ValueError(f"Team '{team_name}' not found")

    # Get roster for key players
    basic_team = client.get_team_by_name(team_name)
    roster = client.get_team_roster(basic_team)
    key_players = _get_key_players(roster, team_data.displayName)

    return Team(
        name=team_data.displayName,
        abbreviation=team_data.abbreviation,
        rank=team_data.rank,
        record=team_data.record,
        key_players=key_players,
    )
