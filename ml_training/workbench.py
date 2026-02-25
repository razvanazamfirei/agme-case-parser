#!/usr/bin/env python3
"""Unified ML workbench with streamlined training/evaluation/review workflows."""

from __future__ import annotations

import argparse
import json
import operator
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, override

import pandas as pd
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from utils import run_python_script

from case_parser.ml.predictor import MLPredictor
from case_parser.patterns.categorization import categorize_procedure

try:
    from ml_training.utils import CATEGORIES, normalize_category_label
except ModuleNotFoundError:
    from utils import CATEGORIES, normalize_category_label

TEXTUAL_AVAILABLE = True
TEXTUAL_IMPORT_ERROR = ""

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.events import Key
    from textual.widgets import Static
except ModuleNotFoundError as exc:
    App = object
    ComposeResult = Any
    Horizontal = object
    Vertical = object
    Key = object
    Static = object
    TEXTUAL_AVAILABLE = False
    TEXTUAL_IMPORT_ERROR = str(exc)

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CASE_DIR = PROJECT_ROOT / "Output-Supervised" / "case-list"
DEFAULT_PREPARED_DATA = PROJECT_ROOT / "ml_training_data" / "batch_prepared.csv"
DEFAULT_SEEN_DATA = PROJECT_ROOT / "ml_training_data" / "seen_train.csv"
DEFAULT_UNSEEN_DATA = PROJECT_ROOT / "ml_training_data" / "unseen_eval.csv"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml_models" / "procedure_classifier.pkl"
DEFAULT_REVIEW_OUTPUT = PROJECT_ROOT / "ml_training_data" / "review_labels.csv"
DEFAULT_REVIEW_PROGRESS = PROJECT_ROOT / "ml_training_data" / "review_progress.json"
DEFAULT_RETRAIN_DATA = (
    PROJECT_ROOT / "ml_training_data" / "seen_train_with_overrides.csv"
)
DEFAULT_REMAINING_EVAL_DATA = (
    PROJECT_ROOT / "ml_training_data" / "unseen_eval_remaining.csv"
)
OVERRIDE_CORRECTION_MULTIPLIER = 3


@dataclass
class ReviewCase:
    """A normalized review case record."""

    index: int
    procedure: str
    ml_prediction: str
    ml_confidence: float
    rule_prediction: str
    disagreement: bool
    top_predictions: list[tuple[str, float]]


@dataclass
class ReviewSessionMetrics:
    """Aggregated outcomes for a review session."""

    reviewed_this_session: int = 0
    accepted_recommended: int = 0
    skipped: int = 0
    staged_labels: list[dict[str, Any]] = field(default_factory=list)
    quit_requested: bool = False


@dataclass(frozen=True)
class ReviewPaths:
    """Resolved file paths used in review flow."""

    model_path: Path
    data_path: Path
    output_path: Path
    progress_path: Path


@dataclass(frozen=True)
class ReviewConfig:
    """Behavior configuration for review flow."""

    focus: str
    low_confidence: float
    max_cases: int | None
    ui_mode: str
    resume: bool


@dataclass
class ReviewRuntime:
    """Mutable review runtime state."""

    paths: ReviewPaths
    config: ReviewConfig
    reviewed_indices: set[int]


@dataclass(frozen=True)
class RetrainMergeSummary:
    """Outcome metrics for override-aware retraining dataset merge."""

    override_count: int
    seen_overrides_applied: int
    unseen_promoted: int
    corrected_rows_weighted: int
    rows_added_by_weighting: int
    weighting_multiplier: int
    retrain_rows: int
    remaining_eval_rows: int


@dataclass(frozen=True)
class RetrainPaths:
    """Resolved paths used by override-aware retraining flow."""

    seen_path: Path
    unseen_path: Path
    review_labels_path: Path
    retrain_output_path: Path
    eval_output_path: Path


def _procedure_title(procedure: str, max_length: int = 96) -> str:
    """Build a compact procedure title from free-form procedure text.

    Args:
        procedure: Free-form procedure text from which to derive the title.
        max_length: Maximum allowed length of the returned title string.
    Returns:
        Truncated title string, at most max_length characters.
    """
    title = procedure.split(";", 1)[0].strip()
    if not title:
        return "Procedure"
    if len(title) <= max_length:
        return title
    return f"{title[: max_length - 3]}..."


def _recommendation_source(rule_match: bool, ml_match: bool) -> str:
    """Describe which assessment(s) produced the recommendation.

    Args:
        rule_match: Whether the rule-based prediction matches the recommended label.
        ml_match: Whether the ML-based prediction matches the recommended label.
    Returns:
        Human-readable string naming the source(s) of the recommendation.
    """
    if rule_match and ml_match:
        return "Rule-based + ML-based"
    if rule_match:
        return "Rule-based"
    if ml_match:
        return "ML-based"
    return "None"


def _dim_if_needed(text: str, dim: bool) -> str:
    """Dim panel text when it is not the recommended option.

    Args:
        text: The panel text to potentially dim.
        dim: Whether to apply Rich dim styling to the text.
    Returns:
        Text wrapped in Rich dim markup if dim is True, otherwise unchanged.
    """
    if dim:
        return f"[dim]{text}[/dim]"
    return text


class ReviewApp(App):
    """Textual app for full-screen case review."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #top {
        height: 4;
        border: heavy $accent;
        padding: 0 1;
    }
    #main {
        height: 1fr;
        layout: horizontal;
    }
    #left {
        width: 3fr;
        layout: vertical;
    }
    #right {
        width: 2fr;
        layout: vertical;
    }
    .panel {
        border: round $surface;
        padding: 0 1;
    }
    #procedure {
        height: 2fr;
    }
    #assessments {
        height: 1fr;
        layout: horizontal;
    }
    .assessment {
        width: 1fr;
        height: 1fr;
        border: round $surface;
        padding: 0 1;
    }
    #recommendation {
        height: 6;
        border: heavy $success;
        content-align: center middle;
    }
    #keys {
        height: 11;
    }
    #categories {
        height: 1fr;
    }
    #status {
        height: 3;
        border: heavy $warning;
        padding: 0 1;
    }
    """

    BINDINGS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ("f", "choose_rule", "Choose Left (Rule)"),
        ("j", "choose_ml", "Choose Right (ML)"),
        ("space", "accept_recommended", "Accept Recommendation"),
        ("o", "choose_other", "Choose Other"),
        ("enter", "submit_input", "Apply Number Override"),
        ("backspace", "backspace_digit", "Delete Digit"),
        ("s", "skip_case", "Skip"),
        ("q", "save_and_quit", "Save/Quit"),
    )

    def __init__(self, queue: list[ReviewCase], runtime: ReviewRuntime) -> None:
        super().__init__()
        self.queue = queue
        self.runtime = runtime
        self.metrics = ReviewSessionMetrics()
        self.current_index = 0
        self.input_buffer = ""
        self.status_message = (
            "f=left rule, j=right ML, space=recommendation, "
            "o=Other, 1-11+Enter=override, s=skip, q=quit"
        )

    @override
    def compose(self) -> ComposeResult:
        yield Static("", id="top", classes="panel")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("", id="procedure", classes="panel")
                with Horizontal(id="assessments"):
                    yield Static("", id="rule_panel", classes="assessment")
                    yield Static("", id="ml_panel", classes="assessment")
                yield Static("", id="recommendation", classes="panel")
            with Vertical(id="right"):
                yield Static("", id="keys", classes="panel")
                yield Static("", id="categories", classes="panel")
        yield Static("", id="status", classes="panel")

    def on_mount(self) -> None:
        self._refresh_view()

    def on_key(self, event: Key) -> None:
        if not event.key.isdigit():
            return
        if len(self.input_buffer) >= 2:
            self.status_message = "Override accepts up to 2 digits (1-11)."
            self._refresh_status()
            event.stop()
            return

        self.input_buffer += event.key
        self.status_message = f"Number override: {self.input_buffer} (press Enter)"
        self._refresh_status()
        event.stop()

    def _current_case(self) -> ReviewCase | None:
        if self.current_index >= len(self.queue):
            return None
        return self.queue[self.current_index]

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        status.update(
            f"Override buffer: {self.input_buffer or '-'} | {self.status_message}"
        )

    def _refresh_view(self) -> None:
        case = self._current_case()
        if case is None:
            self.exit(self.metrics)
            return

        recommended = _recommended_category(case)
        rule_match = recommended == case.rule_prediction
        ml_match = recommended == case.ml_prediction
        rule_dim = ml_match and not rule_match
        ml_dim = rule_match and not ml_match
        focus = self.runtime.config.focus
        threshold = self.runtime.config.low_confidence

        header = self.query_one("#top", Static)
        header.update(
            "\n".join(
                [
                    (
                        f"Case {self.current_index + 1}/{len(self.queue)} | "
                        f"Source ID: {case.index} | "
                        f"Confidence: {case.ml_confidence:.2f}"
                    ),
                    (
                        f"Reviewed: {self.metrics.reviewed_this_session} | "
                        "Accepted recommended: "
                        f"{self.metrics.accepted_recommended} | "
                        f"Skipped: {self.metrics.skipped} | "
                        f"Focus: {focus} | Threshold: {threshold:.2f}"
                    ),
                ]
            )
        )

        procedure = self.query_one("#procedure", Static)
        procedure.update(
            "\n\n".join(
                [
                    f"[bold]{_procedure_title(case.procedure)}[/bold]",
                    case.procedure,
                ]
            )
        )

        rule_panel = self.query_one("#rule_panel", Static)
        rule_panel.update(
            _dim_if_needed(
                f"[bold]Rule-based Assessment[/bold]\n{case.rule_prediction}",
                dim=rule_dim,
            )
        )

        ml_panel = self.query_one("#ml_panel", Static)
        ml_panel.update(
            _dim_if_needed(
                "\n".join(
                    [
                        "[bold]ML-based Assessment[/bold]",
                        case.ml_prediction,
                        f"Confidence: {case.ml_confidence:.2f}",
                    ]
                ),
                dim=ml_dim,
            )
        )

        recommendation = self.query_one("#recommendation", Static)
        recommendation.update(
            "\n".join(
                [
                    "[bold]RECOMMENDATION[/bold]",
                    f"[bold reverse]{recommended}[/bold reverse]",
                    f"Source: {_recommendation_source(rule_match, ml_match)}",
                ]
            )
        )

        keys = self.query_one("#keys", Static)
        keys.update(
            "f: choose left panel (Rule-based)\n"
            "j: choose right panel (ML-based)\n"
            "space: accept recommendation\n"
            "o: choose Other (procedure cat)\n"
            "1-11 then Enter: category override\n"
            "Backspace: remove last digit\n"
            "s: skip case\n"
            "q: save and quit"
        )

        categories = self.query_one("#categories", Static)
        categories.update(
            "\n".join(
                [f"{idx:>2}. {category}" for idx, category in enumerate(CATEGORIES, 1)]
            )
        )

        self._refresh_status()

    def _advance_case(self) -> None:
        self.current_index += 1
        self.input_buffer = ""
        self._refresh_view()

    def _apply_choice(self, choice: str) -> None:
        case = self._current_case()
        if case is None:
            self.exit(self.metrics)
            return

        if choice == "q":
            self.metrics.quit_requested = True
            self.exit(self.metrics)
            return

        applied, status = _apply_review_choice(
            choice=choice,
            case=case,
            runtime=self.runtime,
            metrics=self.metrics,
        )
        self.status_message = status
        if applied:
            self._advance_case()
            return

        self._refresh_status()

    def action_choose_rule(self) -> None:
        self._apply_choice("f")

    def action_choose_ml(self) -> None:
        self._apply_choice("j")

    def action_accept_recommended(self) -> None:
        self._apply_choice(" ")

    def action_choose_other(self) -> None:
        self._apply_choice("o")

    def action_backspace_digit(self) -> None:
        self.input_buffer = self.input_buffer[:-1]
        self.status_message = "Updated number override buffer."
        self._refresh_status()

    def action_submit_input(self) -> None:
        if not self.input_buffer:
            self.status_message = "Type 1-11 then press Enter for override."
            self._refresh_status()
            return

        choice = self.input_buffer
        self.input_buffer = ""
        idx = int(choice)
        if not 1 <= idx <= len(CATEGORIES):
            self.status_message = f"Invalid category {idx}. Use 1-{len(CATEGORIES)}."
            self._refresh_status()
            return

        self._apply_choice(choice)

    def action_skip_case(self) -> None:
        self._apply_choice("s")

    def action_save_and_quit(self) -> None:
        self._apply_choice("q")


def _run_script_stage(name: str, script_path: Path, argv: list[str]) -> int:
    """Run one script stage with logging.

    Args:
        name: Human-readable label for the stage, used in log output.
        script_path: Path to the Python script to execute.
        argv: Command-line arguments to pass to the script.
    Returns:
        Exit code returned by the script.
    """
    command = " ".join([sys.executable, str(script_path), *argv])
    console.print(f"\n[cyan]{name}[/cyan]")
    console.print(f"[dim]$ {command}[/dim]")
    return run_python_script(script_path, argv)


def _resolve_procedure_column(df: pd.DataFrame) -> str:
    """Return the procedure text column name.

    Args:
        df: DataFrame in which to locate the procedure text column.

    Returns:
        Name of the procedure text column found in the DataFrame.

    Raises:
        ValueError: If neither expected procedure column is present.
    """
    if "AIMS_Actual_Procedure_Text" in df.columns:
        return "AIMS_Actual_Procedure_Text"
    if "procedure" in df.columns:
        return "procedure"
    raise ValueError(
        "No procedure column found (expected AIMS_Actual_Procedure_Text or procedure)"
    )


def _rule_prediction_for_procedure(procedure: str) -> str:
    rule_category, _warnings = categorize_procedure(procedure, [])
    if rule_category is None:
        return "Other (procedure cat)"
    return normalize_category_label(rule_category.value)


def _top_predictions(
    classes: Sequence[Any], probabilities: Sequence[float]
) -> list[tuple[str, float]]:
    score_map = {
        normalize_category_label(str(label)): float(prob)
        for label, prob in zip(classes, probabilities, strict=False)
    }
    return sorted(score_map.items(), key=operator.itemgetter(1), reverse=True)[:3]


def _build_review_case(
    index: int,
    procedure: str,
    ml_prediction_raw: Any,
    ml_probability_row: Sequence[float],
    classes: Sequence[Any],
) -> ReviewCase:
    ml_prediction = normalize_category_label(str(ml_prediction_raw))
    rule_prediction = _rule_prediction_for_procedure(procedure)
    top_predictions = _top_predictions(classes, ml_probability_row)
    ml_confidence = float(max(ml_probability_row))

    return ReviewCase(
        index=index,
        procedure=procedure,
        ml_prediction=ml_prediction,
        ml_confidence=ml_confidence,
        rule_prediction=rule_prediction,
        disagreement=ml_prediction != rule_prediction,
        top_predictions=top_predictions,
    )


def _should_include_case(case: ReviewCase, focus: str, low_confidence: float) -> bool:
    if focus == "disagreement":
        return case.disagreement
    if focus == "low_confidence":
        return case.ml_confidence < low_confidence
    if focus == "priority":
        return case.disagreement or case.ml_confidence < low_confidence
    return True


def _load_review_cases(
    data_path: Path,
    model_path: Path,
    config: ReviewConfig,
) -> list[ReviewCase]:
    """Load and rank review cases according to configured filters.

    Args:
        data_path: CSV file containing prepared case data to be reviewed.
        model_path: Path to the serialized ML model used to generate predictions.
        config: Review configuration controlling focus and confidence thresholds.
    Returns:
        List of ReviewCase objects sorted by disagreement then confidence.
    """
    predictor = MLPredictor.load(model_path)
    df = pd.read_csv(data_path)
    procedure_col = _resolve_procedure_column(df)

    procedures = df[procedure_col].fillna("").astype(str).tolist()
    ml_predictions = predictor.pipeline.predict(procedures)
    ml_probabilities = predictor.pipeline.predict_proba(procedures)
    classes = list(predictor.pipeline.classes_)

    cases: list[ReviewCase] = []
    for idx, raw_procedure in enumerate(procedures):
        procedure = raw_procedure.strip()
        if not procedure:
            continue

        case = _build_review_case(
            index=int(idx),
            procedure=procedure,
            ml_prediction_raw=ml_predictions[idx],
            ml_probability_row=ml_probabilities[idx],
            classes=classes,
        )
        if _should_include_case(case, config.focus, config.low_confidence):
            cases.append(case)

    cases.sort(key=lambda item: (not item.disagreement, item.ml_confidence))
    return cases


def _load_review_progress(progress_path: Path) -> dict[str, Any]:
    """Load persisted review progress payload.

    Args:
        progress_path: Path to the JSON file storing review progress.
    Returns:
        Parsed progress dict, or an empty dict if the file does not exist.
    """
    if not progress_path.exists():
        return {}
    with progress_path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _save_review_progress(runtime: ReviewRuntime) -> None:
    """Persist reviewed indices for resume support."""
    progress_path = runtime.paths.progress_path
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data_path": str(runtime.paths.data_path),
        "model_path": str(runtime.paths.model_path),
        "reviewed_indices": sorted(runtime.reviewed_indices),
    }
    with progress_path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)


def _load_reviewed_indices(paths: ReviewPaths, resume: bool) -> set[int]:
    """Load previously reviewed indices when resume mode is enabled.

    Args:
        paths: Review paths containing the progress file path to load from.
        resume: Whether to attempt loading prior progress.

    Returns:
        Set of previously reviewed case indices, or empty set if resume is
        False or no matching progress file exists.
    """
    if not resume:
        return set()

    progress = _load_review_progress(paths.progress_path)
    if not progress:
        return set()

    same_data = progress.get("data_path") == str(paths.data_path)
    same_model = progress.get("model_path") == str(paths.model_path)
    if not (same_data and same_model):
        return set()

    return set(progress.get("reviewed_indices", []))


def _save_review_labels(
    output_path: Path, session_labels: list[dict[str, Any]]
) -> None:
    """Merge and persist review labels."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_df = pd.read_csv(output_path) if output_path.exists() else pd.DataFrame()
    current_df = pd.DataFrame(session_labels)

    merged_df = pd.concat([existing_df, current_df], ignore_index=True)
    if not merged_df.empty and "procedure" in merged_df.columns:
        merged_df = merged_df.drop_duplicates(subset=["procedure"], keep="last")

    merged_df.to_csv(output_path, index=False)


def _build_action_table(recommended: str) -> Table:
    """Build compact key/action legend for classic mode.

    Args:
        recommended: The label that will be shown as the recommended option
            in the key/action legend (for example, the suggested category).
    Returns:
        Rich Table mapping keys to their review actions.
    """
    table = Table(show_header=True, box=None, pad_edge=False)
    table.add_column("Key", style="bold yellow", no_wrap=True)
    table.add_column("Action")
    table.add_row("a", f"Accept recommended ({recommended})")
    table.add_row("f", "Choose rule-based prediction")
    table.add_row("j", "Choose ML-based prediction")
    table.add_row("o", "Choose Other (procedure cat)")
    table.add_row(f"1-{len(CATEGORIES)}", "Pick category by number")
    table.add_row("s", "Skip case")
    table.add_row("q", "Save and quit")
    return table


def _build_categories_table() -> Table:
    """Build numbered category lookup table for classic mode.

    Returns:
        Rich Table of numbered category entries.
    """
    table = Table(show_header=True, box=None, pad_edge=False)
    table.add_column("#", style="bold cyan", justify="right", no_wrap=True)
    table.add_column("Category")
    for idx, category in enumerate(CATEGORIES, start=1):
        table.add_row(str(idx), category)
    return table


def _format_top_predictions(top_predictions: list[tuple[str, float]]) -> str:
    return " | ".join(
        f"{label}: {probability:.1%}" for label, probability in top_predictions
    )


def _recommended_category(case: ReviewCase) -> str:
    return case.rule_prediction if case.disagreement else case.ml_prediction


def _label_record(case: ReviewCase, selected: str) -> dict[str, Any]:
    """Create normalized label record for review output.

    Args:
        case: The review case providing procedure text and prediction fields.
        selected: The category chosen by the reviewer.

    Returns:
        Dict with procedure, human_category, rule_category, ml_category,
        confidence, notes, and source_case_id fields.
    """
    return {
        "procedure": case.procedure,
        "human_category": normalize_category_label(selected),
        "rule_category": case.rule_prediction,
        "ml_category": case.ml_prediction,
        "confidence": 3,
        "notes": "",
        "source_case_id": case.index,
    }


def _resolve_selected_category(
    choice: str, case: ReviewCase, recommended: str
) -> str | None:
    """Map user choice to final category.

    Args:
        choice: User's raw input representing the category selection.
        case: The review case providing ML and rule-based predictions.
        recommended: The recommended category to apply when accepting.
    Returns:
        Selected category string, or None if the choice is unrecognized.
    """
    other_category = "Other (procedure cat)"
    selected: str | None = None

    if choice in {"a", " "}:
        selected = recommended
    elif choice in {"m", "j"}:
        selected = case.ml_prediction
    elif choice in {"r", "f"}:
        selected = case.rule_prediction
    elif choice == "o":
        selected = other_category if other_category in CATEGORIES else CATEGORIES[-1]
    elif choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(CATEGORIES):
            selected = CATEGORIES[idx - 1]

    return selected


def _mark_reviewed(
    case: ReviewCase,
    runtime: ReviewRuntime,
    metrics: ReviewSessionMetrics,
) -> None:
    metrics.reviewed_this_session += 1
    runtime.reviewed_indices.add(case.index)
    _save_review_progress(runtime)


def _autosave_if_needed(metrics: ReviewSessionMetrics, output_path: Path) -> bool:
    if not metrics.staged_labels:
        return False
    if len(metrics.staged_labels) % 10 != 0:
        return False

    _save_review_labels(output_path, metrics.staged_labels)
    metrics.staged_labels = []
    return True


def _apply_review_choice(
    choice: str,
    case: ReviewCase,
    runtime: ReviewRuntime,
    metrics: ReviewSessionMetrics,
) -> tuple[bool, str]:
    if choice == "s":
        metrics.skipped += 1
        _mark_reviewed(case, runtime, metrics)
        return True, f"Skipped case id {case.index}."

    recommended = _recommended_category(case)
    selected = _resolve_selected_category(choice, case, recommended)
    if selected is None:
        return False, "Invalid choice."

    if choice in {"a", " "}:
        metrics.accepted_recommended += 1

    metrics.staged_labels.append(_label_record(case, selected))
    _mark_reviewed(case, runtime, metrics)

    if _autosave_if_needed(metrics, runtime.paths.output_path):
        return True, "Autosaved 10 decisions."

    return True, f"Recorded: {selected}"


def _build_case_summary(case: ReviewCase, position: int, total: int) -> str:
    recommended = _recommended_category(case)
    disagreement = " [red](disagreement)[/red]" if case.disagreement else ""
    top_text = _format_top_predictions(case.top_predictions)
    return (
        f"[bold]Case {position}/{total}[/bold] "
        f"(id={case.index}, conf={case.ml_confidence:.2f})\n"
        f"Rule: [yellow]{case.rule_prediction}[/yellow]\n"
        f"ML: [cyan]{case.ml_prediction}[/cyan]{disagreement}\n"
        f"Top ML: {top_text}\n"
        f"Recommended (a): [bold]{recommended}[/bold]"
    )


def _render_classic_case(case: ReviewCase, position: int, total: int) -> None:
    case_summary = _build_case_summary(case, position, total)
    side_panel = Group(
        Panel(
            _build_action_table(_recommended_category(case)),
            title="Keys",
            border_style="cyan",
        ),
        Panel(
            _build_categories_table(),
            title="Category Numbers",
            border_style="magenta",
        ),
    )

    layout = Table.grid(expand=True)
    layout.add_column(ratio=3)
    layout.add_column(ratio=2)
    layout.add_row(
        Panel(case_summary, title="Current Case", border_style="cyan"),
        side_panel,
    )
    console.print(layout)

    procedure_text = case.procedure[:500] + ("..." if len(case.procedure) > 500 else "")
    console.print(Panel(procedure_text, title="Procedure Text", border_style="blue"))


def _prompt_review_choice() -> str:
    while True:
        choice = (
            Prompt.ask(
                f"Choose key (a/f/j/o/1-{len(CATEGORIES)}/s/q)",
                default="a",
            )
            .strip()
            .lower()
        )
        if choice in {"a", "f", "j", "o", "s", "q"}:
            return choice
        if choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            return choice

        console.print(
            f"[yellow]Invalid key.[/yellow] Use a/f/j/o/1-{len(CATEGORIES)}/s/q."
        )


def _run_review_classic(
    queue: list[ReviewCase],
    runtime: ReviewRuntime,
) -> ReviewSessionMetrics:
    """Run classic prompt-based review mode.

    Args:
        queue: Ordered list of ``ReviewCase`` instances to be reviewed in this session.
        runtime: The ``ReviewRuntime`` containing configuration and shared state for the session.
    Returns:
        ReviewSessionMetrics with counts of reviewed, accepted, and skipped cases.
    """
    console.print(
        Panel.fit(
            "[bold cyan]Streamlined Review (Classic)[/bold cyan]\n"
            f"Queue size: {len(queue)}\n"
            f"Focus: {runtime.config.focus}\n"
            "Low-confidence threshold: "
            f"{runtime.config.low_confidence:.2f}",
            border_style="cyan",
        )
    )

    metrics = ReviewSessionMetrics()
    for position, case in enumerate(queue, start=1):
        _render_classic_case(case, position, len(queue))

        choice = _prompt_review_choice()
        if choice == "q":
            metrics.quit_requested = True
            break

        applied, status = _apply_review_choice(
            choice=choice,
            case=case,
            runtime=runtime,
            metrics=metrics,
        )
        if applied:
            if status.startswith("Autosaved"):
                console.print(f"[green]{status}[/green]")
            continue

        console.print(f"[yellow]{status}[/yellow]")

    return metrics


def _run_tui_review_session(
    queue: list[ReviewCase],
    runtime: ReviewRuntime,
) -> ReviewSessionMetrics:
    """Run full-screen review TUI using Textual.

    Args:
        queue: Ordered list of ``ReviewCase`` instances to review.
        runtime: The ``ReviewRuntime`` containing configuration and shared state.

    Returns:
        ReviewSessionMetrics collected during the TUI session.

    Raises:
        RuntimeError: If Textual is not installed.
    """
    if not TEXTUAL_AVAILABLE:
        raise RuntimeError(
            "Textual is required for TUI mode. Install dependencies with "
            "`uv sync --group ml`. "
            f"Import error: {TEXTUAL_IMPORT_ERROR}"
        )

    app = ReviewApp(queue, runtime)
    result = app.run()
    if isinstance(result, ReviewSessionMetrics):
        return result
    return app.metrics


def _print_review_summary(metrics: ReviewSessionMetrics, output_path: Path) -> None:
    """Render review summary table."""
    summary = Table(title="Review Summary", border_style="green")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Reviewed this session", str(metrics.reviewed_this_session))
    summary.add_row("Accepted recommended", str(metrics.accepted_recommended))
    summary.add_row("Skipped", str(metrics.skipped))
    summary.add_row("Output file", str(output_path))
    console.print(summary)


def _resolve_default_review_data_path() -> Path:
    """Prefer remaining unseen pool; fall back to original unseen split.

    Returns:
        Path to the remaining eval data if it exists, otherwise the original
        unseen eval split path.
    """
    remaining = DEFAULT_REMAINING_EVAL_DATA.resolve()
    if remaining.exists():
        return remaining
    return DEFAULT_UNSEEN_DATA.resolve()


def _resolve_optional_data_path(data_arg: str | Path | None) -> Path:
    if data_arg is None:
        return _resolve_default_review_data_path()
    return Path(data_arg).resolve()


def _build_review_paths(args: argparse.Namespace) -> ReviewPaths:
    data_path = _resolve_optional_data_path(args.data)
    if args.data is None:
        console.print(f"[cyan]Using default review data:[/cyan] {data_path}")

    return ReviewPaths(
        model_path=Path(args.model).resolve(),
        data_path=data_path,
        output_path=Path(args.output).resolve(),
        progress_path=Path(args.progress).resolve(),
    )


def _build_review_config(args: argparse.Namespace) -> ReviewConfig:
    return ReviewConfig(
        focus=args.focus,
        low_confidence=args.low_confidence,
        max_cases=args.max_cases,
        ui_mode=args.ui,
        resume=args.resume,
    )


def _validate_review_paths(paths: ReviewPaths) -> bool:
    if not paths.model_path.exists():
        console.print(f"[red]Model not found:[/red] {paths.model_path}")
        return False
    if not paths.data_path.exists():
        console.print(f"[red]Data file not found:[/red] {paths.data_path}")
        return False
    return True


def _build_review_runtime(args: argparse.Namespace) -> ReviewRuntime | None:
    paths = _build_review_paths(args)
    if not _validate_review_paths(paths):
        return None

    config = _build_review_config(args)
    reviewed_indices = _load_reviewed_indices(paths, config.resume)
    return ReviewRuntime(paths=paths, config=config, reviewed_indices=reviewed_indices)


def _build_review_queue(runtime: ReviewRuntime) -> list[ReviewCase]:
    cases = _load_review_cases(
        data_path=runtime.paths.data_path,
        model_path=runtime.paths.model_path,
        config=runtime.config,
    )

    if not cases:
        console.print("[yellow]No cases matched your review filters.[/yellow]")
        return []

    queue = [case for case in cases if case.index not in runtime.reviewed_indices]
    if runtime.config.max_cases is not None:
        queue = queue[: runtime.config.max_cases]

    if not queue:
        console.print(
            "[green]Everything in the selected queue is already reviewed.[/green]"
        )
    return queue


def _resolve_review_ui_mode(config: ReviewConfig) -> str:
    if config.ui_mode != "tui":
        return config.ui_mode

    if sys.stdin.isatty() and sys.stdout.isatty():
        return config.ui_mode

    console.print(
        "[yellow]TUI requires an interactive terminal; "
        "falling back to classic mode.[/yellow]"
    )
    return "classic"


def _run_review_interface(
    queue: list[ReviewCase],
    runtime: ReviewRuntime,
) -> ReviewSessionMetrics:
    ui_mode = _resolve_review_ui_mode(runtime.config)
    if ui_mode == "classic":
        return _run_review_classic(queue, runtime)

    try:
        return _run_tui_review_session(queue, runtime)
    except RuntimeError as exc:
        console.print(
            f"[yellow]TUI initialization failed ({exc}); using classic mode.[/yellow]"
        )
        return _run_review_classic(queue, runtime)


def _review_command(args: argparse.Namespace) -> int:
    """Run streamlined interactive correction workflow.

    Args:
        args: Parsed command-line arguments for the review command.
    Returns:
        0 on success or when the queue is empty, 1 if required paths are invalid.
    """
    runtime = _build_review_runtime(args)
    if runtime is None:
        return 1

    queue = _build_review_queue(runtime)
    if not queue:
        return 0

    metrics = _run_review_interface(queue, runtime)
    if metrics.staged_labels:
        _save_review_labels(runtime.paths.output_path, metrics.staged_labels)

    _print_review_summary(metrics, runtime.paths.output_path)
    return 0


def _normalize_procedure_key(value: Any) -> str:
    """Build stable lookup key for joining procedure rows across files.

    Args:
        value: Input value to normalize; may be any type. ``None`` is treated as
            an empty string, and other values are converted to a stripped,
            whitespace-normalized, uppercased string.
    Returns:
        Uppercased, whitespace-normalized string, or empty string for None.
    """
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).upper()


def _load_override_map(review_labels_path: Path) -> dict[str, str]:
    """Load latest human override per normalized procedure text.

    Args:
        review_labels_path: Path to the review labels CSV file.

    Returns:
        Dict mapping normalized procedure key to canonical human category string.

    Raises:
        ValueError: If the review labels file is missing required columns.
    """
    review_df = pd.read_csv(review_labels_path)
    required = {"procedure", "human_category"}
    missing = required.difference(review_df.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(
            f"Review labels must include columns: {missing_columns} "
            f"(file: {review_labels_path})"
        )

    cleaned = review_df.copy()
    cleaned["procedure_key"] = cleaned["procedure"].map(_normalize_procedure_key)
    cleaned["human_category"] = (
        cleaned["human_category"]
        .fillna("Other (procedure cat)")
        .astype(str)
        .map(normalize_category_label)
    )
    cleaned = cleaned[cleaned["procedure_key"] != ""]
    cleaned = cleaned.drop_duplicates(subset=["procedure_key"], keep="last")
    return dict(zip(cleaned["procedure_key"], cleaned["human_category"], strict=False))


def _upsert_label_column(df: pd.DataFrame, label_column: str) -> pd.DataFrame:
    """Ensure label column exists and normalized.

    Args:
        df: Input DataFrame to update.
        label_column: Name of the label column to ensure and normalize.

    Returns:
        Copy of df with label_column present and values normalized to canonical
        category strings.
    """
    out = df.copy()
    if label_column not in out.columns:
        out[label_column] = "Other (procedure cat)"
    out[label_column] = (
        out[label_column]
        .fillna("Other (procedure cat)")
        .astype(str)
        .map(normalize_category_label)
    )
    return out


def _build_retrain_paths(args: argparse.Namespace) -> RetrainPaths:
    return RetrainPaths(
        seen_path=Path(args.seen_data).resolve(),
        unseen_path=Path(args.unseen_data).resolve(),
        review_labels_path=Path(args.review_labels).resolve(),
        retrain_output_path=Path(args.retrain_data_output).resolve(),
        eval_output_path=Path(args.eval_data_output).resolve(),
    )


def _validate_retrain_paths(paths: RetrainPaths, force: bool) -> None:
    inputs = [paths.seen_path, paths.unseen_path, paths.review_labels_path]
    missing_inputs = [path for path in inputs if not path.exists()]
    if missing_inputs:
        for path in missing_inputs:
            console.print(f"[red]Required file not found:[/red] {path}")
        raise RuntimeError("Missing retrain inputs.")

    if force:
        return

    outputs = [paths.retrain_output_path, paths.eval_output_path]
    existing_outputs = [path for path in outputs if path.exists()]
    if not existing_outputs:
        return

    existing_text = ", ".join(str(path) for path in existing_outputs)
    raise RuntimeError(
        f"Output file(s) already exist. Use --force to overwrite: {existing_text}"
    )


def _add_procedure_key(df: pd.DataFrame, procedure_col: str) -> pd.DataFrame:
    out = df.copy()
    out["_procedure_key"] = out[procedure_col].map(_normalize_procedure_key)
    return out


def _merge_override_frames(
    seen_df: pd.DataFrame,
    unseen_df: pd.DataFrame,
    override_map: dict[str, str],
    label_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, int, int, int, int]:
    """Merge retrain frames and upweight true correction overrides.

    Args:
        seen_df: Training (seen) DataFrame with a ``_procedure_key`` column.
        unseen_df: Holdout (unseen) DataFrame with a ``_procedure_key`` column.
        override_map: Mapping of normalized procedure key to human category override.
        label_column: Name of the label column to update with overrides.

    Returns:
        Tuple of (retrain_df, remaining_eval_df, seen_overrides_applied,
        unseen_promoted, corrected_rows, rows_added_by_weighting).
    """
    seen_original_labels = seen_df[label_column].copy()
    seen_override_mask = seen_df["_procedure_key"].isin(override_map)
    seen_mapped_labels = seen_df.loc[seen_override_mask, "_procedure_key"].map(
        override_map
    )
    seen_changed_mask = pd.Series(False, index=seen_df.index)
    seen_changed_mask.loc[seen_override_mask] = (
        seen_original_labels.loc[seen_override_mask] != seen_mapped_labels
    )
    seen_df.loc[seen_override_mask, label_column] = seen_mapped_labels
    seen_df["_is_override_correction"] = seen_changed_mask

    unseen_override_mask = unseen_df["_procedure_key"].isin(override_map)
    reviewed_unseen_df = unseen_df.loc[unseen_override_mask].copy()
    reviewed_mapped_labels = reviewed_unseen_df["_procedure_key"].map(override_map)
    reviewed_unseen_df["_is_override_correction"] = (
        reviewed_unseen_df[label_column] != reviewed_mapped_labels
    )
    reviewed_unseen_df[label_column] = reviewed_mapped_labels
    remaining_eval_df = unseen_df.loc[~unseen_override_mask].copy()

    retrain_df = pd.concat([seen_df, reviewed_unseen_df], ignore_index=True)
    retrain_df = retrain_df.drop_duplicates(subset=["_procedure_key"], keep="last")
    corrected_rows = int(retrain_df["_is_override_correction"].sum())
    rows_added = 0

    if corrected_rows > 0 and OVERRIDE_CORRECTION_MULTIPLIER > 1:
        corrected_df = retrain_df.loc[retrain_df["_is_override_correction"]].copy()
        extra_frames = [corrected_df] * (OVERRIDE_CORRECTION_MULTIPLIER - 1)
        retrain_df = pd.concat([retrain_df, *extra_frames], ignore_index=True)
        rows_added = corrected_rows * (OVERRIDE_CORRECTION_MULTIPLIER - 1)

    retrain_df = retrain_df.drop(columns=["_procedure_key", "_is_override_correction"])
    remaining_eval_df = remaining_eval_df.drop(columns=["_procedure_key"])
    return (
        retrain_df,
        remaining_eval_df,
        int(seen_override_mask.sum()),
        int(unseen_override_mask.sum()),
        corrected_rows,
        rows_added,
    )


def _prepare_override_retrain_datasets(args: argparse.Namespace) -> RetrainMergeSummary:
    """Create retrain/eval datasets that incorporate human review overrides.

    Args:
        args: Parsed command-line arguments for the retrain command.

    Returns:
        RetrainMergeSummary with counts of overrides applied and rows written.

    Raises:
        RuntimeError: If required input files are missing, output files already
            exist without --force, or the override map is empty.
    """
    paths = _build_retrain_paths(args)
    _validate_retrain_paths(paths, force=args.force)

    override_map = _load_override_map(paths.review_labels_path)
    if not override_map:
        raise RuntimeError(
            "No valid overrides found in review labels file: "
            f"{paths.review_labels_path}"
        )

    seen_df = _upsert_label_column(pd.read_csv(paths.seen_path), args.label_column)
    unseen_df = _upsert_label_column(pd.read_csv(paths.unseen_path), args.label_column)
    seen_df = _add_procedure_key(seen_df, _resolve_procedure_column(seen_df))
    unseen_df = _add_procedure_key(unseen_df, _resolve_procedure_column(unseen_df))

    (
        retrain_df,
        remaining_eval_df,
        seen_overrides_applied,
        unseen_promoted,
        corrected_rows_weighted,
        rows_added_by_weighting,
    ) = _merge_override_frames(
        seen_df=seen_df,
        unseen_df=unseen_df,
        override_map=override_map,
        label_column=args.label_column,
    )

    paths.retrain_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.eval_output_path.parent.mkdir(parents=True, exist_ok=True)
    retrain_df.to_csv(paths.retrain_output_path, index=False)
    remaining_eval_df.to_csv(paths.eval_output_path, index=False)

    return RetrainMergeSummary(
        override_count=len(override_map),
        seen_overrides_applied=seen_overrides_applied,
        unseen_promoted=unseen_promoted,
        corrected_rows_weighted=corrected_rows_weighted,
        rows_added_by_weighting=rows_added_by_weighting,
        weighting_multiplier=OVERRIDE_CORRECTION_MULTIPLIER,
        retrain_rows=len(retrain_df),
        remaining_eval_rows=len(remaining_eval_df),
    )


def _print_retrain_merge_summary(
    args: argparse.Namespace,
    summary: RetrainMergeSummary,
) -> None:
    table = Table(title="Override Merge Summary", border_style="green")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Unique overrides loaded", str(summary.override_count))
    table.add_row("Seen rows relabeled", str(summary.seen_overrides_applied))
    table.add_row("Unseen reviewed rows promoted", str(summary.unseen_promoted))
    table.add_row(
        "Correction rows upweighted",
        str(summary.corrected_rows_weighted),
    )
    table.add_row(
        "Weighting multiplier",
        f"{summary.weighting_multiplier}x",
    )
    table.add_row(
        "Rows added by weighting",
        str(summary.rows_added_by_weighting),
    )
    table.add_row("Retrain dataset rows", str(summary.retrain_rows))
    table.add_row("Remaining eval rows", str(summary.remaining_eval_rows))
    table.add_row(
        "Retrain dataset file",
        str(Path(args.retrain_data_output).resolve()),
    )
    table.add_row("Eval dataset file", str(Path(args.eval_data_output).resolve()))
    console.print(table)


def _retrain_command(args: argparse.Namespace) -> int:
    """Retrain model after applying human review overrides.

    Args:
        args: Parsed command-line arguments for the retrain command.

    Returns:
        0 on success, 1 if dataset preparation fails, or the training script
        exit code if training fails.
    """
    try:
        summary = _prepare_override_retrain_datasets(args)
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    _print_retrain_merge_summary(args, summary)

    train_script = PROJECT_ROOT / "ml_training" / "train_optimized.py"
    train_argv = [
        str(Path(args.retrain_data_output).resolve()),
        "--output",
        str(Path(args.model).resolve()),
        "--label-column",
        args.label_column,
    ]
    if args.cross_validate:
        train_argv.append("--cross-validate")

    train_rc = _run_script_stage("Retrain Model", train_script, train_argv)
    if train_rc != 0:
        return train_rc

    if args.skip_evaluate:
        return 0
    if summary.remaining_eval_rows == 0:
        console.print(
            "[yellow]No remaining unseen rows after promotion; "
            "skipping evaluation.[/yellow]"
        )
        return 0

    eval_args = argparse.Namespace(model=args.model, data=args.eval_data_output)
    return _evaluate_command(eval_args)


def _auto_train_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--case-dir",
        str(Path(args.case_dir).resolve()),
        "--prepared-data",
        str(Path(args.prepared_data).resolve()),
        "--seen-data",
        str(Path(args.seen_data).resolve()),
        "--unseen-data",
        str(Path(args.unseen_data).resolve()),
        "--model-output",
        str(Path(args.model).resolve()),
        "--total-sample",
        str(args.total_sample),
        "--workers",
        str(args.workers),
        "--label-column",
        args.label_column,
        "--unseen-ratio",
        str(args.unseen_ratio),
        "--split-seed",
        str(args.split_seed),
    ]

    if args.sample_per_file is not None:
        argv.extend(["--sample-per-file", str(args.sample_per_file)])
    if args.skip_prepare:
        argv.append("--skip-prepare")
    if args.skip_split:
        argv.append("--skip-split")
    if args.skip_evaluate:
        argv.append("--skip-evaluate")
    if args.cross_validate:
        argv.append("--cross-validate")
    if args.force:
        argv.append("--force")

    return argv


def _train_command(args: argparse.Namespace) -> int:
    """Run deterministic training pipeline.

    Args:
        args: Parsed command-line arguments for the training pipeline.
    Returns:
        Exit code from the auto_train.py script.
    """
    script_path = PROJECT_ROOT / "ml_training" / "auto_train.py"
    argv = _auto_train_argv(args)
    return _run_script_stage("Training", script_path, argv)


def _evaluate_command(args: argparse.Namespace) -> int:
    """Run standalone evaluation command.

    Args:
        args: Parsed command-line arguments for the evaluate command.

    Returns:
        Exit code from the evaluate.py script.
    """
    data_path = _resolve_optional_data_path(args.data)
    if args.data is None:
        console.print(f"[cyan]Using default evaluation data:[/cyan] {data_path}")

    script_path = PROJECT_ROOT / "ml_training" / "evaluate.py"
    argv = [
        str(Path(args.model).resolve()),
        str(data_path),
    ]
    return _run_script_stage("Evaluation", script_path, argv)


def _resolve_eval_data_for_run(args: argparse.Namespace) -> Path:
    if args.eval_data is not None:
        return Path(args.eval_data).resolve()
    if args.skip_split:
        return Path(args.prepared_data).resolve()
    return Path(args.unseen_data).resolve()


def _print_next_review_step(model_path: Path, data_path: Path) -> None:
    command = (
        f"{sys.executable} "
        f"{PROJECT_ROOT / 'ml_training' / 'workbench.py'} review "
        f"--model {model_path} "
        f"--data {data_path}"
    )
    console.print(
        "\n[bold green]Next:[/bold green] "
        "Launch streamlined correction review with:\n"
        f"`{command}`"
    )


def _run_command_chain(args: argparse.Namespace) -> int:
    """Run train -> evaluate in one command and suggest next review step.

    Args:
        args: Parsed command-line options controlling training, evaluation,
            and whether to skip the evaluation step.
    Returns:
        0 on success, or the first non-zero exit code from training or evaluation.
    """
    train_args = argparse.Namespace(**vars(args))
    train_args.skip_evaluate = True

    train_rc = _train_command(train_args)
    if train_rc != 0:
        return train_rc

    if args.skip_evaluate:
        return 0

    eval_data = _resolve_eval_data_for_run(args)
    eval_args = argparse.Namespace(model=args.model, data=eval_data)
    eval_rc = _evaluate_command(eval_args)
    if eval_rc != 0:
        return eval_rc

    _print_next_review_step(Path(args.model).resolve(), eval_data)
    return 0


def _print_cli_overview() -> None:
    """Render quick command overview for interactive help."""
    commands = Table(title="Commands", border_style="cyan")
    commands.add_column("Command", style="bold cyan", no_wrap=True)
    commands.add_column("Purpose")
    commands.add_column("Typical Use", style="yellow")
    commands.add_row("run", "Prepare, split, train, evaluate", "run --force")
    commands.add_row(
        "review",
        "Review predictions and save overrides",
        "review --resume",
    )
    commands.add_row(
        "retrain",
        "Retrain model using saved overrides",
        "retrain --force",
    )
    commands.add_row(
        "evaluate",
        "Evaluate model on default or explicit CSV",
        "evaluate",
    )
    commands.add_row("train", "Run training pipeline stages directly", "train --force")

    defaults = Table(title="Built-In Paths", border_style="green")
    defaults.add_column("Purpose", style="green")
    defaults.add_column("Path")
    defaults.add_row("Model", str(DEFAULT_MODEL_PATH))
    defaults.add_row("Review labels", str(DEFAULT_REVIEW_OUTPUT))
    defaults.add_row("Seen split", str(DEFAULT_SEEN_DATA))
    defaults.add_row("Unseen split", str(DEFAULT_UNSEEN_DATA))
    defaults.add_row("Remaining unseen", str(DEFAULT_REMAINING_EVAL_DATA))

    workflow = (
        "Recommended loop:\n"
        "  1) run --force\n"
        "  2) review --resume\n"
        "  3) retrain --force\n"
        "  4) review --resume  (repeat)"
    )
    console.print(Panel.fit(workflow, title="Workflow", border_style="magenta"))
    console.print(commands)
    console.print(defaults)


def _parser_epilog() -> str:
    return (
        "Workflows:\n"
        "  Initial model build:\n"
        "    python ml_training/workbench.py run --force\n"
        "  Review + override loop:\n"
        "    python ml_training/workbench.py review --resume\n"
        "    python ml_training/workbench.py retrain --force\n"
        "  Evaluate latest model:\n"
        "    python ml_training/workbench.py evaluate\n"
    )


def _add_shared_training_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-dir", default=DEFAULT_CASE_DIR)
    parser.add_argument("--prepared-data", default=DEFAULT_PREPARED_DATA)
    parser.add_argument("--seen-data", default=DEFAULT_SEEN_DATA)
    parser.add_argument("--unseen-data", default=DEFAULT_UNSEEN_DATA)
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--total-sample", type=int, default=50000)
    parser.add_argument("--sample-per-file", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--label-column", default="rule_category")
    parser.add_argument("--unseen-ratio", type=float, default=0.2)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--skip-split", action="store_true")
    parser.add_argument("--skip-evaluate", action="store_true")
    parser.add_argument("--cross-validate", action="store_true")
    parser.add_argument("--force", action="store_true")


def _configure_train_parser(subparsers: argparse._SubParsersAction) -> None:
    train_parser = subparsers.add_parser(
        "train",
        help="Prepare/train/validate model",
        description=(
            "Run deterministic training stages. By default this includes "
            "prepare, split, train, and evaluate."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ml_training/workbench.py train --force\n"
            "  python ml_training/workbench.py train --skip-prepare --force\n"
            "  python ml_training/workbench.py train --cross-validate --force"
        ),
    )
    _add_shared_training_arguments(train_parser)


def _configure_evaluate_parser(subparsers: argparse._SubParsersAction) -> None:
    eval_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate model on a CSV",
        description=(
            "Evaluate the current model on a dataset. "
            "If --data is omitted, built-in default paths are used."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ml_training/workbench.py evaluate\n"
            "  python ml_training/workbench.py evaluate --data "
            "ml_training_data/unseen_eval.csv"
        ),
    )
    eval_parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    eval_parser.add_argument(
        "--data",
        default=None,
        help=(
            "Evaluation CSV path "
            "(default: unseen_eval_remaining.csv if present, else unseen_eval.csv)"
        ),
    )


def _configure_review_parser(subparsers: argparse._SubParsersAction) -> None:
    review_parser = subparsers.add_parser(
        "review",
        help="Streamlined interactive correction interface",
        description=(
            "Review model/rule suggestions, apply overrides quickly, "
            "and save decisions to review_labels.csv."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ml_training/workbench.py review --resume\n"
            "  python ml_training/workbench.py review --ui classic\n"
            "  python ml_training/workbench.py review "
            "--focus disagreement --max-cases 300"
        ),
    )
    review_parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    review_parser.add_argument(
        "--data",
        default=None,
        help=(
            "Review CSV path "
            "(default: unseen_eval_remaining.csv if present, else unseen_eval.csv)"
        ),
    )
    review_parser.add_argument(
        "--focus",
        choices=["priority", "disagreement", "low_confidence", "all"],
        default="priority",
    )
    review_parser.add_argument("--low-confidence", type=float, default=0.8)
    review_parser.add_argument("--max-cases", type=int, default=200)
    review_parser.add_argument("--output", default=DEFAULT_REVIEW_OUTPUT)
    review_parser.add_argument("--progress", default=DEFAULT_REVIEW_PROGRESS)
    review_parser.add_argument("--resume", action="store_true")
    review_parser.add_argument(
        "--ui",
        choices=["tui", "classic"],
        default="tui",
        help="Review interface mode (default: tui)",
    )


def _configure_run_parser(subparsers: argparse._SubParsersAction) -> None:
    run_parser = subparsers.add_parser(
        "run",
        help="Train then evaluate using one command",
        description=(
            "One-command pipeline for prepare/split/train/evaluate. "
            "Best starting point for a fresh training cycle."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ml_training/workbench.py run --force\n"
            "  python ml_training/workbench.py run --skip-prepare --force\n"
            "  python ml_training/workbench.py run --cross-validate --force"
        ),
    )
    _add_shared_training_arguments(run_parser)
    run_parser.add_argument(
        "--eval-data",
        default=None,
        help=(
            "Optional evaluation dataset "
            "(if omitted, unseen split is used when available)"
        ),
    )


def _configure_retrain_parser(subparsers: argparse._SubParsersAction) -> None:
    retrain_parser = subparsers.add_parser(
        "retrain",
        help="Retrain using overrides from review labels",
        description=(
            "Merge review overrides into seen data, promote reviewed unseen cases, "
            "retrain model, and optionally evaluate on remaining unseen rows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ml_training/workbench.py retrain --force\n"
            "  python ml_training/workbench.py retrain --skip-evaluate --force\n"
            "  python ml_training/workbench.py retrain --cross-validate --force"
        ),
    )
    retrain_parser.add_argument("--seen-data", default=DEFAULT_SEEN_DATA)
    retrain_parser.add_argument("--unseen-data", default=DEFAULT_UNSEEN_DATA)
    retrain_parser.add_argument("--review-labels", default=DEFAULT_REVIEW_OUTPUT)
    retrain_parser.add_argument(
        "--retrain-data-output",
        default=DEFAULT_RETRAIN_DATA,
        help="Merged retrain dataset output path",
    )
    retrain_parser.add_argument(
        "--eval-data-output",
        default=DEFAULT_REMAINING_EVAL_DATA,
        help="Remaining unseen evaluation dataset output path",
    )
    retrain_parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    retrain_parser.add_argument("--label-column", default="rule_category")
    retrain_parser.add_argument("--cross-validate", action="store_true")
    retrain_parser.add_argument("--skip-evaluate", action="store_true")
    retrain_parser.add_argument("--force", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser.

    Returns:
        Configured ArgumentParser with train, evaluate, review, run, and
        retrain subcommands.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Unified ML workbench with streamlined train/evaluate/review flows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_parser_epilog(),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _configure_train_parser(subparsers)
    _configure_evaluate_parser(subparsers)
    _configure_review_parser(subparsers)
    _configure_run_parser(subparsers)
    _configure_retrain_parser(subparsers)

    return parser


def main() -> int:
    """Main entrypoint.

    Returns:
        0 on success, 1 if an unknown command is dispatched.
    """
    parser = build_parser()

    console.print(
        Panel.fit(
            "[bold cyan]ML Workbench[/bold cyan]\n"
            "One command for training, evaluation, "
            "and streamlined corrections.",
            border_style="cyan",
        )
    )

    if len(sys.argv) == 1:
        _print_cli_overview()
        console.print("\n[bold]Detailed CLI help:[/bold]")
        parser.print_help()
        return 0

    args = parser.parse_args()

    handlers = {
        "train": _train_command,
        "evaluate": _evaluate_command,
        "review": _review_command,
        "run": _run_command_chain,
        "retrain": _retrain_command,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
