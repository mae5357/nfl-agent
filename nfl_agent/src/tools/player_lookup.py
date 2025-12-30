import asyncio
from typing import Union
from langchain_core.tools import tool

from nfl_agent.src.models.stats import QbPlayer, SkillPlayer, DefPlayer
from nfl_agent.src.utils.cache_utils import get_espn_client


@tool
def get_player_info(player_name: str) -> Union[QbPlayer, SkillPlayer, DefPlayer]:
    """Fetch NFL player information from ESPN by player name.

    Returns detailed player stats including position-specific metrics.
    player_name should be the player's full name or close match (e.g., "Patrick Mahomes")
    """
    client = get_espn_client()

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
    position_class = client._compute_position_class(position_abbr)

    if position_class == "QB":
        return asyncio.run(client.build_qb_player_async(athlete_id, team_abbr))
    elif position_class == "SKILL":
        return asyncio.run(client.build_skill_players_async([athlete_id], team_abbr))[0]
    elif position_class == "DEF":
        return asyncio.run(client.build_def_players_async([athlete_id], team_abbr))[0]
    else:
        raise ValueError(f"Unknown position class: {position_class}")
