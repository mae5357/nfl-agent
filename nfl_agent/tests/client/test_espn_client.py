import json
import os
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.models.espn_responses import ESPNDepthChartResponse
from pytest import fixture


@fixture
def espn_client():
    return ESPNClient()

@fixture
def depth_chart() -> ESPNDepthChartResponse:
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data", "espn_depth_chart_response.json"), "r") as f:
        return ESPNDepthChartResponse(**json.load(f))



def test_get_team_depth_chart(espn_client: ESPNClient, depth_chart: ESPNDepthChartResponse):
    response = espn_client.get_team_depth_chart(team_id="1")
    assert response == depth_chart

def test_build_team(espn_client: ESPNClient):
    team = espn_client.build_team(team_id="21")
    assert team is not None

def test_search_nfl(espn_client):
    response = espn_client.search_nfl(query="Kansas City Chiefs latest news", limit=10)
    assert response is not None
