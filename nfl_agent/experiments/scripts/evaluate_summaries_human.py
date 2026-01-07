#!/usr/bin/env python3
"""
TUI-based evaluation tool for AI-extracted facts from NFL articles.

Uses Textual for a split-pane interface where you can read the article
while evaluating facts simultaneously.

Usage:
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode accuracy
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode completeness
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode relevance
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode all
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TextArea,
)

# Default paths
DEFAULT_ARTICLES_DIR = (
    Path(__file__).parent.parent / "tests" / "test_data" / "article_contents"
)
DEFAULT_TEAM_INFO_DIR = (
    Path(__file__).parent.parent / "tests" / "test_data" / "teamInfo"
)
DEFAULT_OUTPUT_DIR = (
    Path(__file__).parent.parent / "experiments" / "artifacts" / "summary_eval"
)


EvalMode = Literal["accuracy", "completeness", "relevance"]


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y at %I:%M %p UTC")
    except (ValueError, AttributeError):
        return ts or "Unknown"


def extract_all_facts(team_info: dict) -> list[dict]:
    """Extract all facts from team_info with their categories."""
    facts = []

    if team_info.get("coaching_summary"):
        facts.append(
            {"category": "coaching_summary", "fact": team_info["coaching_summary"]}
        )

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


class ArticlePanel(VerticalScroll):
    """Scrollable panel displaying the article content."""

    DEFAULT_CSS = """
    ArticlePanel {
        border: solid $primary;
        height: 60%;
        padding: 1 2;
    }
    
    ArticlePanel .article-headline {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }
    
    ArticlePanel .article-meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    
    ArticlePanel .article-content {
        margin-top: 1;
    }
    
    ArticlePanel .search-highlight {
        background: yellow;
        color: black;
        text-style: bold;
    }
    """

    def __init__(self, article: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self.article = article
        self.search_term = ""
        self.match_positions: list[int] = []
        self.current_match = -1

    def compose(self) -> ComposeResult:
        yield Label(
            "No article loaded", id="article-headline", classes="article-headline"
        )
        yield Label("", id="article-published", classes="article-meta")
        yield Label("", id="article-description", classes="article-meta")
        yield Static("─" * 60, id="article-separator")
        yield Static("", id="article-content-display")

    def on_mount(self) -> None:
        """Initialize content display."""
        self._update_all_fields()

    def _update_all_fields(self) -> None:
        """Update all article fields."""
        try:
            headline_label = self.query_one("#article-headline", Label)
            published_label = self.query_one("#article-published", Label)
            description_label = self.query_one("#article-description", Label)
        except Exception:
            return

        if not self.article:
            headline_label.update("No article loaded")
            published_label.update("")
            description_label.update("")
            self._update_content_display()
            return

        headline = self.article.get("headline", "No headline")
        description = self.article.get("description", "")
        published = format_timestamp(self.article.get("published", ""))

        headline_label.update(f"📰 {headline}")
        published_label.update(f"📅 {published}")
        description_label.update(f"📝 {description}" if description else "")

        self._update_content_display()

    def _update_content_display(self) -> None:
        """Update the article content with optional search highlighting."""
        try:
            display = self.query_one("#article-content-display", Static)
        except Exception:
            return

        if not self.article:
            display.update("No content available")
            return

        content = self.article.get("fetched_content", "No content available")

        if self.search_term:
            # Highlight search matches using Rich Text
            text = Text(content)
            pattern = re.compile(re.escape(self.search_term), re.IGNORECASE)

            # Find all matches and store positions
            self.match_positions = [m.start() for m in pattern.finditer(content)]

            # Highlight all matches
            for match in pattern.finditer(content):
                text.stylize("bold black on yellow", match.start(), match.end())

            # Extra highlight for current match
            if self.match_positions and 0 <= self.current_match < len(
                self.match_positions
            ):
                pos = self.match_positions[self.current_match]
                text.stylize("bold white on red", pos, pos + len(self.search_term))

            display.update(text)
        else:
            self.match_positions = []
            self.current_match = -1
            display.update(content)

    def update_article(self, article: dict) -> None:
        """Update the displayed article."""
        self.article = article
        self.search_term = ""
        self.match_positions = []
        self.current_match = -1
        self._update_all_fields()
        self.scroll_home()

    def search(self, term: str) -> int:
        """Search for term in article. Returns number of matches."""
        self.search_term = term.strip()
        self.current_match = 0 if self.search_term else -1
        self._update_content_display()
        return len(self.match_positions)

    def next_match(self) -> int:
        """Move to next search match. Returns current match index."""
        if not self.match_positions:
            return -1
        self.current_match = (self.current_match + 1) % len(self.match_positions)
        self._update_content_display()
        # Estimate scroll position (rough approximation)
        if self.article:
            content = self.article.get("fetched_content", "")
            if content and self.match_positions:
                # Scroll to approximate position
                pos = self.match_positions[self.current_match]
                # Estimate line number (assume ~80 chars per line)
                approx_line = pos // 80
                self.scroll_to(y=approx_line, animate=False)
        return self.current_match

    def prev_match(self) -> int:
        """Move to previous search match. Returns current match index."""
        if not self.match_positions:
            return -1
        self.current_match = (self.current_match - 1) % len(self.match_positions)
        self._update_content_display()
        # Estimate scroll position
        if self.article:
            content = self.article.get("fetched_content", "")
            if content and self.match_positions:
                pos = self.match_positions[self.current_match]
                approx_line = pos // 80
                self.scroll_to(y=approx_line, animate=False)
        return self.current_match

    def clear_search(self) -> None:
        """Clear search highlighting."""
        self.search_term = ""
        self.match_positions = []
        self.current_match = -1
        self._update_content_display()


class FactPanel(VerticalScroll):
    """Panel displaying the current fact being evaluated."""

    DEFAULT_CSS = """
    FactPanel {
        border: solid $accent;
        height: auto;
        max-height: 12;
        min-height: 5;
        padding: 1 2;
        margin-bottom: 1;
    }
    
    FactPanel .fact-header {
        text-style: bold;
        color: $warning;
    }
    
    FactPanel .fact-category {
        color: $text-muted;
        text-style: italic;
    }
    
    FactPanel .fact-text {
        margin-top: 1;
        color: $text;
    }
    
    FactPanel #fact-display {
        width: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fact_index = 0
        self.total_facts = 0
        self.current_fact = None

    def compose(self) -> ComposeResult:
        yield Static("No fact to display", id="fact-display")

    def update_fact(self, fact: dict | None, index: int, total: int) -> None:
        """Update the displayed fact."""
        self.current_fact = fact
        self.fact_index = index
        self.total_facts = total

        display = self.query_one("#fact-display", Static)

        if not fact:
            display.update("✅ All facts evaluated!")
            return

        category_labels = {
            "coaching_summary": "🏈 Coaching Summary",
            "injuries": "🏥 Injury",
            "strengths": "💪 Strength",
            "problem_areas": "⚠️ Problem Area",
            "relevant_players": "👤 Relevant Player",
        }

        cat_label = category_labels.get(fact["category"], fact["category"])
        text = (
            f"[bold yellow]FACT {index + 1} of {total}[/]\n"
            f"[dim italic]{cat_label}[/]\n\n"
            f"{fact['fact']}"
        )
        display.update(text)


class EvaluationApp(App):
    """Main TUI application for evaluating article facts."""

    CSS = """
    Screen {
        layout: vertical;
    }
    
    #main-container {
        height: 100%;
    }
    
    #search-container {
        height: auto;
        padding: 0 1;
        background: $surface;
    }
    
    #search-input {
        width: 100%;
    }
    
    #search-status {
        color: $text-muted;
        text-style: italic;
        height: 1;
        padding: 0 1;
    }
    
    #evaluation-container {
        height: 40%;
        padding: 1;
    }
    
    #question-label {
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }
    
    #button-container {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    
    #button-container Button {
        margin-right: 2;
    }
    
    #yes-btn {
        background: $success;
    }
    
    #no-btn {
        background: $error;
    }
    
    #skip-btn {
        background: $warning;
    }
    
    #notes-input {
        margin-top: 1;
        height: 3;
    }
    
    #missing-facts-area {
        height: 6;
        margin-top: 1;
    }
    
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    
    #progress-label {
        color: $primary;
        text-style: bold;
    }
    
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("y", "answer_yes", "Yes", show=True),
        Binding("n", "answer_no", "No", show=True),
        Binding("q", "quit_app", "Quit & Save", show=True),
        Binding("slash", "open_search", "Search (/)", show=True),
        Binding("f", "next_match", "Next (f)", show=False),
        Binding("F", "prev_match", "Prev (F)", show=False),
        Binding("escape", "close_search", "Close Search", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
    ]

    def __init__(
        self,
        pairs: list[tuple[int, Path, Path]],
        modes: list[EvalMode],
        output_dir: Path,
        overwrite: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.pairs = pairs
        self.modes = modes
        self.output_dir = output_dir
        self.overwrite = overwrite

        # State
        self.current_pair_index = 0
        self.current_mode_index = 0
        self.current_fact_index = 0

        self.article = None
        self.team_info = None
        self.facts = []
        self.score_data = {}
        self.score_path = None

        # Mode-specific state
        self.accuracy_details = []
        self.relevance_details = []
        self.completeness_has_missing = None

        self.evaluated_count = 0
        self.skipped_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            with Horizontal(id="search-container", classes="hidden"):
                yield Input(
                    placeholder="Search... (Enter to search, Esc to close, f/F for next/prev)",
                    id="search-input",
                )
            yield Label("", id="search-status", classes="hidden")
            yield ArticlePanel(id="article-panel")
            with Vertical(id="evaluation-container"):
                yield FactPanel(id="fact-panel")
                yield Label("", id="question-label")
                with Horizontal(id="button-container"):
                    yield Button("Yes (Y)", id="yes-btn", variant="success")
                    yield Button("No (N)", id="no-btn", variant="error")
                    yield Button(
                        "Next Article",
                        id="skip-btn",
                        variant="warning",
                        classes="hidden",
                    )
                yield Input(
                    placeholder="Optional notes (press Enter to continue)...",
                    id="notes-input",
                    classes="hidden",
                )
                yield TextArea(id="missing-facts-area", classes="hidden")
                yield Label("", id="progress-label")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the first article."""
        self.load_next_article()

    def load_next_article(self) -> None:
        """Load the next article that needs evaluation."""
        while self.current_pair_index < len(self.pairs):
            article_id, article_path, team_info_path = self.pairs[
                self.current_pair_index
            ]

            with open(article_path) as f:
                self.article = json.load(f)

            with open(team_info_path) as f:
                self.team_info = json.load(f)

            self.score_path = self.output_dir / f"{article_id}_summary_score.json"
            self.score_data = load_score_file(self.score_path)
            self.score_data["id"] = article_id

            self.facts = extract_all_facts(self.team_info)

            if not self.facts:
                self.skipped_count += 1
                self.current_pair_index += 1
                continue

            # Check which modes need to run
            modes_needed = []
            for mode in self.modes:
                if self.overwrite or not mode_already_complete(self.score_data, mode):
                    modes_needed.append(mode)

            if not modes_needed:
                self.skipped_count += 1
                self.current_pair_index += 1
                continue

            # Found an article to evaluate
            self.modes = modes_needed
            self.current_mode_index = 0
            self.current_fact_index = 0
            self.accuracy_details = []
            self.relevance_details = []
            self.completeness_has_missing = None

            self.update_display()
            return

        # No more articles
        self.show_completion()

    def update_display(self) -> None:
        """Update all display elements."""
        article_panel = self.query_one("#article-panel", ArticlePanel)
        article_panel.update_article(self.article)

        fact_panel = self.query_one("#fact-panel", FactPanel)
        question_label = self.query_one("#question-label", Label)
        notes_input = self.query_one("#notes-input", Input)
        missing_area = self.query_one("#missing-facts-area", TextArea)
        yes_btn = self.query_one("#yes-btn", Button)
        no_btn = self.query_one("#no-btn", Button)
        skip_btn = self.query_one("#skip-btn", Button)

        # Reset visibility
        notes_input.add_class("hidden")
        missing_area.add_class("hidden")
        yes_btn.remove_class("hidden")
        no_btn.remove_class("hidden")
        skip_btn.add_class("hidden")

        current_mode = self.modes[self.current_mode_index]
        article_id = self.score_data.get("id", "?")

        self.title = (
            f"Evaluate Summaries - Article {article_id} - {current_mode.upper()}"
        )

        if current_mode == "accuracy":
            if self.current_fact_index < len(self.facts):
                fact = self.facts[self.current_fact_index]
                fact_panel.update_fact(fact, self.current_fact_index, len(self.facts))
                question_label.update("❓ Is this fact ACCURATE based on the article?")
            else:
                self.finish_accuracy_mode()

        elif current_mode == "completeness":
            fact_panel.update_fact(None, 0, 0)
            if self.completeness_has_missing is None:
                question_label.update(
                    "❓ Are there any MISSING facts that should have been extracted?"
                )
            else:
                question_label.update(
                    "📝 Enter missing facts (one per line), then click 'Next Article'"
                )
                missing_area.remove_class("hidden")
                missing_area.focus()
                yes_btn.add_class("hidden")
                no_btn.add_class("hidden")
                skip_btn.remove_class("hidden")

        elif current_mode == "relevance":
            if self.current_fact_index < len(self.facts):
                fact = self.facts[self.current_fact_index]
                fact_panel.update_fact(fact, self.current_fact_index, len(self.facts))
                question_label.update("❓ Is this fact RELEVANT for game prediction?")
            else:
                self.finish_relevance_mode()

        self.update_progress()

    def update_progress(self) -> None:
        """Update progress indicators."""
        progress = self.query_one("#progress-label", Label)
        status = self.query_one("#status-bar", Static)

        current_mode = self.modes[self.current_mode_index]
        article_num = self.current_pair_index + 1
        total_articles = len(self.pairs)

        if current_mode in ("accuracy", "relevance"):
            progress.update(
                f"📊 Article {article_num}/{total_articles} | "
                f"Mode: {current_mode.upper()} | "
                f"Fact {self.current_fact_index + 1}/{len(self.facts)}"
            )
        else:
            progress.update(
                f"📊 Article {article_num}/{total_articles} | "
                f"Mode: {current_mode.upper()}"
            )

        status.update(
            f"  Evaluated: {self.evaluated_count} | Skipped: {self.skipped_count} | "
            f"Y/N=answer  /=search  Q=quit"
        )

    def action_scroll_up(self) -> None:
        """Scroll article panel up."""
        panel = self.query_one("#article-panel", ArticlePanel)
        panel.scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        """Scroll article panel down."""
        panel = self.query_one("#article-panel", ArticlePanel)
        panel.scroll_down(animate=False)

    def action_page_up(self) -> None:
        """Page up in article panel."""
        panel = self.query_one("#article-panel", ArticlePanel)
        panel.scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        """Page down in article panel."""
        panel = self.query_one("#article-panel", ArticlePanel)
        panel.scroll_page_down(animate=False)

    def action_open_search(self) -> None:
        """Open the search bar."""
        search_container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", Input)
        search_container.remove_class("hidden")
        search_input.focus()

    def action_close_search(self) -> None:
        """Close the search bar and clear search."""
        search_container = self.query_one("#search-container")
        search_status = self.query_one("#search-status", Label)
        search_input = self.query_one("#search-input", Input)
        article_panel = self.query_one("#article-panel", ArticlePanel)

        search_container.add_class("hidden")
        search_status.add_class("hidden")
        search_input.value = ""
        article_panel.clear_search()

    def action_next_match(self) -> None:
        """Go to next search match."""
        panel = self.query_one("#article-panel", ArticlePanel)
        if panel.match_positions:
            idx = panel.next_match()
            self._update_search_status(idx, len(panel.match_positions))

    def action_prev_match(self) -> None:
        """Go to previous search match."""
        panel = self.query_one("#article-panel", ArticlePanel)
        if panel.match_positions:
            idx = panel.prev_match()
            self._update_search_status(idx, len(panel.match_positions))

    def _update_search_status(self, current: int, total: int) -> None:
        """Update the search status label."""
        search_status = self.query_one("#search-status", Label)
        if total > 0:
            search_status.update(
                f"🔍 Match {current + 1} of {total} (f=next, F=prev, Esc=close)"
            )
            search_status.remove_class("hidden")
        else:
            search_status.update("🔍 No matches found")
            search_status.remove_class("hidden")

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        search_term = event.value.strip()
        panel = self.query_one("#article-panel", ArticlePanel)

        if search_term:
            count = panel.search(search_term)
            self._update_search_status(0 if count > 0 else -1, count)
            # Blur the input so f/F key bindings work for navigation
            panel.focus()
        else:
            panel.clear_search()
            search_status = self.query_one("#search-status", Label)
            search_status.add_class("hidden")

    def action_answer_yes(self) -> None:
        """Handle yes answer."""
        self.handle_answer(True)

    def action_answer_no(self) -> None:
        """Handle no answer."""
        self.handle_answer(False)

    def action_quit_app(self) -> None:
        """Quit and save progress."""
        self.save_current_progress()
        self.exit(message=f"✅ Saved! Evaluated {self.evaluated_count} articles.")

    @on(Button.Pressed, "#yes-btn")
    def on_yes_pressed(self) -> None:
        self.handle_answer(True)

    @on(Button.Pressed, "#no-btn")
    def on_no_pressed(self) -> None:
        self.handle_answer(False)

    @on(Button.Pressed, "#skip-btn")
    def on_skip_pressed(self) -> None:
        """Handle moving to next article in completeness mode."""
        self.finish_completeness_mode()

    def handle_answer(self, answer: bool) -> None:
        """Process the user's answer."""
        current_mode = self.modes[self.current_mode_index]

        if current_mode == "accuracy":
            fact = self.facts[self.current_fact_index]
            self.accuracy_details.append(
                {"category": fact["category"], "fact": fact["fact"], "correct": answer}
            )
            self.current_fact_index += 1
            self.update_display()

        elif current_mode == "completeness":
            self.completeness_has_missing = answer
            if not answer:
                # No missing facts, finish this mode
                self.finish_completeness_mode()
            else:
                # Show text area for missing facts
                self.update_display()

        elif current_mode == "relevance":
            fact = self.facts[self.current_fact_index]
            self.relevance_details.append(
                {
                    "category": fact["category"],
                    "fact": fact["fact"],
                    "relevant": answer,
                    "notes": "",
                }
            )
            self.current_fact_index += 1
            self.update_display()

    def finish_accuracy_mode(self) -> None:
        """Finish accuracy mode and move to next mode or article."""
        correct_count = sum(1 for d in self.accuracy_details if d["correct"])
        accuracy_score = (
            correct_count / len(self.accuracy_details) if self.accuracy_details else 0.0
        )

        self.score_data["accuracy_score"] = round(accuracy_score, 4)
        self.score_data["accuracy_details"] = self.accuracy_details

        self.advance_mode()

    def finish_completeness_mode(self) -> None:
        """Finish completeness mode."""
        missing_area = self.query_one("#missing-facts-area", TextArea)
        missing_text = missing_area.text.strip()
        missing_facts = (
            [f.strip() for f in missing_text.split("\n") if f.strip()]
            if missing_text
            else []
        )

        completeness_score = 0.0 if self.completeness_has_missing else 1.0

        self.score_data["completeness_score"] = completeness_score
        self.score_data["missing_facts"] = missing_facts

        # Reset for next article
        missing_area.clear()

        self.advance_mode()

    def finish_relevance_mode(self) -> None:
        """Finish relevance mode."""
        relevant_count = sum(1 for d in self.relevance_details if d["relevant"])
        relevance_score = (
            relevant_count / len(self.relevance_details)
            if self.relevance_details
            else 0.0
        )

        self.score_data["relevance_score"] = round(relevance_score, 4)
        self.score_data["relevance_details"] = self.relevance_details

        self.advance_mode()

    def advance_mode(self) -> None:
        """Move to next mode or next article."""
        self.current_mode_index += 1
        self.current_fact_index = 0

        if self.current_mode_index >= len(self.modes):
            # Done with all modes for this article
            save_score_file(self.score_path, self.score_data)
            self.evaluated_count += 1

            self.current_pair_index += 1
            self.load_next_article()
        else:
            # Reset for next mode
            self.accuracy_details = []
            self.relevance_details = []
            self.completeness_has_missing = None
            self.update_display()

    def save_current_progress(self) -> None:
        """Save current progress before quitting."""
        if self.score_path:
            save_score_file(self.score_path, self.score_data)

    def show_completion(self) -> None:
        """Show completion message and exit."""
        self.exit(
            message=f"✅ Complete! Evaluated {self.evaluated_count} articles, "
            f"skipped {self.skipped_count}."
        )


def main():
    parser = argparse.ArgumentParser(
        description="TUI-based evaluation of AI-extracted facts from NFL articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  accuracy      - Verify each fact against the source article (yes/no per fact)
  completeness  - Check if any relevant facts were missed
  relevance     - Assess if facts are relevant for game predictions
  all           - Run all three modes sequentially

Controls:
  Y / Click Yes  - Answer yes
  N / Click No   - Answer no
  Q              - Quit and save progress
  /              - Open search (Cmd+F style)
  f / F          - Next / previous search match
  Escape         - Close search
  Up/Down        - Scroll article
  PageUp/PageDn  - Scroll article faster

Examples:
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode accuracy
    python -m nfl_agent.scripts.evaluate_summaries_tui --mode all --overwrite
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

    if not args.articles_dir.exists():
        print(f"Error: Articles directory not found: {args.articles_dir}")
        sys.exit(1)

    if not args.team_info_dir.exists():
        print(f"Error: Team info directory not found: {args.team_info_dir}")
        sys.exit(1)

    pairs = find_article_pairs(args.articles_dir, args.team_info_dir)

    if not pairs:
        print("Error: No matching article pairs found")
        sys.exit(1)

    modes = (
        ["accuracy", "completeness", "relevance"] if args.mode == "all" else [args.mode]
    )

    print(f"Found {len(pairs)} articles with team info")
    print(f"Modes: {', '.join(modes)}")
    print("Starting TUI...")

    app = EvaluationApp(
        pairs=pairs,
        modes=modes,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )
    result = app.run()
    if result:
        print(result)


if __name__ == "__main__":
    main()
