import json
import os
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.utils import stats_mapper
from nfl_agent.src.models.espn_responses import ESPNDepthChartResponse
from pytest import fixture


@fixture
def espn_client():
    return ESPNClient()


@fixture
def depth_chart() -> ESPNDepthChartResponse:
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "test_data",
            "espn_depth_chart_response.json",
        ),
        "r",
    ) as f:
        return ESPNDepthChartResponse(**json.load(f))


def test_get_team_depth_chart(
    espn_client: ESPNClient, depth_chart: ESPNDepthChartResponse
):
    response = espn_client.get_team_depth_chart(team_id="1")
    assert response is not None


def test_build_team(espn_client: ESPNClient):
    team = stats_mapper.build_team_from_client(espn_client, team_id="21")
    assert team is not None


def test_search_nfl(espn_client):
    # team_id=12 is Kansas City Chiefs
    response = espn_client.search_nfl(team_id=12, max_articles=10)
    assert response is not None


def test_get_list_of_articles(espn_client: ESPNClient):
    # team_id=21 is Philadelphia Eagles
    articles = espn_client.search_nfl(team_id=21)
    assert articles is not None
