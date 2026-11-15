# Bitbrains-01: partial forecasting run — 2026-11-15

**Status: incomplete.** Both forecast sweeps exited 2. The results below describe only completed jobs; they do not establish a winner across the requested seven-model sweep. The comparison plots omit failed jobs and cannot make the sweep complete.

## Provenance and scope

The input is the GWA-T-12 Bitbrains fastStorage VM trace. Acknowledge Bitbrains and the Grid Workloads Archive and cite Shen, van Beek and Iosup, *Statistical Characterization of Business-Critical Workloads Hosted in Cloud Datacenters*, CCGrid 2015. It is recorded hosted-VM telemetry, not physical edge-node or application-SLO data. The input archive SHA-256 is `11313f528a0cbcbe57e63162f8ae5a41a9c7e7c1a79872e294ff3c5bbaa2e671`. The local ignored output ZIP SHA-256 is `b09d186c69f8ffacd60706c623bdec2aee449d86d942c36d0cfe4d2e492c9add`. Its manifest reports `incomplete`; the 114 entries were checked against the output directory and CRCs. The raw archive and results are not stored in Git.

The input manifest names five VMs (`bitbrains-1`, `bitbrains-10`, `bitbrains-100`, `bitbrains-1000`, `bitbrains-1001`), with 29,281 rows imported and 33,028 skipped, zero duplicates, and 6/1/0/0/0 missing cadence buckets respectively. An independent check of the five CSV files found 62,309 rows: 33,026 excluded for nonpositive memory capacity and two conflicting same-VM timestamps (VMs 10 and 100). This substantial exclusion can bias the retained sample and requires investigation before generalizing. CPU is a fraction of provisioned CPU and memory is active/provisioned KB. The reported span is 2013-08-12T13:40:46Z to 2013-09-11T13:39:58Z. The `stable` folder name is a legacy runner label, not a verified stable workload scenario. Seeds 42 and 43 use the same VM subset, not independent traces.

The run used 300-second cadence, 60 history steps, 300/600/1800/3600-second horizons, CPU and memory targets, 20 requested epochs and bounded tuning. The outer configuration records Git commit `3f709d8d9b6d5742cf20cd2d4f294fdffbc68494`; model records say Git commit unavailable and working tree dirty. They record Python 3.11.18, PyTorch 2.6.0+cu126 and statsmodels 0.14.4. The runner log records pandas 3.1.1 already installed immediately before statsmodels installation. This limits exact source reproducibility. Selection is within each model family by mean validation RMSE over 64 sampled validation windows; it is not a final cross-family deployment selection. Completed neural selections used hidden width 16 or 32 and learning rate 0.001.

## Outcomes

Each seed completed persistence, LSTM, GRU, temporal and Transformer for both CPU and memory (10 of 14 jobs). ARIMA and ETS failed for both targets, each after four recorded attempts, with `TypeError: deprecate_kwarg() missing 1 required positional argument: 'new_arg_name'` during statsmodels import. The traceback indicates a dependency API compatibility failure involving the installed statistical stack; no repaired dependency combination was verified by this run. A separate, untuned seed-42 CPU persistence calibration job completed in 7.3257 seconds; it does not complete the failed statistical jobs. No PPO policy was requested (`policies` is empty), so this run contains no PPO evaluation or control outcome.

The completed results record 18,226 training windows, 5,097 validation windows and 64 sampled test windows per horizon. Calibration records 105 observations and a separate confidence audit 108 per horizon for the inspected persistence result. Training includes five VMs, but validation and test windows contain only VMs 1, 1000 and 1001. The 64 test windows comprise 17, 16 and 31 respectively. These are not independent VM deployments; limited coverage and the large input exclusion constrain inference. The following test MAE values are utilization fractions, rounded to five decimal places. They are per seed and target, ordered by horizon in seconds; they are descriptive, not a full-sweep ranking.

| Seed | Target | Completed model | 300 | 600 | 1800 | 3600 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 42 | cpu | persistence | 0.01442 | 0.01675 | 0.00247 | 0.00299 |
| 42 | cpu | lstm | 0.00843 | 0.00869 | 0.01151 | 0.01894 |
| 42 | cpu | gru | 0.01068 | 0.01038 | 0.01719 | 0.02490 |
| 42 | cpu | temporal | 0.01110 | 0.01856 | 0.02063 | 0.02334 |
| 42 | cpu | transformer | 0.00698 | 0.00658 | 0.01063 | 0.01482 |
| 42 | memory | persistence | 0.03287 | 0.05498 | 0.01688 | 0.02135 |
| 42 | memory | lstm | 0.01458 | 0.01684 | 0.01444 | 0.01697 |
| 42 | memory | gru | 0.01466 | 0.01610 | 0.01302 | 0.01643 |
| 42 | memory | temporal | 0.01421 | 0.01636 | 0.01309 | 0.01495 |
| 42 | memory | transformer | 0.01076 | 0.01450 | 0.01058 | 0.01606 |
| 43 | cpu | persistence | 0.01442 | 0.01675 | 0.00247 | 0.00299 |
| 43 | cpu | lstm | 0.00786 | 0.00852 | 0.01190 | 0.01844 |
| 43 | cpu | gru | 0.01140 | 0.00916 | 0.01011 | 0.01408 |
| 43 | cpu | temporal | 0.01260 | 0.01431 | 0.01773 | 0.01832 |
| 43 | cpu | transformer | 0.00222 | 0.00473 | 0.01242 | 0.01755 |
| 43 | memory | persistence | 0.03287 | 0.05498 | 0.01688 | 0.02135 |
| 43 | memory | lstm | 0.01514 | 0.01804 | 0.01347 | 0.01713 |
| 43 | memory | gru | 0.01236 | 0.01657 | 0.01360 | 0.01715 |
| 43 | memory | temporal | 0.01297 | 0.01612 | 0.01257 | 0.01589 |
| 43 | memory | transformer | 0.01180 | 0.01444 | 0.01225 | 0.01704 |

For example, seed 42 CPU persistence has test MAE 0.01442 at five minutes and 0.00247 at 30 minutes; the Transformer has 0.00698 and 0.01063 respectively. Differences depend on horizon and target. The 64 sampled windows are not sufficient on their own to establish generalization, especially across different nodes, periods or workloads. Persistence CPU test RMSE at 30 and 60 minutes was 0.006942 and 0.009863 in both seeds, lower than the completed neural jobs at those horizons; ARIMA and ETS are absent. For LSTM CPU at five minutes, nominal 90% intervals covered 65.625% and 67.188% of the sampled test windows in seeds 42 and 43. These examples do not establish interval guarantees. Test MAE is not a measured SLA improvement. Validation choices, interval coverage, resource usage, detailed metrics and plots remain in each job's JSON and the archive; there is no valid result for failed jobs.

## Per-horizon RMSE and selected configuration

Test RMSE is a utilization fraction; each entry uses 64 sampled test windows. Missing ARIMA and ETS rows indicate failure, not zero error.

| Seed | Target | Model | 300 s | 600 s | 1800 s | 3600 s | Selected hidden width | Job seconds |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 42 | cpu | persistence | 0.04584 | 0.05149 | 0.00694 | 0.00986 | — | 1.32 |
| 42 | cpu | lstm | 0.01879 | 0.01904 | 0.03659 | 0.05832 | 32 | 39.40 |
| 42 | cpu | gru | 0.02956 | 0.03547 | 0.07014 | 0.09484 | 32 | 40.14 |
| 42 | cpu | temporal | 0.04676 | 0.07478 | 0.09475 | 0.10638 | 16 | 40.91 |
| 42 | cpu | transformer | 0.02393 | 0.02448 | 0.04353 | 0.06601 | 32 | 61.41 |
| 42 | memory | persistence | 0.07379 | 0.10786 | 0.04073 | 0.04842 | — | 1.20 |
| 42 | memory | lstm | 0.02840 | 0.04018 | 0.02502 | 0.03475 | 32 | 27.94 |
| 42 | memory | gru | 0.02485 | 0.04197 | 0.02068 | 0.03162 | 32 | 25.83 |
| 42 | memory | temporal | 0.02413 | 0.04236 | 0.02077 | 0.02930 | 32 | 34.28 |
| 42 | memory | transformer | 0.01465 | 0.03623 | 0.01675 | 0.03026 | 32 | 69.44 |
| 43 | cpu | persistence | 0.04584 | 0.05149 | 0.00694 | 0.00986 | — | 1.17 |
| 43 | cpu | lstm | 0.01401 | 0.01504 | 0.03010 | 0.05668 | 32 | 35.08 |
| 43 | cpu | gru | 0.01745 | 0.01690 | 0.02442 | 0.04376 | 32 | 32.74 |
| 43 | cpu | temporal | 0.03636 | 0.04908 | 0.05608 | 0.05324 | 16 | 16.42 |
| 43 | cpu | transformer | 0.00418 | 0.01041 | 0.03231 | 0.05314 | 32 | 35.75 |
| 43 | memory | persistence | 0.07379 | 0.10786 | 0.04073 | 0.04842 | — | 1.18 |
| 43 | memory | lstm | 0.02639 | 0.04530 | 0.02169 | 0.03033 | 32 | 23.18 |
| 43 | memory | gru | 0.02209 | 0.04116 | 0.02375 | 0.03469 | 16 | 23.46 |
| 43 | memory | temporal | 0.02247 | 0.04306 | 0.02083 | 0.02973 | 16 | 21.55 |
| 43 | memory | transformer | 0.01753 | 0.03731 | 0.01935 | 0.03036 | 32 | 39.98 |

The measured job durations cover each successful job's recorded run, including its bounded candidate search and evaluation; they are not a controlled hardware benchmark. The GPU preflight identified an NVIDIA GeForce RTX 3060 Laptop GPU and the neural result records CUDA. The system snapshot reports Linux WSL2, 16 logical CPUs and Python 3.11.18. Direct per-model inference latency, model sizes and calibration intervals are in the individual result JSON; compare only with matching hardware and workloads. No network-serving latency or production load test was measured here.

## Next steps

Investigate excluded rows and validate their distributions, repair and verify the statistical dependency stack, then repeat the complete sweep with preserved input provenance and a new run ID. Report all failures and selection criteria, check sample coverage by VM and time, and evaluate on additional independent traces before proposing a serving model. Do not merge these partial metrics into the synthetic trial or present a live-cluster, migration, PPO or SLA result from them.
