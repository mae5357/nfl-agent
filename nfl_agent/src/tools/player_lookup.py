from langchain_core.tools import tool

from nfl_agent.src.models.stats import Player
from nfl_agent.src.tools.team_lookup import get_team_info


@tool
def get_player_info(player_name: str, team_name: str) -> Player:
    """Fetch NFL player information from ESPN by player name and team name.

    player name and team name are case-insensitive
    
    This tool searches for the player within the team's key players (QB, skill players, defensive player).
    """
    # Get team data which includes key players
    team = get_team_info.invoke({"team_name": team_name})
    
    # Search for player in team's key players
    player_name_lower = player_name.lower().strip()
    
    # Check QB
    if player_name_lower in team.qb_player.name.lower():
        return team.qb_player
    
    # Check skill players
    for skill_player in team.skill_stats:
        if player_name_lower in skill_player.name.lower():
            return skill_player
    
    # Check defensive player
    if team.def_player and player_name_lower in team.def_player.name.lower():
        return team.def_player
    
    # Check injured players
    for injured_player in team.injured_players:
        if player_name_lower in injured_player.name.lower():
            return injured_player
    
    # Player not found in key players
    raise ValueError(
        f"Player '{player_name}' not found in {team_name}'s key players. "
        f"Note: This tool only searches QB, top skill players (RB/WR/TE), and defensive player."
    )
