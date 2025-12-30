from nfl_agent.src.tools.player_lookup import get_player_info


def test_get_player_info():
    # Test with a well-known QB
    player_info = get_player_info.invoke({"player_name": "Patrick Mahomes"})
    assert player_info is not None
    assert player_info.position == "QB"

    import json

    with open("player_info.json", "w") as f:
        json.dump(player_info.model_dump(mode="json"), f, indent=4)


def test_get_skill_player_info():
    # Test with a skill position player
    player_info = get_player_info.invoke({"player_name": "Travis Kelce"})
    assert player_info is not None
    assert player_info.position_class == "SKILL"

    import json

    with open("skill_player_info.json", "w") as f:
        json.dump(player_info.model_dump(mode="json"), f, indent=4)


def test_get_defensive_player_info():
    # Test with a defensive player
    player_info = get_player_info.invoke({"player_name": "Micah Parsons"})
    assert player_info is not None
    assert player_info.position_class == "DEF"

    import json

    with open("def_player_info.json", "w") as f:
        json.dump(player_info.model_dump(mode="json"), f, indent=4)
