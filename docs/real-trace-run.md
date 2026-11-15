# Real workload forecasting run

The experiment used VM measurements from [Bitbrains fastStorage](https://atlarge-research.com/gwa-t-12/), rather than generated scenarios. The archive is about 128 MB. Its workload variation and longer histories make it a better forecasting input than the earlier short idle capture. It represents hosted VMs, not independent physical edge nodes, application latency, or observed resource-control outcomes.

The source requests acknowledgment of Bitbrains and the Grid Workloads Archive, and citation of Shen, van Beek and Iosup, *Statistical Characterization of Business-Critical Workloads Hosted in Cloud Datacenters*, CCGrid 2015. Keep that attribution in any resulting report.

## Run a new experiment

The project now pins the statistical stack to NumPy 2.1.3, pandas 2.2.3, SciPy 1.14.1, statsmodels 0.14.4 and patsy 1.0.1 in `services/prediction-service/requirements-statistical.txt`, addressing the dependency mismatch observed in bitbrains-01. A completed replacement sweep is still required to assess the full run. Use Docker Desktop with Linux containers and an NVIDIA GPU available to Docker. Put `.env` at the repository root using `.env.example`. Start from the updated `main` branch and choose a new run ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -UseBitbrains -Tune -RunId bitbrains-example -Seeds 42,43 -CheckpointPackage
```

On Linux, the Bash entry point delegates to the same GPU workflow and requires PowerShell 7 (`pwsh`):

```bash
bash scripts/run_dt_models.sh -UseBitbrains -Tune -RunId bitbrains-example -Seeds 42,43 -CheckpointPackage
```

The runner downloads and caches the official archive when needed, imports a bounded five-VM subset, and uses CPU and memory targets at their five-minute cadence. Forecast horizons are 5, 10, 30 and 60 minutes, with 60 historical observations. It prepares the GPU container dependencies, records logs and timestamped events, and packages outputs under `experiments/runs/windows-models/bitbrains-example.zip`. Use the identical command and run ID to resume; changed experiment settings require a new ID. No host Python environment is required for the container workflow.

`-Tune` enables a small fixed candidate search for each model family, with one persistence baseline. Candidate selection uses validation RMSE; test scores are reserved for final evaluation. This is a bounded search, not exhaustive optimization or evidence that every parameter has been optimized. PPO remains a separate synthetic policy experiment and is not trained on these VM observations as though they contained ground-truth actions.

## Recorded result and follow-up

The [bitbrains-01 analysis](analysis/bitbrains-01-partial-2026-11-15.md) records an incomplete run: both seeds exited 2 after ARIMA and ETS failed for both targets. Completed jobs and plots are partial evidence, not a seven-model comparison. The ZIP includes prepared SQLite data and model weights; review its contents before sharing externally. It and the traces remain Git-ignored.

Before a replacement sweep, investigate excluded source rows and verify the statistical dependencies. Use a new run ID for changed settings or software, retain the input manifest and archive, and report any failures. The same VM subset across seeds does not establish independent-trace generalization. PPO is a separate synthetic policy experiment and no PPO results were produced in bitbrains-01. Earlier reports remain in the [evidence index](analysis/README.md).
