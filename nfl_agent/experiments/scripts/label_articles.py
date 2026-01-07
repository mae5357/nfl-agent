#!/usr/bin/env python3
"""
CLI tool for labeling article relevance in ESPN article datasets.

Usage:
    python -m nfl_agent.scripts.label_articles articles.json
    python -m nfl_agent.scripts.label_articles articles.json --overwrite
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_INPUT_FILE = (
    Path(__file__).parent.parent
    / "artifacts"
    / "article_relevance_eval"
    / "team_articles.json"
)


# ANSI color codes for pretty display
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def clear_screen():
    """Clear terminal screen."""
    print("\033[2J\033[H", end="")


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y at %I:%M %p UTC")
    except (ValueError, AttributeError):
        return ts or "Unknown"


def get_api_link(article: dict) -> str:
    """Extract API link from article links."""
    try:
        return (
            article.get("links", {}).get("api", {}).get("self", {}).get("href", "N/A")
        )
    except (AttributeError, TypeError):
        return "N/A"


def display_article(article: dict, index: int, total: int) -> None:
    """Display article information in a pretty format."""
    clear_screen()

    # Header
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.BOLD}  Article {index + 1} of {total}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}\n")

    # Headline
    headline = article.get("headline", "No headline")
    print(f"{Colors.BOLD}{Colors.CYAN}📰 HEADLINE{Colors.ENDC}")
    print(f"   {headline}\n")

    # Description
    description = article.get("description", "No description available")
    print(f"{Colors.BOLD}{Colors.GREEN}📝 DESCRIPTION{Colors.ENDC}")
    print(f"   {description}\n")

    # Published date
    published = format_timestamp(article.get("published"))
    print(f"{Colors.BOLD}{Colors.YELLOW}📅 PUBLISHED{Colors.ENDC}")
    print(f"   {published}\n")

    # API Link
    api_link = get_api_link(article)
    print(f"{Colors.BOLD}{Colors.BLUE}🔗 API LINK{Colors.ENDC}")
    print(f"   {api_link}\n")

    # Existing score (if any)
    existing_score = article.get("human_labelled_relevance_score")
    if existing_score is not None:
        print(f"{Colors.DIM}Previous score: {existing_score}{Colors.ENDC}\n")

    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}")


def get_score_input() -> int | None:
    """Prompt user for relevance score. Returns None to quit."""
    print(f"\n{Colors.BOLD}Relevance Score Guide:{Colors.ENDC}")
    print(f"  {Colors.RED}0{Colors.ENDC} = Not relevant at all")
    print(f"  {Colors.YELLOW}1{Colors.ENDC} = Slightly relevant")
    print(f"  {Colors.CYAN}2{Colors.ENDC} = Moderately relevant")
    print(f"  {Colors.GREEN}3{Colors.ENDC} = Highly relevant")
    print(f"  {Colors.DIM}q = Quit and save{Colors.ENDC}\n")

    while True:
        try:
            response = (
                input(f"{Colors.BOLD}Enter score (0-3) or 'q' to quit: {Colors.ENDC}")
                .strip()
                .lower()
            )

            if response == "q":
                return None

            score = int(response)
            if 0 <= score <= 3:
                return score
            else:
                print(
                    f"{Colors.RED}Please enter a number between 0 and 3.{Colors.ENDC}"
                )
        except ValueError:
            print(
                f"{Colors.RED}Invalid input. Please enter 0, 1, 2, 3, or 'q'.{Colors.ENDC}"
            )


def save_articles(articles: list, filepath: Path) -> None:
    """Save articles back to JSON file."""
    with open(filepath, "w") as f:
        json.dump(articles, f, indent=4)


def main():
    parser = argparse.ArgumentParser(
        description="Label ESPN articles with relevance scores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""        
Examples:
    uv run label-articles
    uv run label-articles --overwrite
        """,
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="Path to JSON file containing articles",
        default=DEFAULT_INPUT_FILE,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-score articles that already have a human_labelled_relevance_score",
    )

    args = parser.parse_args()

    # Validate input file
    if not args.input_file.exists():
        print(f"{Colors.RED}Error: File not found: {args.input_file}{Colors.ENDC}")
        sys.exit(1)

    # Load articles
    try:
        with open(args.input_file) as f:
            articles = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}Error: Invalid JSON file: {e}{Colors.ENDC}")
        sys.exit(1)

    if not isinstance(articles, list):
        print(f"{Colors.RED}Error: Expected a JSON array of articles{Colors.ENDC}")
        sys.exit(1)

    total = len(articles)
    labeled_count = 0
    skipped_count = 0

    print(f"{Colors.BOLD}Loading {total} articles from {args.input_file}{Colors.ENDC}")

    for i, article in enumerate(articles):
        # Skip already labeled articles unless --overwrite
        if not args.overwrite and "human_labelled_relevance_score" in article:
            skipped_count += 1
            continue

        display_article(article, i, total)
        score = get_score_input()

        if score is None:
            # User wants to quit
            print(f"\n{Colors.YELLOW}Saving progress...{Colors.ENDC}")
            save_articles(articles, args.input_file)
            print(
                f"{Colors.GREEN}✓ Saved! Labeled {labeled_count} articles this session.{Colors.ENDC}"
            )
            if skipped_count > 0:
                print(
                    f"{Colors.DIM}  Skipped {skipped_count} already-labeled articles.{Colors.ENDC}"
                )
            sys.exit(0)

        # Update article with score
        article["human_labelled_relevance_score"] = score
        labeled_count += 1

        # Save after each score (in case of crash/interrupt)
        save_articles(articles, args.input_file)

    # Completed all articles
    clear_screen()
    print(f"{Colors.GREEN}{Colors.BOLD}✓ Labeling complete!{Colors.ENDC}")
    print(f"  Labeled: {labeled_count} articles")
    if skipped_count > 0:
        print(f"  Skipped: {skipped_count} already-labeled articles")
    print(f"  Results saved to: {args.input_file}")


if __name__ == "__main__":
    main()
