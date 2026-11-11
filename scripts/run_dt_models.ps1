# Offline, simulation-only Windows model runner. Compatible with Windows PowerShell 5.1 and PowerShell 7.
param(
    [string]$OutputRoot = "experiments/runs/windows-models",
    [string]$RunId = "",
    [ValidateSet("persistence", "arima", "ets", "lstm", "gru", "temporal", "transformer")]
    [string[]]$Models = @("persistence", "arima", "ets", "lstm", "gru", "temporal", "transformer"),
    [ValidateSet("cpu", "memory", "network_in", "network_out")]
    [string[]]$Metrics = @("cpu"),
    [ValidateSet("stable", "burst", "memory-pressure")]
    [string[]]$Scenarios = @("stable"),
    [int[]]$Seeds = @(42),
    [ValidateSet("ppo")]
    [string[]]$Policies = @(),
    [int]$TrainingSteps = 2048,
    [int]$Epochs = 20,
    [string]$TelemetryExport = "",
    [switch]$Fresh,
    [switch]$CheckpointPackage,
    [switch]$RunAdversarialScenarios,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot = Join-Path $repo $OutputRoot }
if (-not $RunId) { $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") }
if ($RunId -notmatch '^[A-Za-z0-9_-]+$') { throw "RunId must contain only letters, numbers, _ or -" }
if ($Epochs -lt 1 -or $TrainingSteps -lt 1 -or $Seeds.Count -eq 0 -or $Models.Count -eq 0) { throw "Epochs, steps, seeds and models must be nonempty and positive" }
$run = Join-Path $OutputRoot $RunId
$venv = Join-Path $repo ".venv-dt-models"
$python = Join-Path $venv "Scripts/python.exe"
$prediction = Join-Path $repo "services/prediction-service"
$requirements = Join-Path $repo "scripts/requirements-dt-models.txt"
$ppoRequirements = Join-Path $repo "scripts/requirements-dt-ppo.txt"
$compose = Join-Path $repo "infrastructure/docker/docker-compose.yml"
$composeGpu = Join-Path $repo "infrastructure/docker/docker-compose.gpu.yml"
$input = $null
if ($TelemetryExport) {
    $input = (Resolve-Path -LiteralPath $TelemetryExport -ErrorAction Stop).Path
    if (-not [IO.File]::Exists($input)) { throw "TelemetryExport must be a local JSONL file" }
}
if ((Test-Path -LiteralPath $run) -and $Fresh) { throw "Fresh requires a new RunId so previous runs stay intact" }
if ($WhatIf) {
    $pythonAvailable = [bool](Get-Command py, python, python3 -ErrorAction SilentlyContinue)
    Write-Output "WHATIF prerequisites: docker_cli=$([bool](Get-Command docker -ErrorAction SilentlyContinue)); python_launcher=$pythonAvailable; env_file=$(Test-Path -LiteralPath (Join-Path $repo '.env')); local_export=$([bool]$input)"
    Write-Output "WHATIF: run=$run; source=$(if ($input) { 'local JSONL' } else { 'synthetic' }); models=$($Models -join ','); metrics=$($Metrics -join ','); scenarios=$($Scenarios -join ','); seeds=$($Seeds -join ','); policies=$($Policies -join ',')"
    Write-Output "WHATIF: check Docker Desktop/NVIDIA GPU; build and start local Compose stack with GPU override; create project venv and CUDA PyTorch; prepare offline SQLite; estimate; run existing prediction CLI and optional PPO CLI; synthetic scenarios=$RunAdversarialScenarios; zip outputs"
    exit 0
}

New-Item -ItemType Directory -Path $run -Force | Out-Null
$log = Join-Path $run "runner.log"
function Stamp { (Get-Date).ToUniversalTime().ToString("o") }
function Log([string]$message) { $line = "$(Stamp) $message"; Add-Content -LiteralPath $log -Value $line; Write-Host $line }
function SaveJson([string]$path, $value) {
    $tmp = "$path.tmp"
    $value | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $path -Force
}
function Invoke-Local([string]$label, [string]$exe, [string[]]$arguments, [string]$workingDirectory = $repo) {
    Log "START $label executable=$exe arguments=$($arguments -join ' ')"
    $started = Get-Date
    Push-Location $workingDirectory
    try { & $exe @arguments 2>&1 | ForEach-Object { Log "$label $_" } }
    finally { Pop-Location }
    $code = $LASTEXITCODE
    $elapsed = ((Get-Date) - $started).TotalSeconds
    Log "END $label exit=$code seconds=$elapsed"
    return $code
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is required; install Docker Desktop with Linux containers and GPU support first" }
    if (-not (Test-Path -LiteralPath (Join-Path $repo ".env"))) { throw "Local .env is required for Compose; copy .env.example and set unique credentials" }
    $composeArgs = @("compose", "-f", $compose, "-f", $composeGpu)
    if ((Invoke-Local "docker-preflight" "docker" ($composeArgs + @("config", "--quiet"))) -ne 0) { throw "GPU Compose configuration is invalid" }
    if ((Invoke-Local "docker-start" "docker" ($composeArgs + @("up", "-d", "--build"))) -ne 0) { throw "Could not build/start local Docker services" }
    if ((Invoke-Local "docker-gpu-check" "docker" ($composeArgs + @("exec", "-T", "prediction-service", "python", "-c", "import torch; assert torch.cuda.is_available(), 'CUDA GPU unavailable in prediction container'; print(torch.cuda.get_device_name(0))"))) -ne 0) { throw "Prediction container cannot access CUDA GPU" }
    if (-not (Test-Path -LiteralPath $python)) {
        $basePython = (Get-Command py -ErrorAction SilentlyContinue)
        if ($basePython) {
            $selectedVersion = $null
            foreach ($minor in @(13, 12, 11)) {
                & $basePython.Source "-3.$minor" --version *> $null
                if ($LASTEXITCODE -eq 0) { $selectedVersion = "-3.$minor"; break }
            }
            if (-not $selectedVersion) { throw "Python 3.11, 3.12 or 3.13 is required; install one and register it with the py launcher" }
            & $basePython.Source $selectedVersion -m venv $venv
        } else {
            $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
            if (-not $pythonCommand) { $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
            if (-not $pythonCommand) { throw "Python 3.11, 3.12 or 3.13 is required; expose py, python, or python3 on PATH" }
            $pythonVersion = & $pythonCommand.Source --version 2>&1 | Out-String
            if ($pythonVersion -notmatch 'Python 3\.(11|12|13)\.') { throw "Python 3.11, 3.12 or 3.13 is supported; found $($pythonVersion.Trim())" }
            & $pythonCommand.Source -m venv $venv
        }
        if ($LASTEXITCODE -ne 0) { throw "Could not create project-local virtual environment" }
    }
    $installed = Join-Path $venv "dt-requirements.sha256"
    $digest = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    if (-not (Test-Path $installed) -or (Get-Content $installed -Raw).Trim() -ne $digest) {
        if ((Invoke-Local "install-forecast-deps" $python @("-m", "pip", "install", "--requirement", $requirements)) -ne 0) { throw "Pinned forecast dependency install failed" }
        Set-Content -LiteralPath $installed -Value $digest
    }
    $cudaInstalled = Join-Path $venv "dt-cuda-torch.txt"
    if (-not (Test-Path $cudaInstalled) -or (Get-Content $cudaInstalled -Raw).Trim() -ne "2.6.0+cu126") {
        if ((Invoke-Local "install-cuda-torch" $python @("-m", "pip", "install", "torch==2.6.0+cu126", "--index-url", "https://download.pytorch.org/whl/cu126")) -ne 0) { throw "Pinned CUDA PyTorch install failed" }
        Set-Content -LiteralPath $cudaInstalled -Value "2.6.0+cu126"
    }
    if ((Invoke-Local "host-gpu-check" $python @("-c", "import torch; assert torch.cuda.is_available(), 'CUDA GPU unavailable to Windows Python'; print(torch.__version__, torch.cuda.get_device_name(0))")) -ne 0) { throw "Host Python cannot access CUDA GPU" }
    $env:DT_RAM_REQUIRE_CUDA = "1"
    $gpuInfo = & $python -c "import json, torch; print(json.dumps({'torch':torch.__version__, 'cuda_runtime':torch.version.cuda, 'gpu':torch.cuda.get_device_name(0)}))"
    SaveJson (Join-Path $run "runtime.json") @{ timestamp = (Stamp); gpu = ($gpuInfo | ConvertFrom-Json);
        docker = ((& docker --version 2>&1 | Out-String).Trim()); compose = ((& docker compose version 2>&1 | Out-String).Trim()) }
    if ($Policies.Count -gt 0) {
        $ppoInstalled = Join-Path $venv "dt-ppo-requirements.sha256"
        $ppoDigest = (Get-FileHash -LiteralPath $ppoRequirements -Algorithm SHA256).Hash
        if (-not (Test-Path $ppoInstalled) -or (Get-Content $ppoInstalled -Raw).Trim() -ne $ppoDigest) {
            if ((Invoke-Local "install-ppo-deps" $python @("-m", "pip", "install", "--requirement", $ppoRequirements)) -ne 0) { throw "Pinned PPO dependency install failed" }
            Set-Content -LiteralPath $ppoInstalled -Value $ppoDigest
        }
    }
    $version = (& $python --version 2>&1 | Out-String).Trim()
    $gitSha = (& git -C $repo rev-parse HEAD | Out-String).Trim()
    $identity = if ($input) { @{ path = $input; sha256 = (Get-FileHash -LiteralPath $input -Algorithm SHA256).Hash; included_in_archive = $false } } else { @{ source = "synthetic" } }
    $config = @{ schema_version = 1; created_at = (Stamp); git_commit = $gitSha; python = $version; ps_version = $PSVersionTable.PSVersion.ToString();
                 machine = [Environment]::MachineName; os = [Environment]::OSVersion.VersionString; models = $Models; metrics = $Metrics;
                 scenarios = $Scenarios; seeds = $Seeds; policies = $Policies; training_steps = $TrainingSteps; epochs = $Epochs; input = $identity }
    SaveJson (Join-Path $run "config.json") $config
    $jobs = @()
    $failed = @()
    foreach ($scenario in $Scenarios) {
        foreach ($seed in $Seeds) {
            $name = "$scenario-seed$seed"
            $jobDir = Join-Path $run $name
            New-Item -ItemType Directory -Path $jobDir -Force | Out-Null
            $db = Join-Path $OutputRoot "_inputs/$RunId/$name.sqlite"
            $dbParent = Split-Path -Parent $db
            New-Item -ItemType Directory -Path $dbParent -Force | Out-Null
            if (-not (Test-Path -LiteralPath $db)) {
                $prepare = @((Join-Path $repo "scripts/prepare_dt_data.py"), "--output", $db, "--seed", "$seed", "--scenario", $scenario)
                if ($input) { $prepare += @("--input", $input) }
                if ((Invoke-Local "prepare-$name" $python $prepare) -ne 0) { throw "Input preparation failed for $name" }
            }
            Copy-Item -LiteralPath ([IO.Path]::ChangeExtension($db, ".manifest.json")) -Destination (Join-Path $jobDir "input-manifest.json") -Force
            $dataManifest = Get-Content -LiteralPath (Join-Path $jobDir "input-manifest.json") -Raw | ConvertFrom-Json
            if ($input -and $dataManifest.input_sha256 -ne $identity.sha256) { throw "Input changed since $name was prepared; use a new RunId" }
            $calibrationDir = Join-Path $run "calibration"
            if (-not (Test-Path (Join-Path $calibrationDir "summary.json"))) {
                $calibration = @("-m", "prediction_app.scripts.run_all_models", "--db", $db, "--run-dir", $calibrationDir,
                                 "--models", "persistence", "--metrics", "cpu", "--history-steps", "12", "--horizons", "1", "2", "3",
                                 "--seed", "$seed", "--epochs", "1", "--source-label", "synthetic-calibration")
                if ((Invoke-Local "calibrate-persistence" $python $calibration $prediction) -ne 0) { throw "Bounded local calibration failed" }
            }
            $sweep = @("-m", "prediction_app.scripts.run_all_models", "--db", $db, "--run-dir", (Join-Path $jobDir "forecast"),
                       "--models") + $Models + @("--metrics") + $Metrics + @("--seed", "$seed", "--epochs", "$Epochs", "--source-label", $(if ($input) { "local-export" } else { "synthetic-$scenario" }))
            $estimate = $sweep + @("--estimate-only")
            if (-not (Test-Path (Join-Path $jobDir "forecast/runtime_estimate.json"))) {
                if ((Invoke-Local "estimate-$name" $python $estimate $prediction) -ne 0) { throw "Estimate failed for $name" }
            }
            $estimatePath = Join-Path $jobDir "forecast/runtime_estimate.json"
            $estimateJson = Get-Content -LiteralPath $estimatePath -Raw | ConvertFrom-Json
            $calibrationState = Get-Content -LiteralPath (Join-Path $calibrationDir "run_state.json") -Raw | ConvertFrom-Json
            $calibrationSeconds = $calibrationState.jobs.persistence__cpu.duration_seconds
            Log "ESTIMATE $name seconds=$($estimateJson.estimated_remaining_seconds) method=$($estimateJson.estimate_method); calibration_persistence_seconds=$calibrationSeconds; low confidence for statistical and neural models"
            $code = 1
            for ($attempt = 1; $attempt -le 2 -and $code -ne 0; $attempt++) {
                $code = Invoke-Local "forecast-$name-attempt$attempt" $python $sweep $prediction
            }
            $jobs += @{ name = $name; type = "forecast"; exit_code = $code; output = "$name/forecast" }
            if ($code -ne 0) { $failed += "forecast-$name" }
            if ($Policies.Count -gt 0) {
                $policyFile = Join-Path $jobDir "ppo.json"
                if (-not (Test-Path $policyFile)) {
                    $ppo = @((Join-Path $repo "services/rl-service/cli.py"), "--train", "--multi-objective", "--seed", "$seed", "--timesteps", "$TrainingSteps", "--output", $policyFile)
                    $policyCode = Invoke-Local "ppo-$name" $python $ppo
                    $jobs += @{ name = $name; type = "ppo"; exit_code = $policyCode; output = "$name/ppo.json" }
                    if ($policyCode -ne 0) { $failed += "ppo-$name" }
                }
            }
            SaveJson (Join-Path $run "state.json") @{ schema_version = 1; updated_at = (Stamp); jobs = $jobs; failed = $failed }
            if ($CheckpointPackage) { Compress-Archive -Path (Join-Path $run "*") -DestinationPath "$run.zip" -Force }
        }
    }
    if ($RunAdversarialScenarios) {
        $scenarioOutput = Join-Path $run "synthetic-scenarios.json"
        if ((Invoke-Local "adversarial-scenarios" $python @((Join-Path $repo "scripts/run_synthetic_scenarios.py"), "--seed", "$($Seeds[0])", "--output", $scenarioOutput)) -ne 0) {
            $failed += "synthetic-scenarios"
        }
    }
    if ((Invoke-Local "comparison-plots" $python @((Join-Path $repo "scripts/plot_run_comparisons.py"), "--run-dir", $run)) -ne 0) {
        $failed += "comparison-plots"
    }
    $manifest = @{ schema_version = 1; created_at = (Stamp); run_id = $RunId; synthetic = (-not [bool]$input); jobs = $jobs;
                   failed = $failed; input = $identity; archive = "$run.zip"; note = "Offline simulation-only outputs; no live cluster evidence" }
    SaveJson (Join-Path $run "manifest.json") $manifest
    Compress-Archive -Path (Join-Path $run "*") -DestinationPath "$run.zip" -Force
    Log "ARCHIVE $run.zip manifest=$(Join-Path $run 'manifest.json')"
    if ($failed.Count -gt 0) { exit 2 }
} catch {
    Log "FAILURE $($_.Exception.Message)"
    SaveJson (Join-Path $run "failure.json") @{ timestamp = (Stamp); error = $_.Exception.Message }
    Compress-Archive -Path (Join-Path $run "*") -DestinationPath "$run.zip" -Force
    throw
}
