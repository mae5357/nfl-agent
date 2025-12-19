from nfl_agent.src.tools.player_lookup import get_player_info


def test_get_player_info():
    player_info = get_player_info.invoke(
        {"player_name": "Patrick Mahomes", "team_name": "Kansas City Chiefs"}
    )
    assert player_info is not None
