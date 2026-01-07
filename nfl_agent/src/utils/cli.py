"""CLI utilities for NFL agent interaction."""

from typing import Optional
from datetime import datetime, timezone
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.models.espn_responses import NormalizedGame


def find_current_week(client: ESPNClient) -> Optional[int]:
    """
    Determine the current NFL week based on today's date and game schedules.

    Args:
        client: ESPNClient instance

    Returns:
        Current week number (1-18) or None if not found
    """
    today = datetime.now(timezone.utc).date()

    # Check weeks 1-18 to find which week contains games around today
    for week in range(1, 19):
        try:
            games = client.get_weekly_games(week=week)

            for game in games:
                if game.kickoff_utc:
                    try:
                        kickoff_dt = datetime.fromisoformat(
                            game.kickoff_utc.replace("Z", "+00:00")
                        )
                        if kickoff_dt.tzinfo is None:
                            kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)
                        kickoff_date = kickoff_dt.date()

                        # Check if this game is within 7 days of today (current week)
                        days_diff = abs((kickoff_date - today).days)
                        if days_diff <= 7:
                            return week
                    except (ValueError, AttributeError):
                        continue
        except Exception:
            continue

    return None


def find_next_week_with_games(client: ESPNClient) -> int:
    """
    Find the next week that has scheduled games (not yet played).

    Uses get_weekly_games() and today's date to determine current week,
    then finds the next week with scheduled games.

    Args:
        client: ESPNClient instance

    Returns:
        Week number (1-18) with upcoming games

    Raises:
        Exception: If no upcoming games found in any week
    """
    now = datetime.now(timezone.utc)
    current_week = find_current_week(client)

    # Start checking from current week (or week 1 if current week not found)
    start_week = current_week if current_week else 1

    # Check weeks starting from current week through 18
    for week in range(start_week, 19):
        try:
            games = client.get_weekly_games(week=week)

            # Check if any games are scheduled or in the future
            for game in games:
                # If status is "scheduled", it's an upcoming game
                if game.status == "scheduled":
                    return week

                # If kickoff time is in the future, it's an upcoming game
                if game.kickoff_utc:
                    try:
                        kickoff_dt = datetime.fromisoformat(
                            game.kickoff_utc.replace("Z", "+00:00")
                        )
                        if kickoff_dt.tzinfo is None:
                            kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)
                        if kickoff_dt > now:
                            return week
                    except (ValueError, AttributeError):
                        # If we can't parse the date, check if status indicates it's upcoming
                        if game.status and game.status not in ["post", "final"]:
                            return week
        except Exception:
            # If a week fails, continue to next week
            continue

    # If no upcoming games found, default to week 1
    return 18


def select_game_from_week(week: Optional[int] = None) -> NormalizedGame:
    """
    Display all games for a given week and prompt user to select one.

    Args:
        week: Week number (1-18). If None, defaults to next week with scheduled games.

    Returns:
        The selected NormalizedGame object

    Raises:
        ValueError: If invalid game number is selected
        Exception: If unable to fetch games
    """
    client = ESPNClient()

    # Default to next week with scheduled games if not specified
    if week is None:
        week = find_next_week_with_games(client)

    print(f"\nFetching games for week {week}...")
    games = client.get_weekly_games(week=week)

    if not games:
        raise Exception(f"No games found for week {week}")

    print(f"\nFound {len(games)} games:\n")

    # Display numbered list of games
    for idx, game in enumerate(games, start=1):
        away_team = game.away_team_abbr or game.away_team_name or game.away_team_id
        home_team = game.home_team_abbr or game.home_team_name or game.home_team_id

        # Format kickoff time if available
        kickoff_info = ""
        if game.kickoff_utc:
            try:
                kickoff_dt = datetime.fromisoformat(
                    game.kickoff_utc.replace("Z", "+00:00")
                )
                if kickoff_dt.tzinfo is None:
                    kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)
                kickoff_info = f" ({kickoff_dt.strftime('%a %b %d, %I:%M %p')})"
            except (ValueError, AttributeError):
                pass

        status_info = ""
        if game.status:
            status_info = f" [{game.status}]"

        print(f"  {idx}. {away_team} @ {home_team}{kickoff_info}{status_info}")

    # Prompt user for selection
    while True:
        try:
            selection = input(f"\nSelect a game (1-{len(games)}): ").strip()
            game_num = int(selection)

            if 1 <= game_num <= len(games):
                selected_game = games[game_num - 1]
                away_team = selected_game.away_team_abbr or selected_game.away_team_name
                home_team = selected_game.home_team_abbr or selected_game.home_team_name
                print(f"\nSelected: {away_team} @ {home_team}")
                return selected_game
            else:
                print(f"Please enter a number between 1 and {len(games)}")
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\nCancelled.")
            raise
