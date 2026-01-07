"""Fetch pre-match spread data for NFL games from ESPN odds API."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from nfl_agent.src.utils.espn_client import ESPNClient

load_dotenv()


def fetch_spreads_for_week(
    week: int,
    provider_id: str = "38",
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Fetch spread data for all games in a given week.

    Args:
        week: NFL week number (1-18 for regular season)
        provider_id: ESPN odds provider ID (default "38" = Caesars)
        output_dir: Directory to save output JSON (optional)

    Returns:
        Dict with week number and list of game spread data
    """
    client = ESPNClient()

    print(f"Fetching games for week {week}...")
    games = client.get_weekly_games(week=week)
    print(f"Found {len(games)} games")

    spread_data = {
        "week": week,
        "fetched_at": datetime.now().isoformat(),
        "provider_id": provider_id,
        "games": [],
    }

    for game in games:
        print(f"  Fetching odds for {game.away_team_name} @ {game.home_team_name}...")

        odds = client.get_game_odds(event_id=game.event_id, provider_id=provider_id)

        game_data = {
            "event_id": game.event_id,
            "home_team": game.home_team_name,
            "home_team_abbr": game.home_team_abbr,
            "away_team": game.away_team_name,
            "away_team_abbr": game.away_team_abbr,
            "kickoff_utc": game.kickoff_utc,
        }

        if odds:
            game_data.update(
                {
                    "provider": odds.get("provider"),
                    "home_spread": odds.get("spread"),
                    "away_spread": -odds.get("spread") if odds.get("spread") else None,
                    "over_under": odds.get("over_under"),
                    "details": odds.get("details"),
                    "home_favorite": odds.get("home_favorite"),
                    "away_favorite": odds.get("away_favorite"),
                    "home_moneyline": odds.get("home_moneyline"),
                    "away_moneyline": odds.get("away_moneyline"),
                }
            )
        else:
            game_data.update(
                {
                    "provider": None,
                    "home_spread": None,
                    "away_spread": None,
                    "over_under": None,
                    "details": None,
                    "home_favorite": None,
                    "away_favorite": None,
                    "home_moneyline": None,
                    "away_moneyline": None,
                }
            )

        spread_data["games"].append(game_data)

    # Save to file if output directory provided
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"week_{week}.json"
        with open(output_path, "w") as f:
            json.dump(spread_data, f, indent=2)
        print(f"\nSaved spread data to {output_path}")

    return spread_data


def main():
    """Main entry point - fetch spreads for a specific week."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch pre-match spread data from ESPN"
    )
    parser.add_argument(
        "--week",
        type=int,
        default=18,
        help="NFL week number (default: 18)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="38",
        help="ESPN odds provider ID (default: 38 = Caesars)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: artifacts/prematch_spread/)",
    )

    args = parser.parse_args()

    # Default output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = (
            Path(__file__).parent.parent
            / "experiments"
            / "artifacts"
            / "prematch_spread"
        )

    spread_data = fetch_spreads_for_week(
        week=args.week,
        provider_id=args.provider,
        output_dir=output_dir,
    )

    # Print summary
    print("\n" + "=" * 70)
    print(f"Week {args.week} Spread & Moneyline Summary")
    print("=" * 70)
    print(f"  {'MATCHUP':<15} | {'SPREAD':<12} | {'MONEYLINE':<18} | FAV")
    print("-" * 70)

    for game in spread_data["games"]:
        home = game["home_team_abbr"] or game["home_team"]
        away = game["away_team_abbr"] or game["away_team"]
        spread = game.get("home_spread")
        details = game.get("details", "N/A")
        home_ml = game.get("home_moneyline")
        away_ml = game.get("away_moneyline")

        if spread is not None:
            fav = home if game.get("home_favorite") else away
            # Format moneyline with + for underdogs
            home_ml_str = f"{home_ml:+d}" if home_ml is not None else "N/A"
            away_ml_str = f"{away_ml:+d}" if away_ml is not None else "N/A"
            ml_str = f"{away}:{away_ml_str} {home}:{home_ml_str}"
            print(f"  {away:4} @ {home:4}  | {details:<12} | {ml_str:<18} | {fav}")
        else:
            print(f"  {away:4} @ {home:4}  | No odds available")

    print("=" * 70)


if __name__ == "__main__":
    main()
