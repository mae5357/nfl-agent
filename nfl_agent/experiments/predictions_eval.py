"""Evaluate NFL prediction model performance using Brier Score."""

import json
import re
from pathlib import Path

import numpy as np


def moneyline_to_prob(ml: int) -> float:
    """Convert American moneyline odds to implied probability."""
    if ml < 0:
        return abs(ml) / (abs(ml) + 100)
    else:
        return 100 / (ml + 100)


def brier_score(probs: list[float], outcomes: list[int]) -> float:
    """Calculate Brier score - lower is better (0=perfect, 0.25=random)."""
    return np.mean([(p - o) ** 2 for p, o in zip(probs, outcomes)])


def load_agent_predictions(predictions_dir: Path, week: int) -> list[dict]:
    """Load agent predictions from JSON files."""
    predictions = []
    pattern = f"*_week_{week}.json"

    for filepath in predictions_dir.glob(pattern):
        try:
            with open(filepath) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue

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
            continue

        # Get team names from the human message
        human_msg = None
        for msg in messages:
            if msg.get("type") == "human":
                human_msg = msg.get("data", {}).get("content", "")
                break

        if human_msg:
            match = re.match(r"(.+?)\s+vs\.?\s+(.+)", human_msg)
            if match:
                home_team = match.group(1).strip()
                away_team = match.group(2).strip()
            else:
                continue
        else:
            continue

        # Normalize probabilities to 0-1 range
        home_prob = final_prediction.get("home_team_probability")
        if home_prob is not None and home_prob > 1:
            home_prob = home_prob / 100

        predictions.append(
            {
                "home_team": home_team,
                "away_team": away_team,
                "home_probability": home_prob,
            }
        )

    return predictions


def load_spread_data(spread_file: Path) -> dict:
    """Load spread data from JSON file."""
    with open(spread_file) as f:
        return json.load(f)


def load_game_scores(scores_file: Path) -> dict:
    """Load actual game scores from JSON file."""
    with open(scores_file) as f:
        return json.load(f)


def main():
    week = 18
    artifacts_dir = Path(__file__).parent / "artifacts"

    predictions_dir = artifacts_dir / "nfl_stats_agent_v1"
    spread_file = artifacts_dir / "prematch_spread" / f"week_{week}.json"
    scores_file = (
        artifacts_dir / "game_scores_week_18" / f"scores_week_{week}_2025.json"
    )

    # Load data
    predictions = load_agent_predictions(predictions_dir, week)
    spread_data = load_spread_data(spread_file)
    scores_data = load_game_scores(scores_file)

    # Build lookup dicts
    spread_by_home = {g["home_team"]: g for g in spread_data["games"]}
    scores_by_home = {g["home_team"]: g for g in scores_data["games"]}

    # Collect data for Brier score calculation
    model_probs = []
    spread_probs = []
    random_probs = []
    outcomes = []
    game_details = []

    for pred in predictions:
        home_team = pred["home_team"]

        if home_team not in spread_by_home or home_team not in scores_by_home:
            continue

        spread = spread_by_home[home_team]
        score = scores_by_home[home_team]

        # Get probabilities
        model_prob = pred["home_probability"]
        if model_prob is None:
            continue

        # Convert moneyline to implied probability (normalized)
        home_ml = spread.get("home_moneyline")
        away_ml = spread.get("away_moneyline")
        if home_ml is None or away_ml is None:
            continue

        home_implied = moneyline_to_prob(home_ml)
        away_implied = moneyline_to_prob(away_ml)
        total = home_implied + away_implied
        spread_prob = home_implied / total  # Normalized

        # Determine actual outcome (1 = home win, 0 = away win)
        home_score = int(score["home_score"])
        away_score = int(score["away_score"])
        outcome = 1 if home_score > away_score else 0

        model_probs.append(model_prob)
        spread_probs.append(spread_prob)
        random_probs.append(0.5)
        outcomes.append(outcome)

        # Determine if predictions were correct
        model_predicted_home = model_prob > 0.5
        spread_predicted_home = spread_prob > 0.5
        model_correct = model_predicted_home == (outcome == 1)
        spread_correct = spread_predicted_home == (outcome == 1)

        game_details.append(
            {
                "game": f"{pred['away_team']} @ {pred['home_team']}",
                "model_prob": model_prob,
                "spread_prob": spread_prob,
                "outcome": outcome,
                "score": f"{away_score}-{home_score}",
                "model_correct": model_correct,
                "spread_correct": spread_correct,
            }
        )

    # Calculate Brier scores
    model_brier = brier_score(model_probs, outcomes)
    spread_brier = brier_score(spread_probs, outcomes)
    random_brier = 0.25

    # Calculate accuracy
    model_correct = sum(1 for p, o in zip(model_probs, outcomes) if (p > 0.5) == o)
    spread_correct = sum(1 for p, o in zip(spread_probs, outcomes) if (p > 0.5) == o)
    n_games = len(outcomes)

    model_accuracy = model_correct / n_games
    spread_accuracy = spread_correct / n_games
    random_accuracy = 0.5

    # Calculate Brier Skill Score vs random
    model_bss = 1 - (model_brier / random_brier)
    spread_bss = 1 - (spread_brier / random_brier)

    # Write summary markdown file
    output_file = artifacts_dir / "predictions_eval_summary.md"
    with open(output_file, "w") as f:
        f.write("# Prediction Evaluation Summary\n\n")
        f.write(f"**Week {week}** - {n_games} games evaluated\n\n")
        f.write("## Metrics\n\n")
        f.write("| Metric | Model | Sportsbook | Random |\n")
        f.write("|--------|-------|------------|--------|\n")
        f.write(
            f"| Brier Score | {model_brier:.4f} | {spread_brier:.4f} | {random_brier:.4f} |\n"
        )
        f.write(
            f"| Accuracy | {model_accuracy:.1%} | {spread_accuracy:.1%} | {random_accuracy:.1%} |\n"
        )
        f.write(f"| BSS vs Random | {model_bss:+.1%} | {spread_bss:+.1%} | 0.0% |\n")
        f.write(f"| Games Evaluated | {n_games} | {n_games} | {n_games} |\n")
        f.write("\n")
        f.write("## Game-by-Game Details)\n\n")
        f.write(
            "| Game | Model Prob | Sportsbook Prob | Outcome | Score | Prediction Result |\n"
        )
        f.write(
            "|------|------------|-----------------|---------|-------|-------------------|\n"
        )
        for game in game_details:
            outcome_str = "Home Win" if game["outcome"] == 1 else "Away Win"
            model_correct = game["model_correct"]
            spread_correct = game["spread_correct"]

            # Build prediction result indicator
            if model_correct and not spread_correct:
                result = "**Model ✓, Sportsbook ✗**"
            elif not model_correct and spread_correct:
                result = "**Sportsbook ✓, Model ✗**"
            elif not model_correct and not spread_correct:
                result = "**Both ✗**"
            else:  # both correct
                result = "Both ✓"

            f.write(
                f"| {game['game']} | {game['model_prob']:.2%} | {game['spread_prob']:.2%} | {outcome_str} | {game['score']} | {result} |\n"
            )

        # Count prediction comparison cases
        model_only_correct = sum(
            1 for g in game_details if g["model_correct"] and not g["spread_correct"]
        )
        spread_only_correct = sum(
            1 for g in game_details if not g["model_correct"] and g["spread_correct"]
        )
        model_incorrect = sum(1 for g in game_details if not g["model_correct"])
        spread_incorrect = sum(1 for g in game_details if not g["spread_correct"])
        both_correct = sum(
            1 for g in game_details if g["model_correct"] and g["spread_correct"]
        )
        both_incorrect = sum(
            1
            for g in game_details
            if not g["model_correct"] and not g["spread_correct"]
        )

        f.write("\n")
        f.write("*probabilities are for home team\n\n")
        f.write("## Prediction Comparison Summary\n\n")
        f.write(
            f"- **Model correct, Sportsbook incorrect**: {model_only_correct} games\n"
        )
        f.write(
            f"- **Sportsbook correct, Model incorrect**: {spread_only_correct} games\n"
        )
        f.write(f"- **Model incorrect**: {model_incorrect} games\n")
        f.write(f"- **Sportsbook incorrect**: {spread_incorrect} games\n")
        f.write(f"- **Both correct**: {both_correct} games\n")
        f.write(f"- **Both incorrect**: {both_incorrect} games\n")
        f.write("\n")
        f.write("## Notes\n\n")
        f.write("- **Brier Score**: Lower is better (0 = perfect, 0.25 = random)\n")
        f.write(
            "- **BSS (Brier Skill Score)**: Higher is better (1 = perfect, 0 = random baseline)\n"
        )
        f.write("- **Outcome**: 1 = Home Win, 0 = Away Win\n")

    print(f"Summary written to {output_file}")
    print()
    print("=== Prediction Evaluation Summary ===")
    print(f"{'Metric':<20} {'Model':>12} {'Sportsbook':>12} {'Random':>12}")
    print("-" * 58)
    print(
        f"{'Brier Score':<20} {model_brier:>12.4f} {spread_brier:>12.4f} {random_brier:>12.4f}"
    )
    print(
        f"{'Accuracy':<20} {model_accuracy:>11.1%} {spread_accuracy:>11.1%} {random_accuracy:>11.1%}"
    )
    print(f"{'BSS vs Random':<20} {model_bss:>+11.1%} {spread_bss:+11.1%} {'0.0%':>12}")
    print(f"{'Games Evaluated':<20} {n_games:>12} {n_games:>12} {n_games:>12}")


if __name__ == "__main__":
    main()
