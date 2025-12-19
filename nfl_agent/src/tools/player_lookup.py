import re

from langchain_core.tools import tool

from nfl_agent.src.models.stats import Player
from nfl_agent.src.utils.cache import get_espn_client
from nfl_agent.src.utils.client import ESPNPlayer


def _parse_height_to_inches(height_str: str) -> int:
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


@tool
def get_player_info(player_name: str, team_name: str) -> Player:
    """Fetch NFL player information from ESPN by player name and team name.

    player name and team name are case-insensitive
    """
    client = get_espn_client()
    team = client.get_team_by_name(team_name)
    if not team:
        raise ValueError(f"Team '{team_name}' not found")

    roster = client.get_team_roster(team)
    player_data = client.find_player_in_roster(roster, player_name)
    if not player_data:
        raise ValueError(f"Player '{player_name}' not found on team '{team_name}'")

    return _extract_player_data(player_data, team.displayName)
