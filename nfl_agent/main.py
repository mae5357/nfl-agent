import json
from nfl_agent.src.agents.nfl_stats_agent import create_nfl_stats_agent
from nfl_agent.src.utils.cli import select_game_from_week
from dotenv import load_dotenv
from langchain_core.messages import AIMessage

load_dotenv()


def pretty_print_prediction(game, prediction_data):
    """
    Pretty print the prediction results with reasoning.

    Args:
        game: NormalizedGame object
        prediction_data: Dict containing prediction data from agent
    """
    away_team = game.away_team_abbr or game.away_team_name or game.away_team_id
    home_team = game.home_team_abbr or game.home_team_name or game.home_team_id

    home_prob = prediction_data.get("home_team_probability", 0)
    away_prob = prediction_data.get("away_team_probability", 0)

    # Normalize probabilities if they're in 0-100 range
    if home_prob > 1:
        home_prob = home_prob / 100
    if away_prob > 1:
        away_prob = away_prob / 100

    home_summary = prediction_data.get("home_team_summary", "")
    away_summary = prediction_data.get("away_team_summary", "")

    print("\n" + "=" * 80)
    print(f"PREDICTION: {away_team} @ {home_team}")
    print("=" * 80)

    print("\nWIN PROBABILITIES:")
    print(f"  {home_team}: {home_prob:.1%}")
    print(f"  {away_team}: {away_prob:.1%}")

    if home_summary:
        print(f"\n{home_team} ANALYSIS:")
        print(f"  {home_summary}")

    if away_summary:
        print(f"\n{away_team} ANALYSIS:")
        print(f"  {away_summary}")

    print("\n" + "=" * 80 + "\n")


def extract_prediction_from_agent_response(agent_response):
    """
    Extract the ProbabilityResponse from agent's message response.

    Args:
        agent_response: Response dict from agent.invoke()

    Returns:
        Dict with prediction data or None if not found
    """
    messages = agent_response.get("messages", [])

    # Find the final AI message with the prediction
    for msg in reversed(messages):
        # Handle both LangChain message objects and dict representations
        if isinstance(msg, AIMessage):
            content = msg.content
        elif isinstance(msg, dict):
            # Handle dict format (from serialized messages)
            if msg.get("type") == "ai":
                content = msg.get("data", {}).get("content") or msg.get("content")
            else:
                continue
        else:
            # Try to access as attribute if it's a message-like object
            if (
                hasattr(msg, "content")
                and hasattr(msg, "type")
                and getattr(msg, "type", None) == "ai"
            ):
                content = msg.content
            else:
                continue

        if content:
            try:
                # Try to parse as JSON
                prediction = json.loads(content)
                # Verify it has the expected fields
                if (
                    "home_team_probability" in prediction
                    and "away_team_probability" in prediction
                ):
                    return prediction
            except (json.JSONDecodeError, TypeError):
                # If content is already a dict, check if it has the right structure
                if isinstance(content, dict):
                    if (
                        "home_team_probability" in content
                        and "away_team_probability" in content
                    ):
                        return content
                continue

    return None


def main():
    """Main entry point for NFL stats agent CLI."""
    try:
        # Get game selection from user
        game = select_game_from_week()

        # Create agent
        print("\nInitializing agent...")
        agent = create_nfl_stats_agent()

        # Format game matchup
        away_team = game.away_team_name or game.away_team_abbr or game.away_team_id
        home_team = game.home_team_name or game.home_team_abbr or game.home_team_id
        matchup = f"{home_team} vs. {away_team}"

        print(f"\nAnalyzing {matchup}...")
        print("This may take a moment as the agent gathers information...\n")

        # Invoke agent
        result = agent.invoke({"messages": [{"role": "user", "content": matchup}]})

        # Extract prediction
        prediction = extract_prediction_from_agent_response(result)

        if prediction:
            pretty_print_prediction(game, prediction)
        else:
            print("\n⚠️  Warning: Could not extract prediction from agent response.")
            print("Raw response messages:")
            print(json.dumps(result.get("messages", []), indent=2))

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == "__main__":
    main()
