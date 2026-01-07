"""
Compare two article relevance experiment results.

Usage:
    python -m nfl_agent.experiments.compare_results results_a.json results_b.json
"""

import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# Minimal models for loading results (avoid heavy imports from article_relevance_eval)
class ArticleSummary(BaseModel):
    id: int
    headline: str
    description: str
    score: int
    was_selected: bool = False


class TrialResult(BaseModel):
    trial_id: int
    group_size: int
    difficulty: Optional[str] = None
    selected_article_id: int
    selected_article_score: int
    max_score_in_group: int
    is_success: bool
    random_baseline: float
    score_distribution: dict
    articles_compared: list[ArticleSummary] = []


class ExperimentResults(BaseModel):
    total_trials: int
    total_successes: int
    success_rate: float
    random_baseline_avg: float
    lift_over_random: float
    p_value: float
    confidence_interval_95: tuple[float, float]
    by_group_size: dict[str, dict]
    by_difficulty: Optional[dict[str, dict]] = None
    trials: list[TrialResult]


def load_results(path: str) -> ExperimentResults:
    """Load experiment results from JSON file."""
    with open(path) as f:
        return ExperimentResults.model_validate_json(f.read())


def compare_results(
    results_a: ExperimentResults, results_b: ExperimentResults, name_a: str, name_b: str
):
    """Compare two experiment results and print analysis."""

    # Build trial lookup by trial_id for comparison
    trials_a = {t.trial_id: t for t in results_a.trials}
    trials_b = {t.trial_id: t for t in results_b.trials}

    # Find common trials (same trial_id)
    common_ids = set(trials_a.keys()) & set(trials_b.keys())

    # Categorize trials
    both_success = []
    both_failure = []
    a_only_success = []  # A got right, B got wrong
    b_only_success = []  # B got right, A got wrong

    for trial_id in sorted(common_ids):
        ta = trials_a[trial_id]
        tb = trials_b[trial_id]

        if ta.is_success and tb.is_success:
            both_success.append((ta, tb))
        elif not ta.is_success and not tb.is_success:
            both_failure.append((ta, tb))
        elif ta.is_success and not tb.is_success:
            a_only_success.append((ta, tb))
        else:  # B success, A failure
            b_only_success.append((ta, tb))

    # Print comparison summary
    print("\n" + "=" * 70)
    print("EXPERIMENT COMPARISON")
    print("=" * 70)

    print(f"\n📁 File A: {name_a}")
    print(f"📁 File B: {name_b}")

    print("\n" + "-" * 70)
    print("OVERALL METRICS")
    print("-" * 70)

    print(f"\n{'Metric':<25} {'A':>15} {'B':>15} {'Δ (B-A)':>15}")
    print("-" * 70)

    # Success rate comparison
    diff_rate = results_b.success_rate - results_a.success_rate
    print(
        f"{'Success Rate':<25} {results_a.success_rate:>14.1%} {results_b.success_rate:>14.1%} {diff_rate:>+14.1%}"
    )

    # Total successes
    diff_success = results_b.total_successes - results_a.total_successes
    print(
        f"{'Total Successes':<25} {results_a.total_successes:>15} {results_b.total_successes:>15} {diff_success:>+15}"
    )

    # Total failures
    failures_a = results_a.total_trials - results_a.total_successes
    failures_b = results_b.total_trials - results_b.total_successes
    diff_failures = failures_b - failures_a
    print(
        f"{'Total Failures':<25} {failures_a:>15} {failures_b:>15} {diff_failures:>+15}"
    )

    # Lift over random
    diff_lift = results_b.lift_over_random - results_a.lift_over_random
    print(
        f"{'Lift over Random':<25} {results_a.lift_over_random:>+14.1%} {results_b.lift_over_random:>+14.1%} {diff_lift:>+14.1%}"
    )

    # p-value
    print(f"{'p-value':<25} {results_a.p_value:>15.2e} {results_b.p_value:>15.2e}")

    print("\n" + "-" * 70)
    print("TRIAL-BY-TRIAL COMPARISON")
    print("-" * 70)

    print(f"\nComparable trials (same trial_id): {len(common_ids)}")
    print(f"\n{'Category':<35} {'Count':>10} {'%':>10}")
    print("-" * 55)
    print(
        f"{'Both correct':<35} {len(both_success):>10} {100 * len(both_success) / len(common_ids):>9.1f}%"
    )
    print(
        f"{'Both wrong':<35} {len(both_failure):>10} {100 * len(both_failure) / len(common_ids):>9.1f}%"
    )
    print(
        f"{'A correct, B wrong':<35} {len(a_only_success):>10} {100 * len(a_only_success) / len(common_ids):>9.1f}%"
    )
    print(
        f"{'B correct, A wrong':<35} {len(b_only_success):>10} {100 * len(b_only_success) / len(common_ids):>9.1f}%"
    )

    # Winner determination
    print("\n" + "-" * 70)
    print("VERDICT")
    print("-" * 70)

    if results_a.success_rate > results_b.success_rate:
        winner = "A"
        winner_name = name_a
        improvement = results_a.success_rate - results_b.success_rate
    elif results_b.success_rate > results_a.success_rate:
        winner = "B"
        winner_name = name_b
        improvement = results_b.success_rate - results_a.success_rate
    else:
        winner = None
        improvement = 0

    if winner:
        print(f"\n🏆 {winner} wins with {improvement:.1%} higher success rate")
        print(f"   ({winner_name})")
    else:
        print("\n🤝 It's a tie!")

    # Show net change
    net_change = len(b_only_success) - len(a_only_success)
    if net_change > 0:
        print(f"\n📈 B got {net_change} more trials correct than A")
    elif net_change < 0:
        print(f"\n📈 A got {-net_change} more trials correct than B")
    else:
        print("\n📊 Same number of unique successes")

    print("\n" + "=" * 70)

    return {
        "both_success": both_success,
        "both_failure": both_failure,
        "a_only_success": a_only_success,
        "b_only_success": b_only_success,
    }


def print_trial_differences(
    comparison: dict, name_a: str, name_b: str, max_show: int = 5
):
    """Print details about trials where results differed."""

    a_only = comparison["a_only_success"]
    b_only = comparison["b_only_success"]

    if a_only:
        print(f"\n{'=' * 70}")
        print(f"TRIALS WHERE A SUCCEEDED BUT B FAILED ({len(a_only)} total)")
        print(f"{'=' * 70}")

        for i, (ta, tb) in enumerate(a_only[:max_show]):
            print(f"\n--- Trial {ta.trial_id} (group size: {ta.group_size}) ---")
            print(f"Score distribution: {ta.score_distribution}")

            # Find the article A selected (correct)
            a_selected = next(a for a in ta.articles_compared if a.was_selected)
            b_selected = next(a for a in tb.articles_compared if a.was_selected)

            print(
                f"\n  A selected (score {a_selected.score}): {a_selected.headline[:60]}..."
            )
            print(
                f"  B selected (score {b_selected.score}): {b_selected.headline[:60]}..."
            )

        if len(a_only) > max_show:
            print(f"\n... and {len(a_only) - max_show} more")

    if b_only:
        print(f"\n{'=' * 70}")
        print(f"TRIALS WHERE B SUCCEEDED BUT A FAILED ({len(b_only)} total)")
        print(f"{'=' * 70}")

        for i, (ta, tb) in enumerate(b_only[:max_show]):
            print(f"\n--- Trial {ta.trial_id} (group size: {ta.group_size}) ---")
            print(f"Score distribution: {ta.score_distribution}")

            # Find what each selected
            a_selected = next(a for a in ta.articles_compared if a.was_selected)
            b_selected = next(a for a in tb.articles_compared if a.was_selected)

            print(
                f"\n  A selected (score {a_selected.score}): {a_selected.headline[:60]}..."
            )
            print(
                f"  B selected (score {b_selected.score}): {b_selected.headline[:60]}..."
            )

        if len(b_only) > max_show:
            print(f"\n... and {len(b_only) - max_show} more")


def generate_comparison_html(
    results_a: ExperimentResults,
    results_b: ExperimentResults,
    comparison: dict,
    name_a: str,
    name_b: str,
    output_path: str,
) -> str:
    """Generate an HTML report comparing two experiment results."""

    both_success = comparison["both_success"]
    both_failure = comparison["both_failure"]
    a_only_success = comparison["a_only_success"]
    b_only_success = comparison["b_only_success"]

    total_compared = (
        len(both_success)
        + len(both_failure)
        + len(a_only_success)
        + len(b_only_success)
    )

    # Determine winner
    if results_a.success_rate > results_b.success_rate:
        winner_text = (
            f"A wins (+{(results_a.success_rate - results_b.success_rate):.1%})"
        )
        winner_color = "#3b82f6"
    elif results_b.success_rate > results_a.success_rate:
        winner_text = (
            f"B wins (+{(results_b.success_rate - results_a.success_rate):.1%})"
        )
        winner_color = "#8b5cf6"
    else:
        winner_text = "Tie"
        winner_color = "#6b7280"

    # Calculate percentages for stats bar
    pct_both_success = (
        100 * len(both_success) / total_compared if total_compared > 0 else 0
    )
    pct_a_only = 100 * len(a_only_success) / total_compared if total_compared > 0 else 0
    pct_b_only = 100 * len(b_only_success) / total_compared if total_compared > 0 else 0
    pct_both_fail = (
        100 * len(both_failure) / total_compared if total_compared > 0 else 0
    )

    # Diff classes
    def diff_class(val_b, val_a, higher_is_better=True):
        if val_b > val_a:
            return "diff-positive" if higher_is_better else "diff-negative"
        elif val_b < val_a:
            return "diff-negative" if higher_is_better else "diff-positive"
        return "diff-neutral"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Experiment Comparison: {Path(name_a).stem} vs {Path(name_b).stem}</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1400px; margin: 0 auto; padding: 20px; background: #0f172a; color: #e2e8f0;
        }}
        h1 {{ color: #f8fafc; }}
        h2 {{ color: #cbd5e1; border-bottom: 2px solid #334155; padding-bottom: 10px; }}
        h3 {{ color: #94a3b8; }}
        .card {{ 
            background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        .summary-grid {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;
        }}
        .metric-card {{
            background: #1e293b; padding: 20px; border-radius: 12px; text-align: center;
        }}
        .metric-card.a {{ border-left: 4px solid #3b82f6; }}
        .metric-card.b {{ border-left: 4px solid #8b5cf6; }}
        .metric-value {{ font-size: 2.5em; font-weight: bold; }}
        .metric-value.a {{ color: #3b82f6; }}
        .metric-value.b {{ color: #8b5cf6; }}
        .metric-label {{ color: #94a3b8; margin-top: 5px; }}
        .comparison-table {{
            width: 100%; border-collapse: collapse; margin: 20px 0;
        }}
        .comparison-table th, .comparison-table td {{
            padding: 12px; text-align: left; border-bottom: 1px solid #334155;
        }}
        .comparison-table th {{ color: #94a3b8; font-weight: 500; }}
        .comparison-table td {{ color: #e2e8f0; }}
        .comparison-table tr:hover {{ background: #334155; }}
        .diff-positive {{ color: #22c55e; }}
        .diff-negative {{ color: #ef4444; }}
        .diff-neutral {{ color: #94a3b8; }}
        .winner-badge {{
            display: inline-block; padding: 8px 16px; border-radius: 9999px;
            font-weight: bold; font-size: 1.2em; margin: 10px 0;
            background: {winner_color}; color: white;
        }}
        .trial {{ 
            background: #1e293b; padding: 15px; border-radius: 8px; margin-bottom: 12px;
            border-left: 4px solid #475569;
        }}
        .trial.a-won {{ border-left-color: #3b82f6; }}
        .trial.b-won {{ border-left-color: #8b5cf6; }}
        .article {{ 
            padding: 10px; margin: 8px 0; border-radius: 6px; background: #334155;
        }}
        .article.selected-a {{ border: 2px solid #3b82f6; }}
        .article.selected-b {{ border: 2px solid #8b5cf6; }}
        .article.best {{ background: #166534; }}
        .score {{ 
            display: inline-block; padding: 2px 8px; border-radius: 4px; 
            font-weight: bold; margin-right: 8px; font-size: 0.9em;
        }}
        .score-3 {{ background: #22c55e; color: white; }}
        .score-2 {{ background: #84cc16; color: black; }}
        .score-1 {{ background: #facc15; color: black; }}
        .score-0 {{ background: #ef4444; color: white; }}
        .tabs {{
            display: flex; gap: 10px; margin-bottom: 20px;
        }}
        .tab {{
            padding: 10px 20px; border-radius: 8px; cursor: pointer;
            background: #334155; color: #94a3b8; border: none; font-size: 1em;
        }}
        .tab:hover {{ background: #475569; }}
        .tab.active {{ background: #3b82f6; color: white; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .headline {{ font-weight: 600; color: #f8fafc; }}
        .description {{ color: #94a3b8; font-size: 0.9em; margin-top: 5px; }}
        .file-label {{ 
            display: inline-block; padding: 4px 12px; border-radius: 4px;
            font-size: 0.85em; margin-right: 10px;
        }}
        .file-label.a {{ background: #1e40af; color: #93c5fd; }}
        .file-label.b {{ background: #5b21b6; color: #c4b5fd; }}
        .stats-bar {{
            display: flex; height: 30px; border-radius: 6px; overflow: hidden; margin: 15px 0;
        }}
        .stats-bar-segment {{
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: bold; font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <h1>🏈 Experiment Comparison</h1>
    
    <div class="card">
        <p><span class="file-label a">A</span> {name_a}</p>
        <p><span class="file-label b">B</span> {name_b}</p>
        <div style="text-align: center; margin-top: 20px;">
            <span class="winner-badge">🏆 {winner_text}</span>
        </div>
    </div>
    
    <div class="summary-grid">
        <div class="metric-card a">
            <div class="metric-value a">{results_a.success_rate:.1%}</div>
            <div class="metric-label">A Success Rate</div>
            <div style="margin-top: 10px; color: #64748b;">
                {results_a.total_successes}/{results_a.total_trials} trials
            </div>
        </div>
        <div class="metric-card b">
            <div class="metric-value b">{results_b.success_rate:.1%}</div>
            <div class="metric-label">B Success Rate</div>
            <div style="margin-top: 10px; color: #64748b;">
                {results_b.total_successes}/{results_b.total_trials} trials
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>📊 Metrics Comparison</h2>
        <table class="comparison-table">
            <tr>
                <th>Metric</th>
                <th>A</th>
                <th>B</th>
                <th>Difference (B-A)</th>
            </tr>
            <tr>
                <td>Success Rate</td>
                <td>{results_a.success_rate:.1%}</td>
                <td>{results_b.success_rate:.1%}</td>
                <td class="{diff_class(results_b.success_rate, results_a.success_rate)}">
                    {results_b.success_rate - results_a.success_rate:+.1%}
                </td>
            </tr>
            <tr>
                <td>Total Successes</td>
                <td>{results_a.total_successes}</td>
                <td>{results_b.total_successes}</td>
                <td class="{diff_class(results_b.total_successes, results_a.total_successes)}">
                    {results_b.total_successes - results_a.total_successes:+d}
                </td>
            </tr>
            <tr>
                <td>Total Failures</td>
                <td>{results_a.total_trials - results_a.total_successes}</td>
                <td>{results_b.total_trials - results_b.total_successes}</td>
                <td class="{diff_class(results_b.total_trials - results_b.total_successes, results_a.total_trials - results_a.total_successes, higher_is_better=False)}">
                    {(results_b.total_trials - results_b.total_successes) - (results_a.total_trials - results_a.total_successes):+d}
                </td>
            </tr>
            <tr>
                <td>Lift over Random</td>
                <td>{results_a.lift_over_random:+.1%}</td>
                <td>{results_b.lift_over_random:+.1%}</td>
                <td class="{diff_class(results_b.lift_over_random, results_a.lift_over_random)}">
                    {results_b.lift_over_random - results_a.lift_over_random:+.1%}
                </td>
            </tr>
            <tr>
                <td>p-value</td>
                <td>{results_a.p_value:.2e}</td>
                <td>{results_b.p_value:.2e}</td>
                <td class="diff-neutral">-</td>
            </tr>
        </table>
    </div>
    
    <div class="card">
        <h2>🎯 Trial-by-Trial Comparison</h2>
        <p>Comparing {total_compared} trials with matching IDs:</p>
        
        <div class="stats-bar">
            <div class="stats-bar-segment" style="width: {pct_both_success:.0f}%; background: #22c55e;">
                {len(both_success)}
            </div>
            <div class="stats-bar-segment" style="width: {pct_a_only:.0f}%; background: #3b82f6;">
                {len(a_only_success)}
            </div>
            <div class="stats-bar-segment" style="width: {pct_b_only:.0f}%; background: #8b5cf6;">
                {len(b_only_success)}
            </div>
            <div class="stats-bar-segment" style="width: {pct_both_fail:.0f}%; background: #ef4444;">
                {len(both_failure)}
            </div>
        </div>
        <div style="display: flex; justify-content: space-around; margin-top: 10px; font-size: 0.9em;">
            <span>🟢 Both correct: {len(both_success)}</span>
            <span>🔵 A only: {len(a_only_success)}</span>
            <span>🟣 B only: {len(b_only_success)}</span>
            <span>🔴 Both wrong: {len(both_failure)}</span>
        </div>
    </div>
    
    <div class="tabs">
        <button class="tab active" onclick="showTab('a-only')">A Won ({len(a_only_success)})</button>
        <button class="tab" onclick="showTab('b-only')">B Won ({len(b_only_success)})</button>
        <button class="tab" onclick="showTab('both-fail')">Both Failed ({len(both_failure)})</button>
    </div>
    
    <div id="a-only" class="tab-content active">
        <h3>Trials where A succeeded but B failed</h3>
"""

    if a_only_success:
        for ta, tb in a_only_success:
            a_selected = next(a for a in ta.articles_compared if a.was_selected)
            b_selected = next(a for a in tb.articles_compared if a.was_selected)

            html += f"""
        <div class="trial a-won">
            <h4>Trial {ta.trial_id} (size {ta.group_size})</h4>
            <p style="color: #94a3b8;">Distribution: {ta.score_distribution}</p>
            
            <div class="article selected-a">
                <span class="score score-{a_selected.score}">{a_selected.score}</span>
                <span style="color: #3b82f6; font-weight: bold;">A selected ✓</span>
                <div class="headline">{a_selected.headline}</div>
                <div class="description">{a_selected.description}</div>
            </div>
            
            <div class="article selected-b">
                <span class="score score-{b_selected.score}">{b_selected.score}</span>
                <span style="color: #8b5cf6; font-weight: bold;">B selected ✗</span>
                <div class="headline">{b_selected.headline}</div>
                <div class="description">{b_selected.description}</div>
            </div>
        </div>
"""
    else:
        html += "<p style='color: #64748b;'>No trials where only A succeeded.</p>"

    html += """
    </div>
    
    <div id="b-only" class="tab-content">
        <h3>Trials where B succeeded but A failed</h3>
"""

    if b_only_success:
        for ta, tb in b_only_success:
            a_selected = next(a for a in ta.articles_compared if a.was_selected)
            b_selected = next(a for a in tb.articles_compared if a.was_selected)

            html += f"""
        <div class="trial b-won">
            <h4>Trial {ta.trial_id} (size {ta.group_size})</h4>
            <p style="color: #94a3b8;">Distribution: {ta.score_distribution}</p>
            
            <div class="article selected-a">
                <span class="score score-{a_selected.score}">{a_selected.score}</span>
                <span style="color: #3b82f6; font-weight: bold;">A selected ✗</span>
                <div class="headline">{a_selected.headline}</div>
                <div class="description">{a_selected.description}</div>
            </div>
            
            <div class="article selected-b">
                <span class="score score-{b_selected.score}">{b_selected.score}</span>
                <span style="color: #8b5cf6; font-weight: bold;">B selected ✓</span>
                <div class="headline">{b_selected.headline}</div>
                <div class="description">{b_selected.description}</div>
            </div>
        </div>
"""
    else:
        html += "<p style='color: #64748b;'>No trials where only B succeeded.</p>"

    html += """
    </div>
    
    <div id="both-fail" class="tab-content">
        <h3>Trials where both A and B failed</h3>
"""

    if both_failure:
        for ta, tb in both_failure:
            a_selected = next(a for a in ta.articles_compared if a.was_selected)
            b_selected = next(a for a in tb.articles_compared if a.was_selected)
            best_articles = [a for a in ta.articles_compared if a.score == 3]

            html += f"""
        <div class="trial">
            <h4>Trial {ta.trial_id} (size {ta.group_size})</h4>
            <p style="color: #94a3b8;">Distribution: {ta.score_distribution}</p>
            
            <div class="article selected-a">
                <span class="score score-{a_selected.score}">{a_selected.score}</span>
                <span style="color: #3b82f6; font-weight: bold;">A selected ✗</span>
                <div class="headline">{a_selected.headline}</div>
                <div class="description">{a_selected.description}</div>
            </div>
            
            <div class="article selected-b">
                <span class="score score-{b_selected.score}">{b_selected.score}</span>
                <span style="color: #8b5cf6; font-weight: bold;">B selected ✗</span>
                <div class="headline">{b_selected.headline}</div>
                <div class="description">{b_selected.description}</div>
            </div>
            
            <p style="color: #94a3b8; margin-top: 10px;">Best available (score 3):</p>
"""
            for best in best_articles[:2]:  # Show up to 2 best articles
                html += f"""
            <div class="article best">
                <span class="score score-3">3</span>
                <span style="color: #22c55e; font-weight: bold;">Best option</span>
                <div class="headline">{best.headline}</div>
                <div class="description">{best.description}</div>
            </div>
"""
            html += "</div>"
    else:
        html += "<p style='color: #64748b;'>No trials where both failed.</p>"

    html += """
    </div>
    
    <script>
        function showTab(tabId) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }
    </script>
</body>
</html>
"""

    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Compare two article relevance experiment results"
    )
    parser.add_argument(
        "results_a",
        type=str,
        help="Path to first results JSON file (A)",
    )
    parser.add_argument(
        "results_b",
        type=str,
        help="Path to second results JSON file (B)",
    )
    parser.add_argument(
        "--show-diffs",
        type=int,
        default=5,
        metavar="N",
        help="Show detailed view of first N differing trials (default: 5)",
    )
    parser.add_argument(
        "--html",
        type=str,
        default=None,
        help="Generate HTML comparison report at this path",
    )
    parser.add_argument(
        "--name-a",
        type=str,
        default=None,
        help="Display name for results A (default: filename)",
    )
    parser.add_argument(
        "--name-b",
        type=str,
        default=None,
        help="Display name for results B (default: filename)",
    )

    args = parser.parse_args()

    # Load results
    print(f"Loading {args.results_a}...")
    results_a = load_results(args.results_a)

    print(f"Loading {args.results_b}...")
    results_b = load_results(args.results_b)

    # Use custom names or filenames
    name_a = args.name_a or Path(args.results_a).name
    name_b = args.name_b or Path(args.results_b).name

    # Run comparison
    comparison = compare_results(results_a, results_b, name_a, name_b)

    # Show trial differences
    if args.show_diffs > 0:
        print_trial_differences(comparison, name_a, name_b, args.show_diffs)

    # Generate HTML report
    html_path = (
        args.html
        or f"nfl_agent/experiments/artifacts/comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    generate_comparison_html(
        results_a, results_b, comparison, name_a, name_b, html_path
    )
    print(f"\n📊 HTML comparison report: {html_path}")


if __name__ == "__main__":
    main()
