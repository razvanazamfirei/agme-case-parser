# ML Training Workbench

Current ML workflow for procedure categorization.

Get interactive command overview and full CLI help:

```bash
python ml_training/workbench.py
```

## Install dependencies

```bash
uv sync --group ml
```

## One-command pipeline (recommended)

```bash
python ml_training/workbench.py run --total-sample 50000 --force
```

What this does:
- prepares data (unless `--skip-prepare`)
- splits into seen/unseen sets
- trains on seen split
- evaluates on unseen split

Default outputs:
- `ml_training_data/batch_prepared.csv`
- `ml_training_data/seen_train.csv`
- `ml_training_data/unseen_eval.csv`
- `ml_models/procedure_classifier.pkl`

## Review corrections

TUI mode (default):

```bash
python ml_training/workbench.py review --resume
```

Built-in review data path:
- `ml_training_data/unseen_eval_remaining.csv` (if it exists)
- otherwise `ml_training_data/unseen_eval.csv`

Classic prompt mode:

```bash
python ml_training/workbench.py review \
  --data ml_training_data/unseen_eval.csv \
  --ui classic
```

## Retrain with your overrides

After reviewing cases and writing `ml_training_data/review_labels.csv`, run:

```bash
python ml_training/workbench.py retrain --force
```

What this does:
- loads your overrides from `review_labels.csv`
- relabels matching rows in `seen_train.csv`
- promotes reviewed rows from `unseen_eval.csv` into retraining data
- upweights true correction overrides by a built-in `3x` multiplier
- writes:
  - `ml_training_data/seen_train_with_overrides.csv`
  - `ml_training_data/unseen_eval_remaining.csv`
- retrains the model and evaluates on the remaining unseen rows

## Common commands

Train only:

```bash
python ml_training/workbench.py train --force
```

Evaluate any CSV:

```bash
python ml_training/workbench.py evaluate \
  --model ml_models/procedure_classifier.pkl \
  --data ml_training_data/unseen_eval.csv
```

Or use built-in default eval path:

```bash
python ml_training/workbench.py evaluate
```

## Lower-level scripts (still supported)

- `ml_training/auto_train.py`: deterministic prepare/split/train/evaluate pipeline
- `ml_training/batch_prepare.py`: parallel data preparation + sampling
- `ml_training/train_optimized.py`: model training entrypoint
- `ml_training/evaluate.py`: batch evaluation entrypoint
