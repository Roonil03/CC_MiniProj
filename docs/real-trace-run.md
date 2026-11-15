# Real workload forecasting run

The next experiment uses recorded VM measurements from [Bitbrains fastStorage](https://atlarge-research.com/gwa-t-12/), rather than generated scenarios. The archive is about 128 MB. Its workload variation and longer histories make it a better forecasting input than the earlier short idle capture. It represents hosted VMs, not independent physical edge nodes, application latency, or observed resource-control outcomes.

The source requests acknowledgment of Bitbrains and the Grid Workloads Archive, and citation of Shen, van Beek and Iosup, *Statistical Characterization of Business-Critical Workloads Hosted in Cloud Datacenters*, CCGrid 2015. Keep that attribution in any resulting report.

## Run after implementation PRs are merged

Use Docker Desktop with Linux containers and an NVIDIA GPU available to Docker. Put `.env` at the repository root using `.env.example`. Start from the updated `main` branch and choose a new run ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -UseBitbrains -Tune -RunId bitbrains-01 -Seeds 42,43 -CheckpointPackage
```

On Linux, the Bash entry point delegates to the same GPU workflow and requires PowerShell 7 (`pwsh`):

```bash
bash scripts/run_dt_models.sh -UseBitbrains -Tune -RunId bitbrains-01 -Seeds 42,43 -CheckpointPackage
```

The runner downloads and caches the official archive when needed, imports a bounded five-VM subset, and uses CPU and memory targets at their five-minute cadence. Forecast horizons are 5, 10, 30 and 60 minutes, with 60 historical observations. It prepares the GPU container dependencies, records logs and timestamped events, and packages outputs under `experiments/runs/windows-models/bitbrains-01.zip`. Use the identical command and run ID to resume; changed experiment settings require a new ID. No host Python environment is required for the container workflow.

`-Tune` enables a small fixed candidate search for each model family, with one persistence baseline. Candidate selection uses validation RMSE; test scores are reserved for final evaluation. This is a bounded search, not exhaustive optimization or evidence that every parameter has been optimized. PPO remains a separate synthetic policy experiment and is not trained on these VM observations as though they contained ground-truth actions.

## What to send for analysis

Send the completed ZIP and retain its matching input manifest. The archive contains prepared inputs, results, logs, plots and configuration needed for review. Inspect output filenames before sharing externally; run archives stay Git-ignored. A failed or interrupted archive is partial evidence and should be identified as such.

No real-trace model sweep was run during implementation. Runtime estimates are heuristics and must be checked against actual timings. The next report will compare per-model, per-target, per-horizon and per-seed results, tuning choices, resource use, calibration support and failures. Earlier reports will retain their provenance; superseded summaries can be archived and linked when the new results exist. The documentation PR remains open until that analysis is complete.
