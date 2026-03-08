#!/usr/bin/env python3
"""Optimized ML training with advanced techniques for faster, better models."""

from __future__ import annotations

import argparse
import pickle  # noqa: S403
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
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score, train_test_split

try:
    from case_parser.ml.features import FeatureExtractor
    from case_parser.ml.inputs import (
        FeatureInput,
        build_feature_inputs,
        resolve_service_column,
    )
    from case_parser.ml.predictor import ProcedureMLPipeline
    from ml_training.utils import normalize_category_label
except ImportError:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from case_parser.ml.features import FeatureExtractor
    from case_parser.ml.inputs import (
        FeatureInput,
        build_feature_inputs,
        resolve_service_column,
    )
    from case_parser.ml.predictor import ProcedureMLPipeline
    from ml_training.utils import normalize_category_label

console = Console()


@dataclass
class TrainArtifacts:
    """Container for trained model components and metadata."""

    model: Any
    feature_extractor: FeatureExtractor
    best_score: float
    best_name: str


@dataclass(frozen=True)
class ArtifactMetadataInput:
    """Inputs needed to build persisted model metadata."""

    label_column: str
    service_column: str | None
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
        "--service-column",
        help="Optional service column to include in ML features",
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
    df: pd.DataFrame,
    label_column: str,
    service_column: str | None,
) -> tuple[list[FeatureInput], np.ndarray[Any, Any], str | None]:
    """
    Build feature inputs and label array from a dataframe, resolving an optional service column.
    
    Parameters:
        df (pd.DataFrame): Input dataframe containing at least a "procedure" column and the label column.
        label_column (str): Name of the column to use as target labels; missing values are replaced with "Other (procedure cat)" and normalized.
        service_column (str | None): Optional user-requested column name for service data; if provided, the function attempts to resolve it in the dataframe.
    
    Returns:
        tuple[list[FeatureInput], np.ndarray[Any, Any], str | None]:
            - features: List of FeatureInput objects built from procedures and corresponding services.
            - labels: 1-D numpy array of normalized label strings.
            - resolved_service_column: The actual service column name found in df, or `None` if no service column is used.
    
    Raises:
        ValueError: If `service_column` is provided but cannot be resolved in `df`.
    """
    resolved_service_column = resolve_service_column(df, service_column)
    if service_column is not None and resolved_service_column is None:
        raise ValueError(f"Service column not found: {service_column}")
    procedures = df["procedure"].fillna("").astype(str).tolist()
    if resolved_service_column is not None:
        services = df[resolved_service_column].fillna("").astype(str).tolist()
    else:
        services = ["" for _ in procedures]
    features = build_feature_inputs(procedures, services_list=services)
    labels = (
        df[label_column]
        .fillna("Other (procedure cat)")
        .astype(str)
        .map(normalize_category_label)
        .to_numpy()
    )
    return features, labels, resolved_service_column


def _print_class_distribution(
    labels: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], pd.Series[Any]]:
    """
    Print a table showing each label's count and percentage, and return the labels and their counts.
    
    Parameters:
        labels (np.ndarray[Any, Any]): Array of label values for the dataset.
    
    Returns:
        unique_labels (np.ndarray[Any, Any]): Sorted unique label values present in `labels`.
        class_counts (pd.Series[Any]): Series mapping each label to its occurrence count.
    """
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
    x_train: list[FeatureInput], x_val: list[FeatureInput]
) -> tuple[FeatureExtractor, Any, Any]:
    """
    Builds a FeatureExtractor, fits it on the training feature inputs, and returns transformed feature matrices for training and validation.
    
    Parameters:
        x_train (list[FeatureInput]): FeatureInput list for training samples used to fit and transform the extractor.
        x_val (list[FeatureInput]): FeatureInput list for validation samples to be transformed with the fitted extractor.
    
    Returns:
        tuple[FeatureExtractor, Any, Any]: A tuple containing:
            - feature_extractor: the fitted FeatureExtractor instance.
            - x_train_features: the feature matrix produced from `x_train`.
            - x_val_features: the feature matrix produced from `x_val`.
    """
    feature_extractor = FeatureExtractor()
    with Progress(console=console) as progress:
        task = progress.add_task("Extracting features...", total=1)
        x_train_features = feature_extractor.fit_transform(x_train)
        x_val_features = feature_extractor.transform(x_val)
        progress.advance(task)

    console.print(f"[cyan]Feature matrix shape: {x_train_features.shape}[/cyan]")
    return feature_extractor, x_train_features, x_val_features


def _train_single_model(
    model: Any,
    x_train_features: Any,
    y_train: np.ndarray[Any, Any],
    x_val_features: Any,
    y_val: np.ndarray[Any, Any],
) -> tuple[Any, float]:
    model.fit(x_train_features, y_train)
    score = float(model.score(x_val_features, y_val))
    return model, score


def _build_model_candidates() -> dict[str, Any]:
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


def _print_model_comparison(models: dict[str, tuple[Any, float]]) -> None:
    table = Table(title="Model Comparison", border_style="cyan")
    table.add_column("Model", style="cyan")
    table.add_column("Validation Accuracy", justify="right")

    for name, (_model, score) in models.items():
        table.add_row(name, f"{score:.4f}")

    console.print(table)


def train_ensemble_model(
    x_train: list[FeatureInput],
    y_train: np.ndarray[Any, Any],
    x_val: list[FeatureInput],
    y_val: np.ndarray[Any, Any],
) -> TrainArtifacts:
    """
    Train multiple candidate classifiers (logistic regression, random forest, and a voting ensemble) on the provided feature inputs and select the best performer by validation accuracy.
    
    Parameters:
        x_train (list[FeatureInput]): Feature inputs for training.
        y_train (np.ndarray): Labels for the training set.
        x_val (list[FeatureInput]): Feature inputs for validation.
        y_val (np.ndarray): Labels for the validation set.
    
    Returns:
        TrainArtifacts: Container with the selected best model, the fitted FeatureExtractor, the best validation accuracy (`best_score`), and the model name (`best_name`).
    """
    feature_extractor, x_train_features, x_val_features = _extract_feature_matrices(
        x_train,
        x_val,
    )

    trained_models: dict[str, tuple[Any, float]] = {}
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
            n_jobs=1,
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
    all_features: list[FeatureInput],
    labels: np.ndarray[Any, Any],
    class_counts: pd.Series[Any],
    enabled: bool,
) -> None:
    """
    Run an optional 5-fold cross-validation on the trained model and print the fold scores.
    
    Parameters:
        artifacts (TrainArtifacts): Trained artifacts containing the model and its feature_extractor.
        all_features (list[FeatureInput]): Full dataset feature inputs to be transformed for cross-validation.
        labels (np.ndarray): Label array corresponding to all_features.
        class_counts (pd.Series): Series of per-class counts used to determine whether cross-validation is allowed.
        enabled (bool): If False, cross-validation is skipped immediately.
    
    Description:
        If enabled is True and every class has at least five examples, transforms all_features using
        the artifacts' feature_extractor, runs 5-fold cross-validation with the trained model, and
        prints the individual fold scores and mean ± 2*std. If the smallest class has fewer than
        five examples, prints a warning and skips cross-validation.
    """
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
    """
    Persist the trained pipeline and associated metadata to disk as a pickle file.
    
    Parameters:
        output_path (Path): Filesystem path where the serialized artifact will be written. Parent directories will be created if needed.
        artifacts (TrainArtifacts): Container holding the trained model, the feature extractor, the best validation score, and the model name.
        metadata_input (ArtifactMetadataInput): Inputs used to build persisted metadata (label/service column names, label array, and train/validation sample counts).
    
    The function writes a pickle containing a dictionary with:
        - "pipeline": a ProcedureMLPipeline built from `artifacts.model` and `artifacts.feature_extractor`.
        - "metadata": a mapping with keys:
            - training_date: ISO-formatted timestamp of save time
            - training_samples: number of training samples
            - validation_samples: number of validation samples
            - validation_accuracy: best validation score (float)
            - model_type: chosen model name
            - label_column: name of the label column used
            - service_column: resolved service column name or `None`
            - feature_version: feature extractor version (falls back to 1 if missing)
            - uses_services: `True` if a service column was provided, `False` otherwise
            - categories: sorted list of observed category labels
    """
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
        "service_column": metadata_input.service_column,
        "feature_version": getattr(artifacts.feature_extractor, "feature_version", 1),
        "uses_services": metadata_input.service_column is not None,
        "categories": sorted(set(metadata_input.labels.tolist())),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        pickle.dump({"pipeline": pipeline, "metadata": metadata}, fh)
    console.print(f"\n[green]Model saved to {output_path}[/green]")


def main() -> int:
    """
    Orchestrates the CLI workflow to train an optimized procedure classification model, evaluate it, optionally run cross-validation, and persist the trained pipeline with metadata.
    
    This function parses command-line arguments, loads and validates the input CSV, extracts features and labels (respecting an optional service column), splits data into training and validation sets, trains and selects the best model via an ensemble workflow, reports validation metrics, optionally performs 5-fold cross-validation, and saves the serialized pipeline and metadata to the specified output path.
    
    Returns:
        0 on success, 1 if required columns are missing from the input dataset or if an explicitly requested service column is unavailable.
    """
    args = build_parser().parse_args()

    _print_header(args.input, args.output)
    df = _load_dataset(args.input)

    if not _validate_required_columns(df, args.label_column):
        return 1

    try:
        x, y, resolved_service_column = _extract_training_arrays(
            df,
            args.label_column,
            args.service_column,
        )
    except ValueError as exception:
        console.print(f"[red]{exception}[/red]")
        return 1
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
            service_column=resolved_service_column,
            labels=y,
            train_samples=len(x_train),
            validation_samples=len(x_val),
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
