# Synthetic terminal demo

The demo runs a small, deterministic synthetic DT-RAM scenario in the terminal. It needs Python and does not require Docker, Kubernetes, credentials, or extra Python packages. It makes no infrastructure requests: recommendations and safety outcomes are shown in shadow mode, and physical actuation is disabled.

Run it from the repository root:

```bash
bash scripts/demo.sh
bash scripts/demo.sh --seed 42
```

On PowerShell:

```powershell
./scripts/demo.ps1
./scripts/demo.ps1 --seed 42
```

Both launchers locate `scripts/demo.py` relative to themselves, so they also work when called from another current directory. They forward all arguments to the Python script. The Bash launcher looks for `python3` and then `python`; the PowerShell launcher looks for the Python `py` launcher and then `python`. Set `PYTHON` to an executable path to select a specific interpreter, including paths containing spaces.

The optional `--seed` argument selects the synthetic scenario seed. Use `--no-color` for plain terminal output or `--json` for machine-readable output.

## Reading the demo

The displayed metrics describe the synthetic workload and candidate outcomes; they are not measurements from a live cluster. CPU and memory show current or simulated utilization. `P95` is the simulator's latency estimate, `SLO P` is its estimated probability of an SLO violation, and `MIG COST` summarizes migration overhead; migration duration is shown for approved migration candidates. These estimates compare scenarios and are not production measurements.

The candidates include keeping the current placement (`NOOP`), scaling, and migrating to a healthy or stale node. Each is simulated against the Digital Twin and then checked by the safety gate. `APPROVED` and `DENIED` are illustrative gate verdicts; a denied candidate includes the gate's reasons. Even an approved candidate is shadow-only: it records what could be done but does not change workloads or Kubernetes resources.
