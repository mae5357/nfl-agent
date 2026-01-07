"""
Article Relevance LLM Evaluation Experiment

Evaluates whether search_nfl() consistently picks the most relevant article
(score 3) from a set of articles with varying relevance scores.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import random
import json
import csv
from collections import Counter
import argparse
from datetime import datetime
import time

import numpy as np
from scipy import stats
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from openai import RateLimitError

from nfl_agent.src.models.espn_search import ESPNSearchArticle
from nfl_agent.src.tools.article_fetcher import TeamArticleQueryState, search_nfl

import dotenv

dotenv.load_dotenv()

# =============================================================================
# Phase 1: Data Models and Trial Generator
# =============================================================================


class LabeledArticle(BaseModel):
    """Article with human-labeled relevance score."""

    id: int
    headline: str
    description: str
    human_labelled_relevance_score: int
    raw_data: dict  # Full article data for passing to LLM

    @classmethod
    def from_raw(cls, data: dict) -> "LabeledArticle":
        return cls(
            id=data["id"],
            headline=data["headline"],
            description=data.get("description", ""),
            human_labelled_relevance_score=data["human_labelled_relevance_score"],
            raw_data=data,
        )


class TrialDifficulty(str, Enum):
    EASY = "easy"  # More score-3 than score-2
    MEDIUM = "medium"  # Balanced
    HARD = "hard"  # More score-2 than score-3


class Trial(BaseModel):
    """A single evaluation trial."""

    trial_id: int
    articles: List[LabeledArticle]
    group_size: int
    difficulty: Optional[TrialDifficulty] = None

    # Results (filled after running)
    selected_article_id: Optional[int] = None
    selected_article_score: Optional[int] = None
    max_score_in_group: int = 3
    is_success: Optional[bool] = None  # Did LLM pick a max-score article?

    @property
    def score_distribution(self) -> dict:
        return dict(Counter(a.human_labelled_relevance_score for a in self.articles))

    @property
    def random_baseline(self) -> float:
        """Expected success rate if picking uniformly at random."""
        num_best = sum(
            1
            for a in self.articles
            if a.human_labelled_relevance_score == self.max_score_in_group
        )
        return num_best / len(self.articles)


class TrialGenerator:
    """Generates stratified trials from labeled articles."""

    def __init__(self, articles: List[LabeledArticle], seed: int = 42):
        self.articles = articles
        self.by_score = {
            i: [a for a in articles if a.human_labelled_relevance_score == i]
            for i in range(4)
        }
        self.rng = random.Random(seed)

    def generate_trials(
        self,
        group_size: int,
        num_trials: int,
        difficulty: Optional[TrialDifficulty] = None,
    ) -> List[Trial]:
        """Generate trials with at least one score-3 article each."""
        trials = []

        for trial_id in range(num_trials):
            if difficulty:
                articles = self._generate_stratified_group(group_size, difficulty)
            else:
                articles = self._generate_random_group(group_size)

            trials.append(
                Trial(
                    trial_id=trial_id,
                    articles=articles,
                    group_size=group_size,
                    difficulty=difficulty,
                )
            )

        return trials

    def _generate_random_group(self, size: int) -> List[LabeledArticle]:
        """Generate a random group with at least one score-3 article."""
        # Ensure at least one score-3
        score_3_articles = self.by_score[3]
        must_include = [self.rng.choice(score_3_articles)]

        # Fill rest randomly from all articles (excluding the must-include)
        remaining_pool = [a for a in self.articles if a.id != must_include[0].id]
        rest = self.rng.sample(remaining_pool, min(size - 1, len(remaining_pool)))

        result = must_include + rest
        self.rng.shuffle(result)
        return result

    def _generate_stratified_group(
        self, size: int, difficulty: TrialDifficulty
    ) -> List[LabeledArticle]:
        """Generate a group with controlled score distribution."""
        if difficulty == TrialDifficulty.EASY:
            # More 3s than 2s, some noise from 0-1
            num_3 = max(2, size // 2)
            num_2 = size // 4
            num_low = size - num_3 - num_2
        elif difficulty == TrialDifficulty.MEDIUM:
            # Balanced 3s and 2s
            num_3 = max(1, size // 3)
            num_2 = max(1, size // 3)
            num_low = size - num_3 - num_2
        else:  # HARD
            # Fewer 3s, more 2s
            num_3 = max(1, size // 4)
            num_2 = size // 2
            num_low = size - num_3 - num_2

        # Sample from each bucket
        selected = []
        selected.extend(
            self.rng.sample(self.by_score[3], min(num_3, len(self.by_score[3])))
        )
        selected.extend(
            self.rng.sample(self.by_score[2], min(num_2, len(self.by_score[2])))
        )

        low_pool = self.by_score[0] + self.by_score[1]
        selected.extend(self.rng.sample(low_pool, min(num_low, len(low_pool))))

        # Pad if needed
        while len(selected) < size:
            remaining = [a for a in self.articles if a not in selected]
            if not remaining:
                break
            selected.append(self.rng.choice(remaining))

        self.rng.shuffle(selected)
        return selected[:size]


# =============================================================================
# Phase 2: Experiment Runner
# =============================================================================


class ExperimentConfig(BaseModel):
    """Configuration for an experiment run."""

    group_sizes: List[int] = Field(default=[3, 5, 10, 20])
    trials_per_size: int = 100
    seed: int = 42
    team_name: str = "Philadelphia Eagles"
    difficulties: Optional[List[TrialDifficulty]] = None  # None = random sampling
    delay_between_calls: float = Field(
        default=1.0,
        description="Seconds to wait between LLM calls to avoid rate limits",
    )


class ArticleSummary(BaseModel):
    """Compact article info for debugging."""

    id: int
    headline: str
    description: str
    score: int
    was_selected: bool = False


class TrialResult(BaseModel):
    """Result of a single trial."""

    trial_id: int
    group_size: int
    difficulty: Optional[TrialDifficulty]
    selected_article_id: int
    selected_article_score: int
    max_score_in_group: int
    is_success: bool
    random_baseline: float
    score_distribution: dict

    # For debugging: all articles that were compared
    articles_compared: List[ArticleSummary] = []


class ExperimentResults(BaseModel):
    """Aggregated results from an experiment."""

    config: ExperimentConfig
    total_trials: int
    total_successes: int
    success_rate: float
    random_baseline_avg: float
    lift_over_random: float
    p_value: float  # One-sided binomial test
    confidence_interval_95: tuple[float, float]

    # Breakdown by group size
    by_group_size: dict[int, dict]  # {size: {success_rate, n_trials, ...}}

    # Breakdown by difficulty (if stratified)
    by_difficulty: Optional[dict[str, dict]] = None

    # All individual trial results
    trials: List[TrialResult]


def _article_to_espn_format(article: LabeledArticle) -> ESPNSearchArticle:
    """Convert labeled article to ESPNSearchArticle for the LLM."""
    return ESPNSearchArticle.model_validate(article.raw_data)


class ExperimentRunner:
    """Runs the article relevance evaluation experiment."""

    def __init__(self, config: ExperimentConfig, articles: List[LabeledArticle]):
        self.config = config
        self.articles = articles

        # Seed all random sources for reproducibility
        self._seed_all(config.seed)

        self.generator = TrialGenerator(articles, seed=config.seed)

    def _seed_all(self, seed: int):
        """Seed all random number generators for deterministic behavior."""
        random.seed(seed)
        np.random.seed(seed)

    def run(self) -> ExperimentResults:
        """Run all trials and compute metrics."""
        all_results: List[TrialResult] = []

        # Calculate total trials for progress tracking
        num_difficulty_levels = (
            len(self.config.difficulties) if self.config.difficulties else 1
        )
        total_trials = (
            len(self.config.group_sizes)
            * self.config.trials_per_size
            * num_difficulty_levels
        )
        completed = 0

        for group_size in self.config.group_sizes:
            if self.config.difficulties:
                for difficulty in self.config.difficulties:
                    print(
                        f"\n🔄 Running group_size={group_size}, difficulty={difficulty.value}..."
                    )
                    trials = self.generator.generate_trials(
                        group_size=group_size,
                        num_trials=self.config.trials_per_size,
                        difficulty=difficulty,
                    )
                    results = self._run_trials_with_progress(
                        trials, completed, total_trials
                    )
                    completed += len(results)
                    all_results.extend(results)
            else:
                print(f"\n🔄 Running group_size={group_size}...")
                trials = self.generator.generate_trials(
                    group_size=group_size,
                    num_trials=self.config.trials_per_size,
                    difficulty=None,
                )
                results = self._run_trials_with_progress(
                    trials, completed, total_trials
                )
                completed += len(results)
                all_results.extend(results)

        print()  # Newline after progress

        return self._compute_metrics(all_results)

    def _run_trials_with_progress(
        self, trials: List[Trial], completed: int, total: int
    ) -> List[TrialResult]:
        """Run trials with progress indicator."""
        results = []
        for i, trial in enumerate(trials):
            current = completed + i + 1
            print(
                f"\r  Trial {current}/{total} ({100 * current / total:.0f}%)...",
                end="",
                flush=True,
            )

            # Convert to ESPNSearchArticle format
            espn_articles = [_article_to_espn_format(a) for a in trial.articles]

            # Create minimal state for get_article_relevance
            state: TeamArticleQueryState = {
                "team_name": self.config.team_name,
                "team_id": 21,  # Eagles team ID
                "team_info": None,
                "articles": espn_articles,
                "selected_article": None,
                "article_content": None,
                "new_team_info": None,
                "updated_team_info": None,
            }

            # Run the LLM selection with retry logic
            result_state = self._call_llm_with_retry(state)
            selected = result_state["selected_article"]

            # Find the human label for the selected article
            selected_label = next(
                (a for a in trial.articles if a.id == selected.id), None
            )

            is_success = (
                selected_label.human_labelled_relevance_score
                == trial.max_score_in_group
            )

            # Build article summaries for debugging
            articles_compared = [
                ArticleSummary(
                    id=a.id,
                    headline=a.headline,
                    description=a.description[:200] if a.description else "",
                    score=a.human_labelled_relevance_score,
                    was_selected=(a.id == selected.id),
                )
                for a in trial.articles
            ]

            results.append(
                TrialResult(
                    trial_id=trial.trial_id,
                    group_size=trial.group_size,
                    difficulty=trial.difficulty,
                    selected_article_id=selected.id,
                    selected_article_score=selected_label.human_labelled_relevance_score,
                    max_score_in_group=trial.max_score_in_group,
                    is_success=is_success,
                    random_baseline=trial.random_baseline,
                    score_distribution=trial.score_distribution,
                    articles_compared=articles_compared,
                )
            )

            # Rate limit delay between calls (skip after last trial)
            if i < len(trials) - 1 and self.config.delay_between_calls > 0:
                time.sleep(self.config.delay_between_calls)

        return results

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: print(
            f"  ⏳ Rate limited, waiting {retry_state.next_action.sleep:.1f}s before retry {retry_state.attempt_number}/5..."
        ),
    )
    def _call_llm_with_retry(self, state: TeamArticleQueryState) -> dict:
        """Call get_article_relevance with retry logic for rate limits."""
        return search_nfl.invoke(state["team_name"])

    def _compute_metrics(self, results: List[TrialResult]) -> ExperimentResults:
        """Compute aggregate metrics from trial results."""
        n = len(results)
        successes = sum(1 for r in results if r.is_success)
        success_rate = successes / n if n > 0 else 0

        # Average random baseline across trials
        random_baseline_avg = np.mean([r.random_baseline for r in results])

        # Lift over random
        lift = (
            (success_rate - random_baseline_avg) / random_baseline_avg
            if random_baseline_avg > 0
            else 0
        )

        # Binomial test (one-sided: is LLM better than random?)
        # H0: p = random_baseline_avg, H1: p > random_baseline_avg
        p_value = stats.binomtest(
            successes, n, random_baseline_avg, alternative="greater"
        ).pvalue

        # 95% confidence interval (Wilson score interval)
        ci = self._wilson_ci(successes, n, 0.95)

        # Breakdown by group size
        by_size = {}
        for size in self.config.group_sizes:
            size_results = [r for r in results if r.group_size == size]
            if size_results:
                size_successes = sum(1 for r in size_results if r.is_success)
                size_n = len(size_results)
                by_size[size] = {
                    "n_trials": size_n,
                    "successes": size_successes,
                    "success_rate": size_successes / size_n,
                    "random_baseline": np.mean(
                        [r.random_baseline for r in size_results]
                    ),
                    "ci_95": self._wilson_ci(size_successes, size_n, 0.95),
                }

        # Breakdown by difficulty (if applicable)
        by_difficulty = None
        if self.config.difficulties:
            by_difficulty = {}
            for diff in self.config.difficulties:
                diff_results = [r for r in results if r.difficulty == diff]
                if diff_results:
                    diff_successes = sum(1 for r in diff_results if r.is_success)
                    diff_n = len(diff_results)
                    by_difficulty[diff.value] = {
                        "n_trials": diff_n,
                        "successes": diff_successes,
                        "success_rate": diff_successes / diff_n,
                        "ci_95": self._wilson_ci(diff_successes, diff_n, 0.95),
                    }

        return ExperimentResults(
            config=self.config,
            total_trials=n,
            total_successes=successes,
            success_rate=success_rate,
            random_baseline_avg=float(random_baseline_avg),
            lift_over_random=lift,
            p_value=p_value,
            confidence_interval_95=ci,
            by_group_size=by_size,
            by_difficulty=by_difficulty,
            trials=results,
        )

    @staticmethod
    def _wilson_ci(successes: int, n: int, confidence: float) -> tuple[float, float]:
        """Wilson score confidence interval for a proportion."""
        if n == 0:
            return (0.0, 1.0)

        z = stats.norm.ppf(1 - (1 - confidence) / 2)
        p_hat = successes / n

        denominator = 1 + z**2 / n
        center = (p_hat + z**2 / (2 * n)) / denominator
        spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denominator

        return (max(0, center - spread), min(1, center + spread))


# =============================================================================
# Phase 5: Failure Analysis & Debugging Interface
# =============================================================================


def get_failures(results: ExperimentResults) -> List[TrialResult]:
    """Get all failed trials."""
    return [t for t in results.trials if not t.is_success]


def get_failures_by_selected_score(
    results: ExperimentResults, score: int
) -> List[TrialResult]:
    """Get failures where LLM selected an article with a specific score."""
    return [
        t
        for t in results.trials
        if not t.is_success and t.selected_article_score == score
    ]


def print_failure_details(trial: TrialResult):
    """Print detailed view of a single failed trial."""
    print(f"\n{'=' * 70}")
    print(f"TRIAL {trial.trial_id} (Group size: {trial.group_size})")
    print(f"{'=' * 70}")
    print(f"Score distribution: {trial.score_distribution}")
    print(f"Random baseline: {trial.random_baseline:.1%}")
    print("\nArticles compared:")
    print("-" * 70)

    # Sort by score descending, selected article first
    sorted_articles = sorted(
        trial.articles_compared, key=lambda a: (-a.was_selected, -a.score)
    )

    for a in sorted_articles:
        marker = ">>> SELECTED <<<" if a.was_selected else ""
        score_indicator = "⭐" * a.score if a.score > 0 else "☆"
        print(f"\n[Score {a.score}] {score_indicator} {marker}")
        print(f"ID: {a.id}")
        print(f"Headline: {a.headline}")
        print(f"Description: {a.description}...")

    print(f"\n{'=' * 70}")


def print_failures_summary(results: ExperimentResults, max_show: int = 10):
    """Print summary of failures with option to drill down."""
    failures = get_failures(results)

    print(f"\n{'=' * 60}")
    print("FAILURE ANALYSIS")
    print(f"{'=' * 60}")
    print(f"\nTotal failures: {len(failures)} / {results.total_trials}")

    # Breakdown by selected score
    by_score: dict[int, int] = {}
    for f in failures:
        score = f.selected_article_score
        by_score[score] = by_score.get(score, 0) + 1

    print("\nFailures by selected score:")
    for score in sorted(by_score.keys(), reverse=True):
        print(f"  Selected score {score}: {by_score[score]} failures")

    # Breakdown by group size
    by_size: dict[int, int] = {}
    for f in failures:
        by_size[f.group_size] = by_size.get(f.group_size, 0) + 1

    print("\nFailures by group size:")
    for size in sorted(by_size.keys()):
        total_for_size = sum(1 for t in results.trials if t.group_size == size)
        print(f"  Size {size}: {by_size[size]}/{total_for_size} failures")

    # Show first N failures
    print(f"\n--- First {min(max_show, len(failures))} failures ---")
    for f in failures[:max_show]:
        selected = next(a for a in f.articles_compared if a.was_selected)
        best_available = max(a.score for a in f.articles_compared)
        print(f"\nTrial {f.trial_id} (size {f.group_size}):")
        print(f"  Selected: [{selected.score}] {selected.headline[:60]}...")
        print(f"  Best available: score {best_available}")


def generate_csv_report(
    results: ExperimentResults,
    output_path: str = "nfl_agent/experiments/artifacts/trials.csv",
) -> str:
    """Generate a CSV report with trial-level data."""
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(
            [
                "trial_id",
                "group_size",
                "difficulty",
                "is_success",
                "selected_article_id",
                "selected_article_score",
                "max_score_in_group",
                "random_baseline",
                "score_distribution",
                "num_articles_compared",
            ]
        )

        # Write trial data
        for trial in results.trials:
            writer.writerow(
                [
                    trial.trial_id,
                    trial.group_size,
                    trial.difficulty.value if trial.difficulty else "",
                    trial.is_success,
                    trial.selected_article_id,
                    trial.selected_article_score,
                    trial.max_score_in_group,
                    f"{trial.random_baseline:.4f}",
                    json.dumps(trial.score_distribution),
                    len(trial.articles_compared),
                ]
            )

    return output_path


def generate_markdown_summary(
    results: ExperimentResults,
    output_path: str = "nfl_agent/experiments/artifacts/summary.md",
) -> str:
    """Generate a markdown summary report."""
    failures = get_failures(results)

    # Breakdown by selected score
    by_score: dict[int, int] = {}
    for f in failures:
        score = f.selected_article_score
        by_score[score] = by_score.get(score, 0) + 1

    # Breakdown by group size
    by_size: dict[int, int] = {}
    for f in failures:
        by_size[f.group_size] = by_size.get(f.group_size, 0) + 1

    md = f"""# Article Relevance Experiment Results

## Summary

- **Total trials:** {results.total_trials}
- **Successes:** {results.total_successes} ({results.success_rate:.1%})
- **Failures:** {len(failures)} ({100 - results.success_rate * 100:.1%})
- **Random baseline:** {results.random_baseline_avg:.1%}
- **Lift over random:** {results.lift_over_random:+.1%}
- **95% Confidence Interval:** [{results.confidence_interval_95[0]:.1%}, {results.confidence_interval_95[1]:.1%}]
- **p-value:** {results.p_value:.4f}

## Results by Group Size

| Group Size | Success Rate | Trials | Baseline | 95% CI |
|------------|--------------|--------|----------|--------|
"""

    for size, metrics in sorted(results.by_group_size.items()):
        md += f"| {size} | {metrics['success_rate']:.1%} | {metrics['n_trials']} | {metrics['random_baseline']:.1%} | [{metrics['ci_95'][0]:.1%}, {metrics['ci_95'][1]:.1%}] |\n"

    if results.by_difficulty:
        md += "\n## Results by Difficulty\n\n"
        md += "| Difficulty | Success Rate | Trials | 95% CI |\n"
        md += "|------------|--------------|--------|--------|\n"
        for diff, metrics in results.by_difficulty.items():
            md += f"| {diff.upper()} | {metrics['success_rate']:.1%} | {metrics['n_trials']} | [{metrics['ci_95'][0]:.1%}, {metrics['ci_95'][1]:.1%}] |\n"

    md += "\n## Failure Analysis\n\n"
    md += "### Failures by Selected Score\n\n"
    for score in sorted(by_score.keys(), reverse=True):
        md += f"- **Score {score}:** {by_score[score]} failures\n"

    md += "\n### Failures by Group Size\n\n"
    for size in sorted(by_size.keys()):
        total_for_size = sum(1 for t in results.trials if t.group_size == size)
        md += f"- **Size {size}:** {by_size[size]}/{total_for_size} failures ({100 * by_size[size] / total_for_size:.1%})\n"

    md += "\n## Experiment Configuration\n\n"
    md += f"- **Group sizes:** {', '.join(map(str, results.config.group_sizes))}\n"
    md += f"- **Trials per size:** {results.config.trials_per_size}\n"
    md += f"- **Seed:** {results.config.seed}\n"
    md += f"- **Team:** {results.config.team_name}\n"
    if results.config.difficulties:
        md += f"- **Difficulties:** {', '.join(d.value for d in results.config.difficulties)}\n"
    md += f"- **Delay between calls:** {results.config.delay_between_calls}s\n"

    with open(output_path, "w") as f:
        f.write(md)

    return output_path


# =============================================================================
# Phase 3: CLI and Main Entry Point
# =============================================================================


def load_labeled_articles(
    path: str = "nfl_agent/tests/test_data/team_articles_labelled.json",
) -> List[LabeledArticle]:
    """Load labeled articles from JSON file."""
    with open(path) as f:
        raw_data = json.load(f)
    return [LabeledArticle.from_raw(d) for d in raw_data]


def print_results_summary(results: ExperimentResults):
    """Print a human-readable summary of results."""
    print("\n" + "=" * 60)
    print("ARTICLE RELEVANCE EXPERIMENT RESULTS")
    print("=" * 60)

    print("\n📊 Overall Results:")
    print(f"   Total trials: {results.total_trials}")
    print(f"   Successes: {results.total_successes}")
    print(f"   Success rate: {results.success_rate:.1%}")
    print(f"   Random baseline: {results.random_baseline_avg:.1%}")
    print(f"   Lift over random: {results.lift_over_random:+.1%}")
    print(
        f"   95% CI: [{results.confidence_interval_95[0]:.1%}, {results.confidence_interval_95[1]:.1%}]"
    )
    print(f"   p-value: {results.p_value:.4f}")

    print("\n📈 Results by Group Size:")
    for size, metrics in sorted(results.by_group_size.items()):
        print(
            f"   Size {size:2d}: {metrics['success_rate']:.1%} success "
            f"(n={metrics['n_trials']}, baseline={metrics['random_baseline']:.1%}, "
            f"CI=[{metrics['ci_95'][0]:.1%}, {metrics['ci_95'][1]:.1%}])"
        )

    if results.by_difficulty:
        print("\n🎯 Results by Difficulty:")
        for diff, metrics in results.by_difficulty.items():
            print(
                f"   {diff.upper():8s}: {metrics['success_rate']:.1%} success "
                f"(n={metrics['n_trials']}, CI=[{metrics['ci_95'][0]:.1%}, {metrics['ci_95'][1]:.1%}])"
            )

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run article relevance LLM evaluation experiment"
    )
    parser.add_argument(
        "--group-sizes",
        type=int,
        nargs="+",
        default=[3, 5, 10, 20],
        help="Group sizes to test (default: 3 5 10 20)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Number of trials per group size (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--stratified",
        action="store_true",
        help="Use stratified sampling by difficulty",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: results_TIMESTAMP.json)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="nfl_agent/tests/test_data/team_articles_labelled.json",
        help="Path to labeled articles JSON",
    )
    parser.add_argument(
        "--show-failures",
        type=int,
        default=0,
        metavar="N",
        help="Show detailed view of first N failures",
    )
    parser.add_argument(
        "--csv-report",
        type=str,
        default=None,
        help="Generate CSV report at this path (default: trials_TIMESTAMP.csv)",
    )
    parser.add_argument(
        "--markdown-summary",
        type=str,
        default=None,
        help="Generate Markdown summary at this path (default: summary_TIMESTAMP.md)",
    )
    parser.add_argument(
        "--analyze",
        type=str,
        default=None,
        help="Analyze existing results JSON file instead of running new experiment",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between LLM calls to avoid rate limits (default: 1.0)",
    )

    args = parser.parse_args()

    # If analyzing existing results
    if args.analyze:
        print(f"Loading existing results from {args.analyze}...")
        with open(args.analyze) as f:
            results = ExperimentResults.model_validate_json(f.read())
        print_results_summary(results)
        print_failures_summary(results)

        if args.show_failures > 0:
            failures = get_failures(results)
            print(
                f"\n--- Showing first {min(args.show_failures, len(failures))} failures ---"
            )
            for f in failures[: args.show_failures]:
                print_failure_details(f)

        # Generate CSV and Markdown reports
        csv_path = args.csv_report or args.analyze.replace(".json", "_trials.csv")
        md_path = args.markdown_summary or args.analyze.replace(".json", "_summary.md")
        generate_csv_report(results, csv_path)
        generate_markdown_summary(results, md_path)
        print(f"📊 CSV report: {csv_path}")
        print(f"📊 Markdown summary: {md_path}")
        return

    # Load data
    print(f"Loading labeled articles from {args.data_path}...")
    articles = load_labeled_articles(args.data_path)
    print(f"Loaded {len(articles)} articles")

    # Score distribution
    dist = Counter(a.human_labelled_relevance_score for a in articles)
    print(f"Score distribution: {dict(sorted(dist.items()))}")

    # Configure experiment
    config = ExperimentConfig(
        group_sizes=args.group_sizes,
        trials_per_size=args.trials,
        seed=args.seed,
        difficulties=list(TrialDifficulty) if args.stratified else None,
        delay_between_calls=args.delay,
    )

    # Run experiment
    print(
        f"\nRunning experiment with {len(config.group_sizes)} group sizes, {config.trials_per_size} trials each..."
    )
    if config.difficulties:
        print(f"Using stratified sampling: {[d.value for d in config.difficulties]}")

    runner = ExperimentRunner(config, articles)
    results = runner.run()

    # Print summary
    print_results_summary(results)

    # Failure analysis
    if args.show_failures > 0:
        failures = get_failures(results)
        print(
            f"\n--- Showing first {min(args.show_failures, len(failures))} failures ---"
        )
        for f in failures[: args.show_failures]:
            print_failure_details(f)

    # Save results
    output_path = (
        args.output
        or f"nfl_agent/experiments/artifacts/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(output_path, "w") as f:
        f.write(results.model_dump_json(indent=2))
    print(f"\n💾 Full results saved to {output_path}")

    # Generate CSV and Markdown reports
    base_path = output_path.replace(".json", "")
    csv_path = args.csv_report or f"{base_path}_trials.csv"
    md_path = args.markdown_summary or f"{base_path}_summary.md"
    generate_csv_report(results, csv_path)
    generate_markdown_summary(results, md_path)
    print(f"📊 CSV report: {csv_path}")
    print(f"📊 Markdown summary: {md_path}")

    # Print failure summary
    print_failures_summary(results)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
