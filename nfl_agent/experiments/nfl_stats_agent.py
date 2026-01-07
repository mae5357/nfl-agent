from nfl_agent.src.agents.nfl_stats_agent import create_nfl_stats_agent
from pathlib import Path
import json
from dotenv import load_dotenv
from nfl_agent.src.utils.espn_client import ESPNClient
from langchain_core.messages import messages_to_dict
import time

load_dotenv()


def main():
    week = 18
    agent = create_nfl_stats_agent()

    # get all games for this week
    client = ESPNClient()
    games = client.get_weekly_games(week=week)
    for game in games:
        # check to see if the file already exists
        output_path = (
            Path(__file__).parent
            / "artifacts"
            / "nfl_stats_agent_v1"
            / f"{'_'.join(game.home_team_name.split(' '))}_{'_'.join(game.away_team_name.split(' '))}_week_{week}.json"
        )
        if output_path.exists():
            print(
                f"Skipping {game.home_team_name} vs. {game.away_team_name} because it already exists"
            )
            continue

        print(game.home_team_name, game.away_team_name)
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"{game.home_team_name} vs. {game.away_team_name}",
                    }
                ]
            }
        )

        # save to nfl_stats_agent folder
        output_path.parent.mkdir(parents=True, exist_ok=True)
        serializable_result = {"messages": messages_to_dict(result["messages"])}
        with open(output_path, "w") as f:
            json.dump(serializable_result, f, indent=4)

        # sleep for 5 seconds
        time.sleep(5)


if __name__ == "__main__":
    main()
