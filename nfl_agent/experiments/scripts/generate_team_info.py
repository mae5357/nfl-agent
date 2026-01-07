"""
Script to generate TeamInfo outputs from article content files.

Processes all JSON files in test_data/article_contents and generates
TeamInfo summaries using the article summarizer model.
"""

import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain.messages import SystemMessage, HumanMessage

from nfl_agent.src.models.espn_search import TeamInfo
from nfl_agent.src.utils.settings import get_setting, LLMSettings, get_chat_model
from nfl_agent.prompts.article_summarizer.v2 import (
    SYSTEM_PROMPT as ARTICLE_SUMMARIZER_SYSTEM_PROMPT,
    USER_PROMPT as ARTICLE_SUMMARIZER_USER_PROMPT,
)


TEAM_NAME = "Philadelphia Eagles"


def process_article(article_path: Path, model: ChatOpenAI) -> TeamInfo | None:
    """Process a single article and return TeamInfo."""
    with open(article_path, "r") as f:
        article_data = json.load(f)

    article_content = article_data.get("fetched_content")
    if not article_content:
        print(f"  No fetched_content found in {article_path.name}, skipping...")
        return None

    team_name = TEAM_NAME

    result: TeamInfo = model.invoke(
        [
            SystemMessage(content=ARTICLE_SUMMARIZER_SYSTEM_PROMPT),
            HumanMessage(
                content=ARTICLE_SUMMARIZER_USER_PROMPT.format(
                    team_name=team_name, article_content=article_content
                )
            ),
        ]
    )

    return result


def main():
    # Load environment variables
    load_dotenv("/Users/madison.ebersole/Repos/sandbox/nfl-agent/.env")

    # Set up paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    article_contents_dir = project_root / "tests" / "test_data" / "article_contents"
    output_dir = project_root / "tests" / "test_data" / "teamInfo"

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up the model
    article_summarization_settings = get_setting(LLMSettings)
    article_summarization_model = get_chat_model(article_summarization_settings)
    article_summarization_model = article_summarization_model.with_structured_output(
        TeamInfo
    )

    # Process all JSON files
    article_files = sorted(article_contents_dir.glob("*.json"))
    print(f"Found {len(article_files)} article files to process")

    for i, article_path in enumerate(article_files, 1):
        print(f"Processing {i}/{len(article_files)}: {article_path.name}")

        try:
            result = process_article(article_path, article_summarization_model)

            if result:
                # Save output with same filename pattern
                output_filename = article_path.stem + "_team_info.json"
                output_path = output_dir / output_filename

                with open(output_path, "w") as f:
                    f.write(result.model_dump_json(indent=2))

                print(f"  Saved to {output_filename}")
            else:
                print("  Skipped (no content)")

        except Exception as e:
            print(f"  Error processing {article_path.name}: {e}")


if __name__ == "__main__":
    main()
