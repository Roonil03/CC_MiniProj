# DT-RAM Datasets Directory

This directory stores benchmark workload traces and resource telemetry datasets for training and evaluating DT-RAM forecasting and reinforcement learning models.

## Directory Layout

- `raw/`: Raw external traces (e.g., Alibaba cluster traces, Google cluster trace samples, Azure Functions traces, or custom testbed logs).
  - *Note: Raw datasets are excluded from git tracking via `.gitignore` to prevent repository bloat.*
- `processed/`: Cleaned, resampled, normalized, and partitioned time-series datasets ready for feature engineering and model training.

## Data Ingestion & Preprocessing

When adding new datasets:
1. Place raw traces into `datasets/raw/<dataset_name>/`.
2. Run preprocessing scripts from `services/prediction-service/` or `scripts/`.
3. Save standardized schema outputs into `datasets/processed/`.
