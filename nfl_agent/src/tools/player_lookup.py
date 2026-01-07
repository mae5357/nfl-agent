import asyncio
from typing import Union
from langchain_core.tools import tool

from nfl_agent.src.models.stats import QbPlayer, SkillPlayer, DefPlayer
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.utils import stats_mapper


@tool
def get_player_info(player_name: str) -> Union[QbPlayer, SkillPlayer, DefPlayer]:
    """Fetch NFL player information from ESPN by player name.

    Returns detailed player stats including position-specific metrics.
    player_name should be the player's full name or close match (e.g., "Patrick Mahomes")
    """
    client = ESPNClient()

    search_results = client.search_athletes(player_name, limit=5)

    if not search_results:
        raise ValueError(
            f"Player '{player_name}' not found. Please check the spelling and try again."
        )

    player_result = search_results[0]
    athlete_id = player_result["id"]
    team_abbr = player_result["team"] or "UNK"

    if not athlete_id:
        raise ValueError(f"Could not find athlete ID for '{player_name}'")

    athlete_info = client.get_athlete_info(athlete_id)
    position_abbr = athlete_info.position.abbreviation
    position_class = stats_mapper.compute_position_class(position_abbr)

    if position_class == "QB":
        return asyncio.run(
            stats_mapper.build_qb_player_from_client_async(
                client, athlete_id, team_abbr
            )
        )
    elif position_class == "SKILL":
        players = asyncio.run(
            stats_mapper.build_skill_players_from_client_async(
                client, [athlete_id], team_abbr
            )
        )
        return players[0]
    elif position_class == "DEF":
        players = asyncio.run(
            stats_mapper.build_def_players_from_client_async(
                client, [athlete_id], team_abbr
            )
        )
        return players[0]
    else:
        raise ValueError(f"Unknown position class: {position_class}")
