import pytest
from unittest.mock import AsyncMock, MagicMock

from nfl_agent.src.utils import stats_mapper
from nfl_agent.src.models.espn_responses import (
    ESPNAthleteResponse,
    ESPNStatisticsResponse,
    ESPNSplits,
    ESPNStatCategory,
    ESPNStat,
    ESPNPosition,
)
from nfl_agent.src.models.stats import QbPlayer, SkillPlayer


def test_compute_position_class():
    assert stats_mapper.compute_position_class("QB") == "QB"
    assert stats_mapper.compute_position_class("WR") == "SKILL"
    assert stats_mapper.compute_position_class("RB") == "SKILL"
    assert stats_mapper.compute_position_class("TE") == "SKILL"
    assert stats_mapper.compute_position_class("DE") == "DEF"
    assert stats_mapper.compute_position_class("LB") == "DEF"
    assert stats_mapper.compute_position_class("C") == "OL"
    assert stats_mapper.compute_position_class("LT") == "OL"


def test_map_injury_status():
    from nfl_agent.src.models.espn_responses import ESPNInjury, ESPNInjuryType

    injury_out = ESPNInjury(
        status="Out", type=ESPNInjuryType(id="1", name="INJURY_STATUS_OUT")
    )
    assert stats_mapper.map_injury_status([injury_out]) == "out"

    injury_questionable = ESPNInjury(
        status="Questionable",
        type=ESPNInjuryType(id="2", name="INJURY_STATUS_QUESTIONABLE"),
    )
    assert stats_mapper.map_injury_status([injury_questionable]) == "questionable"

    assert stats_mapper.map_injury_status([]) == "active"


@pytest.mark.asyncio
async def test_build_qb_player_from_client_async():
    mock_client = MagicMock()

    mock_athlete = ESPNAthleteResponse(
        id="123",
        fullName="Test QB",
        height=75.0,
        weight=220.0,
        age=28,
        position=ESPNPosition(abbreviation="QB"),
        team={},
        injuries=[],
    )

    mock_stats = ESPNStatisticsResponse(
        splits=ESPNSplits(
            categories=[
                ESPNStatCategory(
                    name="passing",
                    displayName="Passing",
                    stats=[
                        ESPNStat(
                            displayName="Passing Yards", description="", value=3500.0
                        ),
                        ESPNStat(
                            displayName="Passing Attempts", description="", value=500.0
                        ),
                        ESPNStat(
                            displayName="Completions", description="", value=350.0
                        ),
                        ESPNStat(
                            displayName="Completion Percentage",
                            description="",
                            value=70.0,
                        ),
                        ESPNStat(
                            displayName="Passer Rating", description="", value=95.0
                        ),
                        ESPNStat(
                            displayName="Net Yards Per Pass Attempt",
                            description="",
                            value=7.0,
                        ),
                        ESPNStat(
                            displayName="Passing Touchdowns", description="", value=25.0
                        ),
                        ESPNStat(
                            displayName="Interceptions", description="", value=10.0
                        ),
                        ESPNStat(displayName="Total Sacks", description="", value=20.0),
                    ],
                ),
                ESPNStatCategory(
                    name="general",
                    displayName="General",
                    stats=[
                        ESPNStat(displayName="Fumbles Lost", description="", value=2.0),
                    ],
                ),
            ]
        )
    )

    mock_client.get_athlete_info_async = AsyncMock(return_value=mock_athlete)
    mock_client.get_athlete_stats_async = AsyncMock(return_value=mock_stats)

    qb_player = await stats_mapper.build_qb_player_from_client_async(
        mock_client, "123", "PHI"
    )

    assert isinstance(qb_player, QbPlayer)
    assert qb_player.name == "Test QB"
    assert qb_player.team == "PHI"
    assert qb_player.position == "QB"
    assert qb_player.position_class == "QB"
    assert qb_player.passing_yards.value == 3500.0


@pytest.mark.asyncio
async def test_build_skill_players_from_client_async():
    mock_client = MagicMock()

    mock_athlete = ESPNAthleteResponse(
        id="456",
        fullName="Test WR",
        height=72.0,
        weight=200.0,
        age=25,
        position=ESPNPosition(abbreviation="WR"),
        team={},
        injuries=[],
    )

    mock_stats = ESPNStatisticsResponse(
        splits=ESPNSplits(
            categories=[
                ESPNStatCategory(
                    name="receiving",
                    displayName="Receiving",
                    stats=[
                        ESPNStat(
                            displayName="Receiving Targets", description="", value=100.0
                        ),
                        ESPNStat(displayName="Receptions", description="", value=70.0),
                        ESPNStat(
                            displayName="Receiving Yards", description="", value=1000.0
                        ),
                        ESPNStat(
                            displayName="Receiving Touchdowns",
                            description="",
                            value=8.0,
                        ),
                    ],
                ),
                ESPNStatCategory(
                    name="general",
                    displayName="General",
                    stats=[
                        ESPNStat(
                            displayName="Games Played", description="", value=16.0
                        ),
                        ESPNStat(displayName="Fumbles Lost", description="", value=1.0),
                    ],
                ),
            ]
        )
    )

    mock_client.get_athlete_info_async = AsyncMock(return_value=mock_athlete)
    mock_client.get_athlete_stats_async = AsyncMock(return_value=mock_stats)

    skill_players = await stats_mapper.build_skill_players_from_client_async(
        mock_client, ["456"], "KC"
    )

    assert len(skill_players) == 1
    assert isinstance(skill_players[0], SkillPlayer)
    assert skill_players[0].name == "Test WR"
    assert skill_players[0].team == "KC"
    assert skill_players[0].position == "WR"
    assert skill_players[0].position_class == "SKILL"
    assert skill_players[0].targets == 100
    assert skill_players[0].receptions == 70
    assert skill_players[0].receiving_yards == 1000
