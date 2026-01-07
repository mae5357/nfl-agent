"""Compare NFL stats agent predictions against betting spreads."""

import json
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def load_agent_predictions(predictions_dir: Path, week: int) -> list[dict]:
    """
    Load agent predictions from JSON files.

    Args:
        predictions_dir: Directory containing agent prediction files
        week: Week number to filter files

    Returns:
        List of prediction dicts with home_team, away_team, and probabilities
    """
    predictions = []
    pattern = f"*_week_{week}.json"

    for filepath in predictions_dir.glob(pattern):
        try:
            with open(filepath) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Skipping invalid JSON file {filepath.name}: {e}")
            continue

        # Extract team names from filename (e.g., Home_Team_Away_Team_week_18.json)
        filename = filepath.stem  # e.g., "Atlanta_Falcons_New_Orleans_Saints_week_18"
        filename.replace(f"_week_{week}", "").split("_")

        # Find the split point between home and away team names
        # This is tricky because team names can have multiple words
        # We'll parse from the agent output instead

        # Get the final AI message content (the prediction)
        messages = data.get("messages", [])
        final_prediction = None

        for msg in reversed(messages):
            if msg.get("type") == "ai" and msg.get("data", {}).get("content"):
                content = msg["data"]["content"]
                if content:
                    try:
                        final_prediction = json.loads(content)
                        break
                    except json.JSONDecodeError:
                        continue

        if not final_prediction:
            print(f"Warning: Could not parse prediction from {filepath}")
            continue

        # Get team names from the human message
        human_msg = None
        for msg in messages:
            if msg.get("type") == "human":
                human_msg = msg.get("data", {}).get("content", "")
                break

        if human_msg:
            # Parse "Team A vs. Team B" or "Team A vs Team B"
            match = re.match(r"(.+?)\s+vs\.?\s+(.+)", human_msg)
            if match:
                home_team = match.group(1).strip()
                away_team = match.group(2).strip()
            else:
                home_team = human_msg
                away_team = "Unknown"
        else:
            home_team = "Unknown"
            away_team = "Unknown"

        # Normalize probabilities to 0-1 range (some models output 0-100)
        home_prob = final_prediction.get("home_team_probability")
        away_prob = final_prediction.get("away_team_probability")

        if home_prob is not None and home_prob > 1:
            home_prob = home_prob / 100
        if away_prob is not None and away_prob > 1:
            away_prob = away_prob / 100

        predictions.append(
            {
                "home_team": home_team,
                "away_team": away_team,
                "home_probability": home_prob,
                "away_probability": away_prob,
                "home_summary": final_prediction.get("home_team_summary", ""),
                "away_summary": final_prediction.get("away_team_summary", ""),
                "filepath": str(filepath),
            }
        )

    return predictions


def load_spread_data(spread_file: Path) -> dict:
    """Load spread data from JSON file."""
    with open(spread_file) as f:
        return json.load(f)


def match_predictions_with_spreads(
    predictions: list[dict], spread_data: dict
) -> list[dict]:
    """
    Match agent predictions with spread data by team names.

    Returns list of matched game data with both prediction and spread info.
    """
    matched = []

    for pred in predictions:
        home_team = pred["home_team"]
        away_team = pred["away_team"]

        # Find matching game in spread data
        spread_game = None
        for game in spread_data.get("games", []):
            # Match by home team name (most reliable)
            if game["home_team"] == home_team or game["away_team"] == away_team:
                spread_game = game
                break

        if spread_game:
            matched.append(
                {
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_team_abbr": spread_game.get("home_team_abbr"),
                    "away_team_abbr": spread_game.get("away_team_abbr"),
                    # Prediction data
                    "home_probability": pred["home_probability"],
                    "away_probability": pred["away_probability"],
                    "home_summary": pred["home_summary"],
                    "away_summary": pred["away_summary"],
                    # Spread data
                    "home_spread": spread_game.get("home_spread"),
                    "away_spread": spread_game.get("away_spread"),
                    "over_under": spread_game.get("over_under"),
                    "home_favorite": spread_game.get("home_favorite"),
                    "away_favorite": spread_game.get("away_favorite"),
                    "details": spread_game.get("details"),
                    # Moneyline data
                    "home_moneyline": spread_game.get("home_moneyline"),
                    "away_moneyline": spread_game.get("away_moneyline"),
                }
            )
        else:
            print(f"Warning: No spread data found for {away_team} @ {home_team}")

    return matched


def analyze_comparison(matched_games: list[dict]) -> dict:
    """
    Analyze the comparison between model predictions and spreads.

    Returns analysis with ATS (Against The Spread) picks and agreement stats.
    """
    analysis = {
        "total_games": len(matched_games),
        "games_with_spreads": 0,
        "model_agrees_with_spread": 0,
        "model_against_spread": 0,
        "games": [],
    }

    for game in matched_games:
        home_prob = game["home_probability"]
        home_spread = game["home_spread"]

        if home_prob is None or home_spread is None:
            continue

        analysis["games_with_spreads"] += 1

        # Model pick: team with higher probability
        model_picks_home = home_prob > 0.5

        # Spread pick: negative spread = favored
        spread_picks_home = home_spread < 0

        # ATS: does model disagree with spread?
        agrees_with_spread = model_picks_home == spread_picks_home

        if agrees_with_spread:
            analysis["model_agrees_with_spread"] += 1
        else:
            analysis["model_against_spread"] += 1

        # Convert probability to implied spread (rough heuristic)
        # ~7 points per 50% swing in probability
        implied_spread = (0.5 - home_prob) * 14

        game_analysis = {
            **game,
            "model_picks_home": model_picks_home,
            "spread_picks_home": spread_picks_home,
            "agrees_with_spread": agrees_with_spread,
            "implied_spread": round(implied_spread, 1),
            "model_confidence": abs(home_prob - 0.5) * 2,  # 0-1 scale
        }

        analysis["games"].append(game_analysis)

    # Sort by model confidence (most confident picks first)
    analysis["games"].sort(key=lambda x: x.get("model_confidence", 0), reverse=True)

    return analysis


def generate_markdown_report(analysis: dict, week: int, output_path: Path) -> None:
    """Generate a Markdown report comparing model predictions vs spreads."""

    total = analysis["games_with_spreads"]
    agrees = analysis["model_agrees_with_spread"]
    against = analysis["model_against_spread"]
    agreement_pct = (agrees / total * 100) if total > 0 else 0

    # Separate games into WITH and AGAINST sections
    with_games = [g for g in analysis["games"] if g["agrees_with_spread"]]
    against_games = [g for g in analysis["games"] if not g["agrees_with_spread"]]

    markdown_lines = [
        f"# 🏈 Model vs Spread: Week {week}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Games | {total} |",
        f"| Agreement Rate | {agreement_pct:.0f}% |",
        f"| With Spread | {agrees} |",
        f"| Against Spread | {against} |",
        "",
        "---",
        "",
        "## ⚡ Against The Spread",
        "",
        "Games where the model disagrees with the betting spread - potential value picks.",
        "",
    ]

    if against_games:
        markdown_lines.append(
            "| Matchup | Model Pick | Spread | Implied Spread | Confidence | Moneyline |"
        )
        markdown_lines.append(
            "|---------|------------|--------|----------------|------------|-----------|"
        )
        for game in against_games:
            markdown_lines.append(generate_game_card_markdown(game))
    else:
        markdown_lines.append("*No games against the spread.*")

    markdown_lines.extend(
        [
            "",
            "---",
            "",
            "## ✓ With The Spread",
            "",
            "Games where the model agrees with the betting spread.",
            "",
        ]
    )

    if with_games:
        markdown_lines.append(
            "| Matchup | Model Pick | Spread | Implied Spread | Confidence | Moneyline |"
        )
        markdown_lines.append(
            "|---------|------------|--------|----------------|------------|-----------|"
        )
        for game in with_games:
            markdown_lines.append(generate_game_card_markdown(game))
    else:
        markdown_lines.append("*No games with the spread.*")

    markdown_lines.extend(
        [
            "",
            "---",
            "",
            "## 📋 All Games",
            "",
            "| Matchup | Model Pick | Spread | Implied Spread | Confidence | Moneyline | ATS |",
            "|---------|------------|--------|----------------|------------|-----------|-----|",
        ]
    )
    for game in analysis["games"]:
        markdown_lines.append(generate_game_card_markdown(game, include_ats=True))

    markdown_lines.extend(
        [
            "",
            "---",
            "",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(markdown_lines))

    print(f"Markdown report saved to {output_path}")


def generate_game_card_markdown(game: dict, include_ats: bool = False) -> str:
    """Generate Markdown table row for a single game."""
    home = game.get("home_team_abbr") or game["home_team"][:3].upper()
    away = game.get("away_team_abbr") or game["away_team"][:3].upper()
    home_prob = game["home_probability"]
    away_prob = game["away_probability"]
    details = game.get("details", "N/A")
    agrees = game["agrees_with_spread"]
    model_picks_home = game["model_picks_home"]
    implied_spread = game["implied_spread"]
    confidence = game["model_confidence"]

    # Moneyline data
    home_ml = game.get("home_moneyline")
    away_ml = game.get("away_moneyline")
    home_ml_str = f"{home_ml:+d}" if home_ml is not None else "N/A"
    away_ml_str = f"{away_ml:+d}" if away_ml is not None else "N/A"
    moneyline_str = f"{away} {away_ml_str} / {home} {home_ml_str}"

    model_pick_team = home if model_picks_home else away
    model_pick_prob = home_prob if model_picks_home else away_prob
    spread_pick_team = home if game["spread_picks_home"] else away

    matchup = f"{away} @ {home}"
    model_pick = f"**{model_pick_team}** ({model_pick_prob:.0%})"
    spread = f"**{spread_pick_team}** ({details})"
    implied = f"{implied_spread:+.1f}"
    confidence_str = f"{confidence:.0%}"

    if include_ats:
        ats_text = "✓ WITH" if agrees else "✗ AGAINST"
        return f"| {matchup} | {model_pick} | {spread} | {implied} | {confidence_str} | {moneyline_str} | {ats_text} |"
    else:
        return f"| {matchup} | {model_pick} | {spread} | {implied} | {confidence_str} | {moneyline_str} |"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare NFL agent predictions against betting spreads"
    )
    parser.add_argument(
        "--week",
        type=int,
        default=18,
        help="NFL week number (default: 18)",
    )
    parser.add_argument(
        "--predictions-dir",
        type=str,
        default=None,
        help="Directory with agent predictions (default: artifacts/nfl_stats_agent/)",
    )
    parser.add_argument(
        "--spread-file",
        type=str,
        default=None,
        help="Spread data file (default: artifacts/prematch_spread/week_{week}.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for Markdown report (default: artifacts/prematch_spread/)",
    )

    args = parser.parse_args()

    # Set default paths
    artifacts_dir = Path(__file__).parent.parent / "experiments" / "artifacts"

    predictions_dir = (
        Path(args.predictions_dir)
        if args.predictions_dir
        else artifacts_dir / "nfl_stats_agent_v1"
    )

    spread_file = (
        Path(args.spread_file)
        if args.spread_file
        else artifacts_dir / "prematch_spread" / f"week_{args.week}.json"
    )

    output_dir = (
        Path(args.output_dir) if args.output_dir else artifacts_dir / "prematch_spread"
    )

    # Check inputs exist
    if not predictions_dir.exists():
        print(f"Error: Predictions directory not found: {predictions_dir}")
        return

    if not spread_file.exists():
        print(f"Error: Spread file not found: {spread_file}")
        print(
            "Run fetch_prematch_spread.py first to fetch spread data, or check the week number."
        )
        return

    # Load data
    print(f"Loading predictions from {predictions_dir}...")
    predictions = load_agent_predictions(predictions_dir, args.week)
    print(f"Found {len(predictions)} predictions")

    print(f"Loading spread data from {spread_file}...")
    spread_data = load_spread_data(spread_file)
    print(f"Found {len(spread_data.get('games', []))} games with spread data")

    # Match and analyze
    matched = match_predictions_with_spreads(predictions, spread_data)
    print(f"Matched {len(matched)} games")

    analysis = analyze_comparison(matched)

    # Print console summary
    print("\n" + "=" * 60)
    print(f"Model vs Spread: Week {args.week}")
    print("=" * 60)

    total = analysis["games_with_spreads"]
    agrees = analysis["model_agrees_with_spread"]
    against = analysis["model_against_spread"]
    agreement_pct = (agrees / total * 100) if total > 0 else 0

    print(f"  Games analyzed:     {total}")
    print(f"  Agreement rate:     {agreement_pct:.0f}%")
    print(f"  With spread:        {agrees}")
    print(f"  Against spread:     {against}")
    print()

    # Print ATS picks
    if against > 0:
        print("AGAINST THE SPREAD PICKS:")
        print("-" * 40)
        for game in analysis["games"]:
            if not game["agrees_with_spread"]:
                home = game.get("home_team_abbr") or game["home_team"][:3].upper()
                away = game.get("away_team_abbr") or game["away_team"][:3].upper()
                model_pick = home if game["model_picks_home"] else away
                home if game["spread_picks_home"] else away
                details = game.get("details", "N/A")
                prob = (
                    game["home_probability"]
                    if game["model_picks_home"]
                    else game["away_probability"]
                )
                print(
                    f"  {away} @ {home}: Model picks {model_pick} ({prob:.0%}), Spread: {details}"
                )
        print()

    # Generate Markdown report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"comparison_{timestamp}.md"
    generate_markdown_report(analysis, args.week, output_path)

    print("=" * 60)


if __name__ == "__main__":
    main()
