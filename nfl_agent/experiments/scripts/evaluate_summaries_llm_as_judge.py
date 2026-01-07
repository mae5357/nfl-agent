#!/usr/bin/env python3
"""
LLM-as-Judge CLI tool for evaluating AI-extracted facts from NFL articles.

Uses OpenAI GPT models to automatically evaluate across three dimensions:
- Accuracy: Verify each extracted fact against the source article
- Completeness: Check if all relevant facts were extracted
- Relevance: Assess if facts are relevant for game predictions

Usage:
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode accuracy
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode completeness
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode relevance
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode all
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode accuracy --overwrite
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from nfl_agent.src.utils.settings import LLMSettings, get_setting, get_chat_model

load_dotenv()


# =============================================================================
# Settings
# =============================================================================


class LLMJudgeSettings(LLMSettings):
    """Settings for LLM Judge evaluation."""

    llm_model_name: str = "gpt-4o"
    temperature: float = 0.0  # Low temperature for consistent judging


# =============================================================================
# Pydantic Response Models
# =============================================================================


class AccuracyJudgment(BaseModel):
    """Response model for accuracy evaluation of a single fact."""

    correct: bool = Field(
        description="Whether the fact is accurately extracted from the source article"
    )


class CompletenessJudgment(BaseModel):
    """Response model for completeness evaluation."""

    complete: bool = Field(
        description="Whether all relevant facts were extracted from the article"
    )
    missing_facts: list[str] = Field(
        default_factory=list,
        description="List of facts that were missed by the extraction",
    )
    reasoning: str = Field(description="Explanation of the completeness assessment")


class RelevanceJudgment(BaseModel):
    """Response model for relevance evaluation of a single fact."""

    relevant: bool = Field(
        description="Whether the fact is relevant for game predictions"
    )
    notes: str = Field(
        description="Explanation of why this fact is or isn't relevant for predictions"
    )


# =============================================================================
# Judge Prompts
# =============================================================================


ACCURACY_SYSTEM_PROMPT = """You are an expert fact-checker evaluating the accuracy of AI-extracted facts from NFL articles.

Your task: Given a full article text and a single alleged fact sourced from that text, determine if the fact is CORRECT. Do not provide reasoning for your judgment.
Guidelines:
- Mark YES (correct=true) ONLY if the fact can be directly verified from the article text
- Mark NO (correct=false) if the fact cannot be assumed from the article, even if it seems plausible
- Focus ONLY on factual correctness - do not evaluate clinical significance or relevance
- If a fact is uninformative but still accurate based on the article, mark it as correct
- Be strict: the fact must be supported by the article text, not inferred from general knowledge
- Do not provide reasoning for your judgment.
"""


ACCURACY_USER_PROMPT = """## Source Article:
{article_content}

## Fact to Verify:
Category: {category}
Fact: {fact}

Is this fact accurately extracted from the source article?"""


COMPLETENESS_SYSTEM_PROMPT = """You are an expert evaluator assessing the completeness of AI-extracted facts from NFL articles.

Your task: Given a full article text and the complete list of facts extracted by an AI, determine if any facts relevant to the specified team were MISSED.

Guidelines:
- Focus ONLY on whether all facts relevant to the specified team are extracted from the article
- Look for medical/injury information, player performance data, coaching insights, and game-relevant statistics that pertain to the team
- IGNORE facts about other teams unless they directly impact the specified team's outlook
- IGNORE any potentially hallucinated statements - those are tracked separately
- If you identify missing facts, list them clearly
- Be thorough but focus on facts that would be relevant for predicting game outcomes for the specified team

Only provide reasoning if facts are missing (complete=false). If complete, leave reasoning empty."""


COMPLETENESS_USER_PROMPT = """## Team Being Evaluated:
{team_name}

## Source Article:
{article_content}

## Extracted Facts:
{facts_list}

Are there any facts relevant to the {team_name} from the article that were MISSED by the extraction?"""


RELEVANCE_SYSTEM_PROMPT = """You are an expert NFL analyst evaluating whether extracted facts are relevant for predicting game outcomes for a specific team.

Your task: Given a single fact and the team being evaluated, determine if the fact is RELEVANT for predicting game outcomes for that team.

Guidelines:
- Consider whether this fact would influence betting lines, fantasy decisions, or game outcome predictions for the specified team
- Relevant facts include: injuries to key players, player performance trends, coaching insights, matchup advantages/disadvantages, and any information affecting team strength
- Less relevant facts include: historical trivia, off-field news unrelated to performance, general commentary, or facts about other teams that don't directly impact the specified team

Only provide notes if the fact is NOT relevant (relevant=false), explaining why. If relevant, leave notes empty."""


RELEVANCE_USER_PROMPT = """## Team Being Evaluated:
{team_name}

## Fact to Evaluate:
Category: {category}
Fact: {fact}

Is this fact relevant for predicting game outcomes for the {team_name}?"""


# =============================================================================
# Default Paths
# =============================================================================

DEFAULT_ARTICLES_DIR = (
    Path(__file__).parent.parent / "tests" / "test_data" / "article_contents"
)
DEFAULT_TEAM_INFO_DIR = (
    Path(__file__).parent.parent / "tests" / "test_data" / "teamInfo"
)
DEFAULT_OUTPUT_DIR = (
    Path(__file__).parent.parent
    / "experiments"
    / "artifacts"
    / "summary_eval_llm_judge"
)


# =============================================================================
# Helper Functions
# =============================================================================


def extract_all_facts(team_info: dict) -> list[dict]:
    """Extract all facts from team_info with their categories."""
    facts = []

    # Add coaching_summary as a single fact if present
    if team_info.get("coaching_summary"):
        facts.append(
            {"category": "coaching_summary", "fact": team_info["coaching_summary"]}
        )

    # Add items from list fields
    for category in ["injuries", "strengths", "problem_areas", "relevant_players"]:
        items = team_info.get(category) or []
        for item in items:
            facts.append({"category": category, "fact": item})

    return facts


def find_article_pairs(
    articles_dir: Path, team_info_dir: Path
) -> list[tuple[int, Path, Path]]:
    """Find matching article and team_info file pairs."""
    pairs = []

    for team_info_file in sorted(team_info_dir.glob("article_*_team_info.json")):
        filename = team_info_file.stem
        parts = filename.split("_")
        if len(parts) >= 2:
            try:
                article_id = int(parts[1])
                article_file = articles_dir / f"article_{article_id}.json"
                if article_file.exists():
                    pairs.append((article_id, article_file, team_info_file))
            except ValueError:
                continue

    return pairs


def load_score_file(score_path: Path) -> dict:
    """Load existing score file or return empty dict."""
    if score_path.exists():
        with open(score_path) as f:
            return json.load(f)
    return {}


def save_score_file(score_path: Path, data: dict) -> None:
    """Save score data to JSON file."""
    score_path.parent.mkdir(parents=True, exist_ok=True)
    with open(score_path, "w") as f:
        json.dump(data, f, indent=2)


def mode_already_complete(score_data: dict, mode: str) -> bool:
    """Check if a mode has already been evaluated."""
    if mode == "accuracy":
        return "accuracy_score" in score_data and score_data.get("accuracy_details")
    elif mode == "completeness":
        return "completeness_score" in score_data
    elif mode == "relevance":
        return "relevance_score" in score_data and score_data.get("relevance_details")
    return False


def get_llm_client() -> ChatOpenAI:
    """Get configured LLM client for judge evaluations."""
    settings = get_setting(LLMJudgeSettings)
    return get_chat_model(settings)


# =============================================================================
# Evaluation Functions
# =============================================================================


def run_accuracy_mode(
    article: dict,
    team_info: dict,
    facts: list[dict],
    score_data: dict,
    llm: ChatOpenAI,
) -> dict:
    """Run accuracy evaluation using LLM judge."""
    print(f"  Running accuracy evaluation on {len(facts)} facts...")

    accuracy_details = []
    article_content = article.get("fetched_content", "No content available")

    # Create structured output chain
    accuracy_chain = llm.with_structured_output(AccuracyJudgment)

    for i, fact in enumerate(facts):
        print(f"    Evaluating fact {i + 1}/{len(facts)}...", end=" ", flush=True)

        messages = [
            {"role": "system", "content": ACCURACY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ACCURACY_USER_PROMPT.format(
                    article_content=article_content,
                    category=fact["category"],
                    fact=fact["fact"],
                ),
            },
        ]

        result: AccuracyJudgment = accuracy_chain.invoke(messages)

        accuracy_details.append(
            {
                "category": fact["category"],
                "fact": fact["fact"],
                "correct": result.correct,
            }
        )

        status = "✓" if result.correct else "✗"
        print(status)

    # Calculate accuracy score
    correct_count = sum(1 for d in accuracy_details if d["correct"])
    accuracy_score = correct_count / len(accuracy_details) if accuracy_details else 0.0

    score_data["accuracy_score"] = round(accuracy_score, 4)
    score_data["accuracy_details"] = accuracy_details

    print(f"  Accuracy: {correct_count}/{len(accuracy_details)} = {accuracy_score:.1%}")

    return score_data


def run_completeness_mode(
    article: dict,
    team_info: dict,
    facts: list[dict],
    score_data: dict,
    llm: ChatOpenAI,
) -> dict:
    """Run completeness evaluation using LLM judge."""
    print("  Running completeness evaluation...")

    article_content = article.get("fetched_content", "No content available")
    team_name = team_info.get("name", "Unknown Team")

    # Format facts list for prompt
    facts_formatted = "\n".join(f"- [{f['category']}] {f['fact']}" for f in facts)

    # Create structured output chain
    completeness_chain = llm.with_structured_output(CompletenessJudgment)

    messages = [
        {"role": "system", "content": COMPLETENESS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": COMPLETENESS_USER_PROMPT.format(
                team_name=team_name,
                article_content=article_content,
                facts_list=facts_formatted,
            ),
        },
    ]

    result: CompletenessJudgment = completeness_chain.invoke(messages)

    # Score is 1.0 if complete, 0.0 if missing facts
    completeness_score = 1.0 if result.complete else 0.0

    score_data["completeness_score"] = completeness_score
    score_data["missing_facts"] = result.missing_facts
    score_data["completeness_reasoning"] = result.reasoning

    if result.complete:
        print("  Completeness: ✓ All facts extracted")
    else:
        print(f"  Completeness: ✗ Missing {len(result.missing_facts)} facts")

    return score_data


def run_relevance_mode(
    article: dict,
    team_info: dict,
    facts: list[dict],
    score_data: dict,
    llm: ChatOpenAI,
) -> dict:
    """Run relevance evaluation using LLM judge."""
    print(f"  Running relevance evaluation on {len(facts)} facts...")

    relevance_details = []
    team_name = team_info.get("name", "Unknown Team")

    # Create structured output chain
    relevance_chain = llm.with_structured_output(RelevanceJudgment)

    for i, fact in enumerate(facts):
        # Skip relevance judgment for relevant_players - assume they are relevant
        if fact["category"] == "relevant_players":
            print(f"    Skipping fact {i + 1}/{len(facts)} (relevant_players)... ⊘")
            relevance_details.append(
                {
                    "category": fact["category"],
                    "fact": fact["fact"],
                    "relevant": True,
                    "notes": "",
                }
            )
            continue

        print(f"    Evaluating fact {i + 1}/{len(facts)}...", end=" ", flush=True)

        messages = [
            {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": RELEVANCE_USER_PROMPT.format(
                    team_name=team_name,
                    category=fact["category"],
                    fact=fact["fact"],
                ),
            },
        ]

        result: RelevanceJudgment = relevance_chain.invoke(messages)

        relevance_details.append(
            {
                "category": fact["category"],
                "fact": fact["fact"],
                "relevant": result.relevant,
                "notes": result.notes,
            }
        )

        status = "✓" if result.relevant else "✗"
        print(status)

    # Calculate relevance score
    relevant_count = sum(1 for d in relevance_details if d["relevant"])
    relevance_score = (
        relevant_count / len(relevance_details) if relevance_details else 0.0
    )

    score_data["relevance_score"] = round(relevance_score, 4)
    score_data["relevance_details"] = relevance_details

    print(
        f"  Relevance: {relevant_count}/{len(relevance_details)} = {relevance_score:.1%}"
    )

    return score_data


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="LLM-as-Judge evaluation of AI-extracted facts from NFL articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  accuracy      - Verify each fact against the source article using LLM
  completeness  - Check if any relevant facts were missed using LLM
  relevance     - Assess if facts are relevant for game predictions using LLM
  all           - Run all three modes sequentially

Examples:
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode accuracy
    python -m nfl_agent.scripts.evaluate_summaries_llm_as_judge --mode all --overwrite
        """,
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["accuracy", "completeness", "relevance", "all"],
        default="all",
        help="Evaluation mode (default: all)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-evaluate articles that already have scores for the selected mode",
    )
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=DEFAULT_ARTICLES_DIR,
        help="Directory containing article JSON files",
    )
    parser.add_argument(
        "--team-info-dir",
        type=Path,
        default=DEFAULT_TEAM_INFO_DIR,
        help="Directory containing team_info JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for output score files",
    )

    args = parser.parse_args()

    # Validate directories
    if not args.articles_dir.exists():
        print(f"Error: Articles directory not found: {args.articles_dir}")
        sys.exit(1)

    if not args.team_info_dir.exists():
        print(f"Error: Team info directory not found: {args.team_info_dir}")
        sys.exit(1)

    # Find article pairs
    pairs = find_article_pairs(args.articles_dir, args.team_info_dir)

    if not pairs:
        print("Error: No matching article pairs found")
        sys.exit(1)

    # Determine which modes to run
    modes_to_run = (
        ["accuracy", "completeness", "relevance"] if args.mode == "all" else [args.mode]
    )

    # Get LLM client
    llm = get_llm_client()
    settings = get_setting(LLMJudgeSettings)

    print("LLM Judge Evaluation")
    print("=" * 60)
    print(f"Model: {settings.llm_model_name}")
    print(f"Found {len(pairs)} articles with team info")
    print(f"Modes: {', '.join(modes_to_run)}")
    print(f"Output: {args.output_dir}")
    print("=" * 60)
    print()

    evaluated_count = 0
    skipped_count = 0

    for i, (article_id, article_path, team_info_path) in enumerate(pairs):
        print(f"[{i + 1}/{len(pairs)}] Article {article_id}")

        # Load article and team_info
        with open(article_path) as f:
            article = json.load(f)

        with open(team_info_path) as f:
            team_info = json.load(f)

        # Load or create score file
        score_path = args.output_dir / f"{article_id}_llm_judge_summary_score.json"
        score_data = load_score_file(score_path)
        score_data["id"] = article_id
        score_data["model"] = settings.llm_model_name

        # Extract facts
        facts = extract_all_facts(team_info)

        if not facts:
            print("  Skipping: No facts extracted")
            skipped_count += 1
            continue

        # Check which modes need to run
        modes_needed = []
        for mode in modes_to_run:
            if args.overwrite or not mode_already_complete(score_data, mode):
                modes_needed.append(mode)

        if not modes_needed:
            print("  Skipping: Already evaluated")
            skipped_count += 1
            continue

        # Run each needed mode
        for mode in modes_needed:
            try:
                if mode == "accuracy":
                    score_data = run_accuracy_mode(
                        article, team_info, facts, score_data, llm
                    )
                elif mode == "completeness":
                    score_data = run_completeness_mode(
                        article, team_info, facts, score_data, llm
                    )
                elif mode == "relevance":
                    score_data = run_relevance_mode(
                        article, team_info, facts, score_data, llm
                    )

                # Add timestamp
                score_data["evaluated_at"] = datetime.now().isoformat()

                # Save after each mode
                save_score_file(score_path, score_data)

            except Exception as e:
                print(f"  Error in {mode} mode: {e}")
                continue

        evaluated_count += 1
        print(f"  Saved to {score_path.name}")
        print()

    # Summary
    print("=" * 60)
    print("Evaluation complete!")
    print(f"  Evaluated: {evaluated_count} articles")
    if skipped_count > 0:
        print(f"  Skipped: {skipped_count} articles")
    print(f"  Results saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
