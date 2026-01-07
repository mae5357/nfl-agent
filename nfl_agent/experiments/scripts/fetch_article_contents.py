#!/usr/bin/env python3
"""
Script to fetch article contents from team_articles_labelled.json
and save each article with its content as a separate JSON file.
"""

import json
import sys
from pathlib import Path

from nfl_agent.src.tools.article_fetcher.utils import fetch_article_content

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def main():
    # Define paths
    test_data_dir = Path(__file__).parent.parent / "tests" / "test_data"
    input_file = test_data_dir / "team_articles_labelled.json"
    output_dir = test_data_dir / "article_contents"

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Load articles
    print(f"Loading articles from {input_file}")
    with open(input_file, "r") as f:
        articles = json.load(f)

    print(f"Found {len(articles)} articles")

    # Process each article
    for i, article in enumerate(articles):
        article_id = article.get("id")
        headline = article.get("headline", "Unknown")

        # Get the web URL
        web_url = article.get("links", {}).get("web", {}).get("href", "")

        if not web_url:
            print(
                f"[{i + 1}/{len(articles)}] Skipping article {article_id}: No web URL found"
            )
            continue

        print(
            f"[{i + 1}/{len(articles)}] Fetching content for article {article_id}: {headline[:50]}..."
        )

        # Fetch the article content
        content = fetch_article_content(
            web_url, max_length=50000
        )  # Higher limit for storage

        # Create output object with article info and content
        output_data = {**article, "fetched_content": content, "fetched_url": web_url}

        # Save to individual file
        output_file = output_dir / f"article_{article_id}.json"
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        if content.startswith("Error"):
            print(f"  -> Error fetching content: {content[:100]}")
        else:
            print(f"  -> Saved to {output_file.name} ({len(content)} chars)")

    print(f"\nDone! Articles saved to {output_dir}")


if __name__ == "__main__":
    main()
