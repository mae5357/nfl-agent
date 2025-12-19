from nfl_agent.src.tools.team_lookup import get_team_info


def test_get_team_info():
    team_info = get_team_info.invoke({"team_name": "Kansas City Chiefs"})
    assert team_info is not None
