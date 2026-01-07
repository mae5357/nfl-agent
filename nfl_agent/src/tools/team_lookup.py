from langchain_core.tools import tool

from nfl_agent.src.models.stats import Team
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.utils import stats_mapper

# ESPN Team ID mapping (updated for 2025 season)
TEAM_NAME_TO_ID = {
    "arizona cardinals": "22",
    "atlanta falcons": "1",
    "baltimore ravens": "33",
    "buffalo bills": "2",
    "carolina panthers": "29",
    "chicago bears": "3",
    "cincinnati bengals": "4",
    "cleveland browns": "5",
    "dallas cowboys": "6",
    "denver broncos": "7",
    "detroit lions": "8",
    "green bay packers": "9",
    "houston texans": "34",
    "indianapolis colts": "11",
    "jacksonville jaguars": "30",
    "kansas city chiefs": "12",
    "las vegas raiders": "13",
    "los angeles chargers": "24",
    "los angeles rams": "14",
    "miami dolphins": "15",
    "minnesota vikings": "16",
    "new england patriots": "17",
    "new orleans saints": "18",
    "new york giants": "19",
    "new york jets": "20",
    "philadelphia eagles": "21",
    "pittsburgh steelers": "23",
    "san francisco 49ers": "25",
    "seattle seahawks": "26",
    "tampa bay buccaneers": "27",
    "tennessee titans": "10",
    "washington commanders": "28",
}


@tool
def get_team_info(team_name: str) -> Team:
    """Fetch NFL team information from ESPN by team name.

    team_name is case-insensitive and should be the full team name (e.g. "Kansas City Chiefs")
    """
    client = ESPNClient()

    # Normalize team name and look up ID
    team_name_lower = team_name.lower().strip()
    team_id = TEAM_NAME_TO_ID.get(team_name_lower)

    if not team_id:
        # Try partial match
        for name, tid in TEAM_NAME_TO_ID.items():
            if team_name_lower in name or name in team_name_lower:
                team_id = tid
                break

    if not team_id:
        available_teams = ", ".join(sorted(TEAM_NAME_TO_ID.keys()))
        raise ValueError(
            f"Team '{team_name}' not found. Available teams: {available_teams}"
        )

    team = stats_mapper.build_team_from_client(client, team_id)
    return team
