#!/usr/bin/env python3
"""Optimized ML training with advanced techniques for faster, better models."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table
from sklearn.base import ClassifierMixin
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score, train_test_split

from case_parser.ml.features import FeatureExtractor
from case_parser.ml.predictor import ProcedureMLPipeline

try:
    from ml_training.utils import normalize_category_label
except ModuleNotFoundError:
    from utils import normalize_category_label

console = Console()


@dataclass
class TrainArtifacts:
    """Container for trained model components and metadata."""

    model: ClassifierMixin
    feature_extractor: FeatureExtractor
    best_score: float
    best_name: str


@dataclass(frozen=True)
class ArtifactMetadataInput:
    """Inputs needed to build persisted model metadata."""

    label_column: str
    labels: np.ndarray[Any, Any]
    train_samples: int
    validation_samples: int


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for optimized trainer.

    Returns:
        Configured ArgumentParser for the optimized training tool.
    """
    parser = argparse.ArgumentParser(
        description="Train optimized ML model for procedure categorization"
    )
    parser.add_argument("input", type=Path, help="Input CSV with labeled cases")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml_models/procedure_classifier.pkl"),
        help="Output model file (default: ml_models/procedure_classifier.pkl)",
    )
    parser.add_argument(
        "--label-column",
        default="category",
        help="Name of the label column (default: category)",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.2,
        help="Validation split ratio (default: 0.2)",
    )
    parser.add_argument(
        "--cross-validate",
        action="store_true",
        help="Perform cross-validation",
    )
    return parser


def _print_header(input_path: Path, output_path: Path) -> None:
    console.print(
        Panel.fit(
            "[cyan]Optimized ML Training[/cyan]\n"
            f"Input: {input_path}\n"
            f"Output: {output_path}",
            border_style="cyan",
        )
    )


def _load_dataset(input_path: Path) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    console.print(f"\nLoaded {len(df)} cases")
    return df


def _validate_required_columns(df: pd.DataFrame, label_column: str) -> bool:
    missing_columns: list[str] = []
    if "procedure" not in df.columns:
        missing_columns.append("procedure")
    if label_column not in df.columns:
        missing_columns.append(label_column)

    if not missing_columns:
        return True

    console.print(
        f"[red]Missing required column(s):[/red] {', '.join(missing_columns)}"
    )
    console.print(f"Available columns: {', '.join(df.columns)}")
    return False


def _extract_training_arrays(
    df: pd.DataFrame, label_column: str
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    features = df["procedure"].fillna("").astype(str).to_numpy()
    labels = (
        df[label_column]
        .fillna("Other (procedure cat)")
        .astype(str)
        .map(normalize_category_label)
        .to_numpy()
    )
    return features, labels


def _print_class_distribution(
    labels: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], pd.Series[Any]]:
    unique_labels, counts = np.unique(labels, return_counts=True)

    dist_table = Table(title="Class Distribution", border_style="yellow")
    dist_table.add_column("Category", style="yellow")
    dist_table.add_column("Count", justify="right")
    dist_table.add_column("Percentage", justify="right")

    for category, count in zip(unique_labels, counts, strict=False):
        percentage = (count / len(labels)) * 100
        dist_table.add_row(str(category), str(count), f"{percentage:.1f}%")

    console.print(dist_table)
    class_counts = pd.Series(labels).value_counts()
    return unique_labels, class_counts


def _resolve_stratify_labels(
    labels: np.ndarray[Any, Any], class_counts: pd.Series[Any]
) -> np.ndarray[Any, Any] | None:
    rare_classes = class_counts[class_counts < 2]
    if rare_classes.empty:
        return labels

    rare_names = ", ".join(rare_classes.index.tolist())
    console.print(
        "[yellow]Warning:[/yellow] Disabling stratified split because "
        f"{len(rare_classes)} class(es) have <2 samples: {rare_names}"
    )
    return None


def _extract_feature_matrices(
    x_train: np.ndarray[Any, Any], x_val: np.ndarray[Any, Any]
) -> tuple[FeatureExtractor, Any, Any]:
    feature_extractor = FeatureExtractor()
    with Progress(console=console) as progress:
        task = progress.add_task("Extracting features...", total=1)
        x_train_features = feature_extractor.fit_transform(x_train)
        x_val_features = feature_extractor.transform(x_val)
        progress.advance(task)

    console.print(f"[cyan]Feature matrix shape: {x_train_features.shape}[/cyan]")
    return feature_extractor, x_train_features, x_val_features


def _train_single_model(
    model: ClassifierMixin,
    x_train_features: Any,
    y_train: np.ndarray[Any, Any],
    x_val_features: Any,
    y_val: np.ndarray[Any, Any],
) -> tuple[ClassifierMixin, float]:
    model.fit(x_train_features, y_train)
    score = float(model.score(x_val_features, y_val))
    return model, score


def _build_model_candidates() -> dict[str, ClassifierMixin]:
    return {
        "Logistic Regression": LogisticRegression(
            max_iter=2000,
            random_state=42,
            solver="lbfgs",
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1,
        ),
    }


def _print_model_comparison(models: dict[str, tuple[ClassifierMixin, float]]) -> None:
    table = Table(title="Model Comparison", border_style="cyan")
    table.add_column("Model", style="cyan")
    table.add_column("Validation Accuracy", justify="right")

    for name, (_model, score) in models.items():
        table.add_row(name, f"{score:.4f}")

    console.print(table)


def train_ensemble_model(
    x_train: np.ndarray[Any, Any],
    y_train: np.ndarray[Any, Any],
    x_val: np.ndarray[Any, Any],
    y_val: np.ndarray[Any, Any],
) -> TrainArtifacts:
    """Train candidate models and return the best performer.

    Args:
        x_train: Training feature matrix.
        y_train: Training labels corresponding to ``x_train``.
        x_val: Validation feature matrix.
        y_val: Validation labels corresponding to ``x_val``.
    Returns:
        TrainArtifacts containing the best model, feature extractor, score, and name.
    """
    feature_extractor, x_train_features, x_val_features = _extract_feature_matrices(
        x_train,
        x_val,
    )

    trained_models: dict[str, tuple[ClassifierMixin, float]] = {}
    base_models = _build_model_candidates()

    with Progress(console=console) as progress:
        for name, candidate in base_models.items():
            task = progress.add_task(f"Training {name}...", total=1)
            trained_models[name] = _train_single_model(
                candidate,
                x_train_features,
                y_train,
                x_val_features,
                y_val,
            )
            progress.advance(task)

        task = progress.add_task("Training Ensemble...", total=1)
        ensemble = VotingClassifier(
            estimators=[
                ("lr", trained_models["Logistic Regression"][0]),
                ("rf", trained_models["Random Forest"][0]),
            ],
            voting="soft",
            n_jobs=-1,
        )
        trained_models["Ensemble"] = _train_single_model(
            ensemble,
            x_train_features,
            y_train,
            x_val_features,
            y_val,
        )
        progress.advance(task)

    _print_model_comparison(trained_models)
    best_name, (best_model, best_score) = max(
        trained_models.items(), key=lambda item: item[1][1]
    )
    console.print(f"\n[green]Best model: {best_name} ({best_score:.4f})[/green]")

    return TrainArtifacts(
        model=best_model,
        feature_extractor=feature_extractor,
        best_score=best_score,
        best_name=best_name,
    )


def _print_validation_metrics(
    y_val: np.ndarray[Any, Any],
    y_pred: np.ndarray[Any, Any],
    ordered_labels: np.ndarray[Any, Any],
) -> None:
    console.print("\n[cyan]Validation Performance:[/cyan]")
    console.print(classification_report(y_val, y_pred, zero_division=0))

    confusion = confusion_matrix(y_val, y_pred)
    display_labels = ordered_labels[:5]

    table = Table(title="Confusion Matrix (Top 5)", border_style="yellow")
    table.add_column("True \\ Predicted")
    for label in display_labels:
        table.add_column(str(label)[:20], justify="right")

    for row_idx, true_label in enumerate(display_labels):
        if row_idx >= len(confusion):
            break
        row = [str(true_label)[:20]]
        row.extend(
            str(confusion[row_idx][col_idx])
            if col_idx < len(confusion[row_idx])
            else ""
            for col_idx in range(len(display_labels))
        )
        table.add_row(*row)

    console.print(table)


def _maybe_run_cross_validation(
    artifacts: TrainArtifacts,
    all_features: np.ndarray[Any, Any],
    labels: np.ndarray[Any, Any],
    class_counts: pd.Series[Any],
    enabled: bool,
) -> None:
    if not enabled:
        return

    min_class_count = int(class_counts.min())
    if min_class_count < 5:
        console.print(
            "[yellow]Skipping 5-fold CV:[/yellow] "
            f"minimum class count is {min_class_count} (<5)"
        )
        return

    console.print("\n[cyan]Performing 5-fold cross-validation...[/cyan]")
    transformed = artifacts.feature_extractor.transform(all_features)
    scores = cross_val_score(artifacts.model, transformed, labels, cv=5, n_jobs=-1)
    console.print(
        f"CV Scores: {scores}\nMean: {scores.mean():.4f} (+/- {scores.std() * 2:.4f})"
    )


def _save_model_artifact(
    output_path: Path,
    artifacts: TrainArtifacts,
    metadata_input: ArtifactMetadataInput,
) -> None:
    pipeline = ProcedureMLPipeline(
        model=artifacts.model,
        features=artifacts.feature_extractor,
    )
    metadata = {
        "training_date": pd.Timestamp.now().isoformat(),
        "training_samples": metadata_input.train_samples,
        "validation_samples": metadata_input.validation_samples,
        "validation_accuracy": float(artifacts.best_score),
        "model_type": artifacts.best_name,
        "label_column": metadata_input.label_column,
        "categories": sorted(set(metadata_input.labels.tolist())),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle({"pipeline": pipeline, "metadata": metadata}, output_path)
    console.print(f"\n[green]Model saved to {output_path}[/green]")


def main() -> int:
    """Train optimized ML model.

    Returns:
        0 on success, 1 if required columns are missing from the input dataset.
    """
    args = build_parser().parse_args()

    _print_header(args.input, args.output)
    df = _load_dataset(args.input)

    if not _validate_required_columns(df, args.label_column):
        return 1

    x, y = _extract_training_arrays(df, args.label_column)
    unique_labels, class_counts = _print_class_distribution(y)
    stratify_labels = _resolve_stratify_labels(y, class_counts)

    x_train, x_val, y_train, y_val = train_test_split(
        x,
        y,
        test_size=args.val_split,
        random_state=42,
        stratify=stratify_labels,
    )
    console.print(f"\n[cyan]Train: {len(x_train)}, Validation: {len(x_val)}[/cyan]")

    artifacts = train_ensemble_model(x_train, y_train, x_val, y_val)
    x_val_features = artifacts.feature_extractor.transform(x_val)
    y_pred = artifacts.model.predict(x_val_features)
    _print_validation_metrics(y_val, y_pred, unique_labels)

    _maybe_run_cross_validation(
        artifacts=artifacts,
        all_features=x,
        labels=y,
        class_counts=class_counts,
        enabled=args.cross_validate,
    )

    _save_model_artifact(
        output_path=args.output,
        artifacts=artifacts,
        metadata_input=ArtifactMetadataInput(
            label_column=args.label_column,
            labels=y,
            train_samples=len(x_train),
            validation_samples=len(x_val),
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
