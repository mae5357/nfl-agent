#!/usr/bin/env python3
"""
Analyze summary evaluation scores from LLM judge results.

Calculates average accuracy, completeness, and relevancy scores.
For accuracy and relevancy, stratifies results by category.

Usage:
    python -m nfl_agent.experiments.scripts.analyze_summary_scores
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def load_all_scores(artifacts_dir: Path) -> List[Dict]:
    """Load all JSON score files from the artifacts directory."""
    scores = []
    for json_file in artifacts_dir.glob("*_llm_judge_summary_score.json"):
        with open(json_file, "r") as f:
            scores.append(json.load(f))
    return scores


def calculate_overall_averages(scores: List[Dict]) -> Dict[str, float]:
    """Calculate overall average scores for accuracy, completeness, and relevancy."""
    accuracy_scores = []
    completeness_scores = []
    relevancy_scores = []

    for score_data in scores:
        if "accuracy_score" in score_data:
            accuracy_scores.append(score_data["accuracy_score"])
        if "completeness_score" in score_data:
            completeness_scores.append(score_data["completeness_score"])
        if "relevance_score" in score_data:
            relevancy_scores.append(score_data["relevance_score"])

    return {
        "accuracy": sum(accuracy_scores) / len(accuracy_scores)
        if accuracy_scores
        else 0.0,
        "completeness": sum(completeness_scores) / len(completeness_scores)
        if completeness_scores
        else 0.0,
        "relevancy": sum(relevancy_scores) / len(relevancy_scores)
        if relevancy_scores
        else 0.0,
    }


def calculate_accuracy_by_category(scores: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Calculate accuracy scores stratified by category."""
    category_stats = defaultdict(lambda: {"correct": 0, "total": 0})

    for score_data in scores:
        if "accuracy_details" not in score_data:
            continue

        for detail in score_data["accuracy_details"]:
            category = detail.get("category", "unknown")
            category_stats[category]["total"] += 1
            if detail.get("correct", False):
                category_stats[category]["correct"] += 1

    # Calculate accuracy per category
    category_accuracy = {}
    for category, stats in category_stats.items():
        if stats["total"] > 0:
            category_accuracy[category] = {
                "accuracy": stats["correct"] / stats["total"],
                "total_facts": stats["total"],
                "correct_facts": stats["correct"],
            }

    return category_accuracy


def calculate_relevancy_by_category(scores: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Calculate relevancy scores stratified by category."""
    category_stats = defaultdict(lambda: {"relevant": 0, "total": 0})

    for score_data in scores:
        if "relevance_details" not in score_data:
            continue

        for detail in score_data["relevance_details"]:
            category = detail.get("category", "unknown")
            category_stats[category]["total"] += 1
            if detail.get("relevant", False):
                category_stats[category]["relevant"] += 1

    # Calculate relevancy per category
    category_relevancy = {}
    for category, stats in category_stats.items():
        if stats["total"] > 0:
            category_relevancy[category] = {
                "relevancy": stats["relevant"] / stats["total"],
                "total_facts": stats["total"],
                "relevant_facts": stats["relevant"],
            }

    return category_relevancy


def generate_markdown(
    overall_averages: Dict[str, float],
    accuracy_by_category: Dict[str, Dict[str, float]],
    relevancy_by_category: Dict[str, Dict[str, float]],
    num_files: int,
) -> str:
    """Generate markdown content from results."""
    lines = []
    lines.append("# Summary Evaluation Score Analysis")
    lines.append("")
    lines.append(f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    lines.append(f"**Total files analyzed:** {num_files}")
    lines.append("")

    lines.append("## Overall Average Scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("|--------|-------|")
    lines.append(f"| Accuracy | {overall_averages['accuracy']:.4f} |")
    lines.append(f"| Completeness | {overall_averages['completeness']:.4f} |")
    lines.append(f"| Relevancy | {overall_averages['relevancy']:.4f} |")
    lines.append("")

    lines.append("## Accuracy by Category")
    lines.append("")
    if accuracy_by_category:
        lines.append("| Category | Accuracy | Correct Facts | Total Facts |")
        lines.append("|----------|----------|--------------|-------------|")
        for category in sorted(accuracy_by_category.keys()):
            stats = accuracy_by_category[category]
            lines.append(
                f"| {category} | {stats['accuracy']:.4f} | "
                f"{stats['correct_facts']} | {stats['total_facts']} |"
            )
    else:
        lines.append("No accuracy data available")
    lines.append("")

    lines.append("## Relevancy by Category")
    lines.append("")
    if relevancy_by_category:
        lines.append("| Category | Relevancy | Relevant Facts | Total Facts |")
        lines.append("|----------|-----------|----------------|-------------|")
        for category in sorted(relevancy_by_category.keys()):
            stats = relevancy_by_category[category]
            lines.append(
                f"| {category} | {stats['relevancy']:.4f} | "
                f"{stats['relevant_facts']} | {stats['total_facts']} |"
            )
    else:
        lines.append("No relevancy data available")
    lines.append("")

    return "\n".join(lines)


def print_results(
    overall_averages: Dict[str, float],
    accuracy_by_category: Dict[str, Dict[str, float]],
    relevancy_by_category: Dict[str, Dict[str, float]],
):
    """Print formatted results."""
    print("=" * 80)
    print("SUMMARY EVALUATION SCORE ANALYSIS")
    print("=" * 80)
    print()

    print("OVERALL AVERAGE SCORES")
    print("-" * 80)
    print(f"Accuracy:   {overall_averages['accuracy']:.4f}")
    print(f"Completeness: {overall_averages['completeness']:.4f}")
    print(f"Relevancy:  {overall_averages['relevancy']:.4f}")
    print()

    print("ACCURACY BY CATEGORY")
    print("-" * 80)
    if accuracy_by_category:
        # Sort by category name for consistent output
        for category in sorted(accuracy_by_category.keys()):
            stats = accuracy_by_category[category]
            print(
                f"{category:30s} "
                f"Accuracy: {stats['accuracy']:.4f} "
                f"({stats['correct_facts']}/{stats['total_facts']} correct)"
            )
    else:
        print("No accuracy data available")
    print()

    print("RELEVANCY BY CATEGORY")
    print("-" * 80)
    if relevancy_by_category:
        # Sort by category name for consistent output
        for category in sorted(relevancy_by_category.keys()):
            stats = relevancy_by_category[category]
            print(
                f"{category:30s} "
                f"Relevancy: {stats['relevancy']:.4f} "
                f"({stats['relevant_facts']}/{stats['total_facts']} relevant)"
            )
    else:
        print("No relevancy data available")
    print()
    print("=" * 80)


def main():
    """Main entry point."""
    artifacts_dir = (
        Path(__file__).parent.parent / "artifacts" / "summary_eval_llm_judge_v2"
    )

    if not artifacts_dir.exists():
        print(f"Error: Artifacts directory not found: {artifacts_dir}")
        return

    print(f"Loading scores from: {artifacts_dir}")
    scores = load_all_scores(artifacts_dir)
    print(f"Loaded {len(scores)} score files")
    print()

    # Calculate overall averages
    overall_averages = calculate_overall_averages(scores)

    # Calculate stratified scores
    accuracy_by_category = calculate_accuracy_by_category(scores)
    relevancy_by_category = calculate_relevancy_by_category(scores)

    # Print results
    print_results(overall_averages, accuracy_by_category, relevancy_by_category)

    # Generate and save markdown
    markdown_content = generate_markdown(
        overall_averages, accuracy_by_category, relevancy_by_category, len(scores)
    )
    output_file = artifacts_dir / "analysis_summary.md"
    with open(output_file, "w") as f:
        f.write(markdown_content)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
