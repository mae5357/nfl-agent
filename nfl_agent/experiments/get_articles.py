#!/usr/bin/env python3
"""
Script to fetch NFL articles for all teams and save them to a JSON file.

Usage:
    python -m nfl_agent.scripts.get_articles
"""

import json
from pathlib import Path
from nfl_agent.src.utils.espn_client import ESPNClient
from nfl_agent.src.tools.article_fetcher.utils import fetch_articles_for_team


def main():
    """Fetch articles for all NFL teams and save to JSON file."""
    # Output file path (from nfl_agent/scripts/ to nfl_agent/experiments/artifacts/article_relevance_eval/)
    output_file = (
        Path(__file__).parent.parent
        / "experiments"
        / "artifacts"
        / "article_relevance_eval"
        / "team_articles.json"
    )

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize ESPN client
    client = ESPNClient()

    # Get all team IDs
    team_mapping = client._load_team_mapping()
    team_ids = list(team_mapping.values())

    print(f"Fetching articles for {len(team_ids)} teams...")

    all_articles = []
    articles_by_team = {}

    for team_name, team_id in team_mapping.items():
        print(f"Fetching articles for {team_name} (ID: {team_id})...")
        try:
            articles = fetch_articles_for_team(int(team_id))
            articles_by_team[team_name] = len(articles)
            # Convert Pydantic models to dicts for JSON serialization
            for article in articles:
                article_dict = article.model_dump(mode="json")
                all_articles.append(article_dict)
            print(f"  Found {len(articles)} articles")
        except Exception as e:
            print(f"  Error fetching articles for {team_name}: {e}")
            articles_by_team[team_name] = 0

    # Save all articles to JSON file
    print(f"\nSaving {len(all_articles)} total articles to {output_file}...")
    with open(output_file, "w") as f:
        json.dump(all_articles, f, indent=2, default=str)

    print(f"✓ Successfully saved articles to {output_file}")
    print("\nSummary by team:")
    for team_name, count in sorted(articles_by_team.items()):
        print(f"  {team_name}: {count} articles")


if __name__ == "__main__":
    main()
