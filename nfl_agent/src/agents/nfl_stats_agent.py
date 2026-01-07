from nfl_agent.src.utils.settings import get_setting, NFLAgentSettings, get_chat_model
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from nfl_agent.src.tools import search_nfl, get_team_info, get_player_info


def create_nfl_stats_agent():
    from nfl_agent.prompts.probability.v1 import PROMPT
    from nfl_agent.prompts.probability.schema import ProbabilityResponse

    settings = get_setting(NFLAgentSettings)
    model = get_chat_model(settings)

    agent = create_agent(
        model=model,
        system_prompt=PROMPT,
        tools=[search_nfl, get_team_info, get_player_info],
        response_format=ProviderStrategy(ProbabilityResponse, strict=True),
    )
    return agent
