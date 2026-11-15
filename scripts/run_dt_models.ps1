# Offline, simulation-only Windows model runner. Compatible with Windows PowerShell 5.1 and PowerShell 7.
param(
    [string]$OutputRoot = "experiments/runs/windows-models",
    [string]$RunId = "",
    [string[]]$Models = @("persistence", "arima", "ets", "lstm", "gru", "temporal", "transformer"),
    [string[]]$Metrics = @("cpu"),
    [string[]]$Scenarios = @("stable"),
    [string[]]$Seeds = @("42"),
    [string[]]$Policies = @(),
    [int]$TrainingSteps = 2048,
    [int]$Epochs = 20,
    [int]$PeriodSeconds = 1,
    [int]$HistorySteps = 60,
    [string[]]$Horizons = @("5", "10", "30", "60"),
    [switch]$Tune,
    [switch]$UseBitbrains,
    [string]$BitbrainsArchive = "",
    [string]$TelemetryExport = "",
    [switch]$Fresh,
    [switch]$CheckpointPackage,
    [switch]$RunAdversarialScenarios,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
if ($UseBitbrains) {
    if (-not $PSBoundParameters.ContainsKey("Metrics")) { $Metrics = @("cpu", "memory") }
    if (-not $PSBoundParameters.ContainsKey("PeriodSeconds")) { $PeriodSeconds = 300 }
    if (-not $PSBoundParameters.ContainsKey("HistorySteps")) { $HistorySteps = 60 }
    if (-not $PSBoundParameters.ContainsKey("Horizons")) { $Horizons = @("300", "600", "1800", "3600") }
}
$Models = @($Models | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Metrics = @($Metrics | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Scenarios = @($Scenarios | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Policies = @($Policies | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Horizons = @($Horizons | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (@($Horizons | Where-Object { $_ -notmatch '^\d+$' -or [long]$_ -gt [int]::MaxValue }).Count -gt 0) { throw "Horizons must be comma-separated positive integers" }
$Horizons = @($Horizons | ForEach-Object { [int]$_ })
$seedValues = @($Seeds | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (@($seedValues | Where-Object { $_ -notmatch '^\d+$' -or [long]$_ -gt [int]::MaxValue }).Count -gt 0) {
    throw "Seeds must be comma-separated nonnegative integers"
}
$Seeds = @($seedValues | ForEach-Object { [int]$_ })
$validModels = @("persistence", "arima", "ets", "lstm", "gru", "temporal", "transformer")
$validMetrics = @("cpu", "memory", "network_in", "network_out")
$validScenarios = @("stable", "burst", "memory-pressure")
$validPolicies = @("ppo")
if (@($Models | Where-Object { $_ -notin $validModels }).Count -gt 0) { throw "Unsupported model selection: $($Models -join ',')" }
if (@($Metrics | Where-Object { $_ -notin $validMetrics }).Count -gt 0) { throw "Unsupported metric selection: $($Metrics -join ',')" }
if (@($Scenarios | Where-Object { $_ -notin $validScenarios }).Count -gt 0) { throw "Unsupported scenario selection: $($Scenarios -join ',')" }
if (@($Policies | Where-Object { $_ -notin $validPolicies }).Count -gt 0) { throw "Unsupported policy selection: $($Policies -join ',')" }
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot = Join-Path $repo $OutputRoot }
if (-not $RunId) { $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") }
if ($RunId -notmatch '^[A-Za-z0-9_-]+$') { throw "RunId must contain only letters, numbers, _ or -" }
if ($Epochs -lt 1 -or $TrainingSteps -lt 1 -or $Seeds.Count -eq 0 -or $Models.Count -eq 0) { throw "Epochs, steps, seeds and models must be nonempty and positive" }
$run = Join-Path $OutputRoot $RunId
$python = "container-python"
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
if ($UseBitbrains -and $TelemetryExport) { throw "Choose either Bitbrains or TelemetryExport" }
if ($PeriodSeconds -lt 1 -or $HistorySteps -lt 1 -or $Horizons.Count -eq 0 -or @($Horizons | Where-Object { $_ -lt 1 }).Count) { throw "PeriodSeconds, HistorySteps and Horizons must be positive" }
if ($UseBitbrains -and ($PeriodSeconds -ne 300 -or $HistorySteps -ne 60 -or ($Horizons -join ',') -ne '300,600,1800,3600')) { throw "Bitbrains requires -PeriodSeconds 300 -HistorySteps 60 -Horizons 300,600,1800,3600" }
if ((Test-Path -LiteralPath $run) -and $Fresh) { throw "Fresh requires a new RunId so previous runs stay intact" }
if ($WhatIf) {
    Write-Output "WHATIF prerequisites: docker_cli=$([bool](Get-Command docker -ErrorAction SilentlyContinue)); env_file=$(Test-Path -LiteralPath (Join-Path $repo '.env')); local_export=$([bool]$input); Python=GPU-enabled Docker container"
    Write-Output "WHATIF: run=$run; source=$(if ($UseBitbrains) { 'Bitbrains fastStorage' } elseif ($input) { 'local JSONL' } else { 'synthetic' }); models=$($Models -join ','); metrics=$($Metrics -join ','); scenarios=$($Scenarios -join ','); seeds=$($Seeds -join ','); policies=$($Policies -join ',')"
    Write-Output "WHATIF: check Docker Desktop/NVIDIA GPU; build and start local Compose stack with GPU override; run preparation, estimation, training, plots in its Python container; prepare offline SQLite; run existing prediction CLI and optional PPO CLI; synthetic scenarios=$RunAdversarialScenarios; zip outputs"
    exit 0
}

# Reject incompatible resumes before touching prior output or starting services.
$existingConfig = Join-Path $run "config.json"
if (Test-Path -LiteralPath $existingConfig) {
    $prior = Get-Content -LiteralPath $existingConfig -Raw | ConvertFrom-Json
    $requested = @{ models=$Models; metrics=$Metrics; scenarios=$Scenarios; seeds=$Seeds; policies=$Policies;
                    training_steps=$TrainingSteps; epochs=$Epochs; period_seconds=$PeriodSeconds;
                    history_steps=$HistorySteps; horizons=$Horizons; tune=[bool]$Tune }
    foreach ($key in $requested.Keys) {
        if ((@($prior.$key) -join ",") -ne (@($requested[$key]) -join ",")) { throw "Run configuration changed ($key); use a new RunId" }
    }
    $requestedSource = if ($UseBitbrains) { "bitbrains-fastStorage" } elseif ($input) { $null } else { "synthetic" }
    if ($prior.input.source -ne $requestedSource) { throw "Run input changed; use a new RunId" }
    $sourceFile = $input
    if ($UseBitbrains) {
        $sourceFile = if ($BitbrainsArchive) { $BitbrainsArchive } else { Join-Path $repo "datasets/raw/gwa_t_12_fastStorage.zip" }
        if (-not [IO.Path]::IsPathRooted($sourceFile)) { $sourceFile = Join-Path $repo $sourceFile }
        if (-not (Test-Path -LiteralPath $sourceFile)) { throw "Cached Bitbrains archive is required to verify this resume" }
    }
    if ($sourceFile -and (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash -ne $prior.input.sha256) { throw "Run input changed; use a new RunId" }
}
New-Item -ItemType Directory -Path $run -Force | Out-Null
$log = Join-Path $run "runner.log"
function Stamp { (Get-Date).ToUniversalTime().ToString("o") }
function Log([string]$message) {
    $record = @{ timestamp = (Stamp); event = "runner"; message = $message; system = @{
        machine = [Environment]::MachineName; os = [Environment]::OSVersion.VersionString;
        processor_count = [Environment]::ProcessorCount; working_set_bytes = [Environment]::WorkingSet
    } }
    $line = $record | ConvertTo-Json -Compress -Depth 5
    [IO.File]::AppendAllText((Join-Path $run "runner-events.jsonl"), "$line`n", (New-Object Text.UTF8Encoding($false)))
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    Write-Host $line
}
function SaveJson([string]$path, $value) {
    $tmp = "$path.tmp"
    $value | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $path -Force
}
function Test-PpoResult([string]$path, [int]$seed, [int]$steps) {
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try {
        $result = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        return ($result.seed -eq $seed -and $result.config.algorithm -eq "PPO" -and $result.config.training -eq $true -and
                $result.ppo.requested_steps -eq $steps -and $result.ppo.actual_steps -ge $steps -and
                $null -ne $result.ppo.policy -and $null -ne $result.evaluation.comparators.ppo)
    } catch { return $false }
}
function To-ContainerPath([string]$path) {
    $fullPath = [IO.Path]::GetFullPath($path)
    $rootPrefix = $repo.TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
    if ($fullPath -ne $repo -and -not $fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Container-run input/output path must be inside the repository: $path"
    }
    $relative = $fullPath.Substring($repo.Length).TrimStart([char[]]@('\', '/')).Replace('\', '/')
    return "/workspace/$relative"
}
function Invoke-Local([string]$label, [string]$exe, [string[]]$arguments, [string]$workingDirectory = $repo) {
    if ($exe -eq "container-python") {
        $mapped = @($arguments | ForEach-Object {
            if ($_ -eq "/workspace" -or $_.StartsWith("/workspace/", [StringComparison]::Ordinal)) { $_ } elseif ([IO.Path]::IsPathRooted($_)) { To-ContainerPath $_ } else { $_ }
        })
        $exe = "docker"
        $arguments = $composeArgs + @("exec", "-T", "-w", "/workspace/services/prediction-service",
                                      "prediction-service", "python") + $mapped
    }
    Log "START $label executable=$exe arguments=$($arguments -join ' ')"
    $started = Get-Date
    Push-Location $workingDirectory
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell can turn native stderr progress into terminating
        # ErrorRecords when the caller uses Stop. Keep the process exit code as
        # the authority and capture both output streams into the run log.
        $ErrorActionPreference = "Continue"
        & $exe @arguments 2>&1 | ForEach-Object { Log "$label $_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    Log "END $label exit=$code seconds=$elapsed"
    return $code
}

$resumeRejected = $false
$jobs = @()
$failed = @()
$failurePath = Join-Path $run "failure.json"
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is required; install Docker Desktop with Linux containers and GPU support first" }
    if (-not (Test-Path -LiteralPath (Join-Path $repo ".env"))) { throw "Local .env is required for Compose; copy .env.example and set unique credentials" }
    $composeArgs = @("compose", "--progress", "plain", "--env-file", (Join-Path $repo ".env"),
                     "-f", $compose, "-f", $composeGpu)
    if ((Invoke-Local "docker-preflight" "docker" ($composeArgs + @("config", "--quiet"))) -ne 0) { throw "GPU Compose configuration is invalid" }
    if ((Invoke-Local "docker-start" "docker" ($composeArgs + @("up", "-d", "--build", "--pull", "missing"))) -ne 0) { throw "Could not pull missing images, build images, and start local Docker services" }
    if ((Invoke-Local "docker-gpu-check" "docker" ($composeArgs + @("exec", "-T", "prediction-service", "python", "-c", "import torch; assert torch.cuda.is_available(), 'CUDA GPU unavailable in prediction container'; print(torch.cuda.get_device_name(0))"))) -ne 0) { throw "Prediction container cannot access CUDA GPU" }
    if ((Invoke-Local "container-python-check" $python @("-c", "import torch; assert torch.cuda.is_available(), 'CUDA GPU unavailable'; print('Python GPU runtime:', __import__('sys').version, torch.__version__, torch.cuda.get_device_name(0))")) -ne 0) { throw "GPU-enabled container Python is unavailable" }
    if ((Invoke-Local "install-model-deps" $python @("-m", "pip", "install", "--requirement", "/workspace/scripts/requirements-dt-models.txt")) -ne 0) { throw "Pinned model dependency install failed" }
    if ($Policies.Count -gt 0) {
        if ((Invoke-Local "install-ppo-deps" $python @("-m", "pip", "install", "--requirement", "/workspace/scripts/requirements-dt-ppo.txt")) -ne 0) { throw "Pinned PPO dependency install failed" }
    }
    if ($UseBitbrains) {
        if (-not $BitbrainsArchive) { $BitbrainsArchive = Join-Path $repo "datasets/raw/gwa_t_12_fastStorage.zip" }
        if (-not [IO.Path]::IsPathRooted($BitbrainsArchive)) { $BitbrainsArchive = Join-Path $repo $BitbrainsArchive }
        [void](To-ContainerPath $BitbrainsArchive)
        if (-not (Test-Path -LiteralPath $BitbrainsArchive)) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BitbrainsArchive) | Out-Null
            $partial = "$BitbrainsArchive.part"
            Log "Downloading official Bitbrains fastStorage archive"
            try { Invoke-WebRequest -Uri "https://atlarge-research.com/gwa-traces/gwa_t_12_fastStorage.zip" -OutFile $partial; Move-Item -LiteralPath $partial -Destination $BitbrainsArchive }
            catch { if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }; throw }
        }
    }
    $version = "GPU-enabled prediction-service container Python (version recorded by container-python-check)"
    $gitSha = (& git -C $repo rev-parse HEAD | Out-String).Trim()
    $identity = if ($UseBitbrains) { @{ source = "bitbrains-fastStorage"; sha256 = (Get-FileHash -LiteralPath $BitbrainsArchive -Algorithm SHA256).Hash } } elseif ($input) { @{ path = $input; sha256 = (Get-FileHash -LiteralPath $input -Algorithm SHA256).Hash; included_in_archive = $false } } else { @{ source = "synthetic" } }
    $config = @{ schema_version = 1; created_at = (Stamp); git_commit = $gitSha; python = $version; ps_version = $PSVersionTable.PSVersion.ToString();
                 machine = [Environment]::MachineName; os = [Environment]::OSVersion.VersionString; models = $Models; metrics = $Metrics;
                 scenarios = $Scenarios; seeds = $Seeds; policies = $Policies; training_steps = $TrainingSteps; epochs = $Epochs; period_seconds = $PeriodSeconds; history_steps = $HistorySteps; horizons = $Horizons; tune = [bool]$Tune; input = $identity }
    $configPath = Join-Path $run "config.json"
    if (Test-Path -LiteralPath $configPath) {
        $previous = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        foreach ($key in @("models", "metrics", "scenarios", "seeds", "policies", "training_steps", "epochs", "period_seconds", "history_steps", "horizons", "tune")) {
            if ((@($previous.$key) -join ",") -ne (@($config[$key]) -join ",")) { $resumeRejected = $true; throw "Run configuration changed ($key); use a new RunId" }
        }
        if ($previous.input.sha256 -ne $identity.sha256 -or $previous.input.source -ne $identity.source) { $resumeRejected = $true; throw "Run input changed; use a new RunId" }
    } else { SaveJson $configPath $config }
    foreach ($scenario in $Scenarios) {
        foreach ($seed in $Seeds) {
            $name = "$scenario-seed$seed"
            $jobDir = Join-Path $run $name
            New-Item -ItemType Directory -Path $jobDir -Force | Out-Null
            $db = Join-Path $jobDir "input.sqlite"
            $dbParent = Split-Path -Parent $db
            New-Item -ItemType Directory -Path $dbParent -Force | Out-Null
            $dbManifest = if ($UseBitbrains) { "$db.manifest.json" } else { [IO.Path]::ChangeExtension($db, ".manifest.json") }
            $hasDb = Test-Path -LiteralPath $db
            $hasManifest = Test-Path -LiteralPath $dbManifest
            if ($hasDb -xor $hasManifest) {
                Log "Discarding incomplete input artifacts for $name"
                foreach ($partialPath in @($db, $dbManifest, "$db-wal", "$db-shm")) {
                    if (Test-Path -LiteralPath $partialPath) { Remove-Item -LiteralPath $partialPath -Force }
                }
            }
            if (-not (Test-Path -LiteralPath $db) -and $UseBitbrains) {
                if ((Invoke-Local "import-$name" $python @("-m", "prediction_app.bitbrains", "--archive", $BitbrainsArchive, "--db", $db, "--max-vms", "5")) -ne 0) { throw "Bitbrains import failed for $name" }
            }
            if (-not (Test-Path -LiteralPath $db)) {
                $prepare = @((Join-Path $repo "scripts/prepare_dt_data.py"), "--output", $db, "--seed", "$seed", "--scenario", $scenario)
                if ($input) { $prepare += @("--input", $input) }
                if ((Invoke-Local "prepare-$name" $python $prepare) -ne 0) { throw "Input preparation failed for $name" }
            }
            Copy-Item -LiteralPath $dbManifest -Destination (Join-Path $jobDir "input-manifest.json") -Force
            $dataManifest = Get-Content -LiteralPath (Join-Path $jobDir "input-manifest.json") -Raw | ConvertFrom-Json
            if ($UseBitbrains -and ($dataManifest.archive_sha256 -ne $identity.sha256 -or $dataManifest.cadence_seconds -ne 300 -or $dataManifest.source_url -ne "https://atlarge-research.com/gwa-t-12/" -or $dataManifest.download_url -ne "https://atlarge-research.com/gwa-traces/gwa_t_12_fastStorage.zip")) { throw "Bitbrains input provenance does not match the requested source and cadence; use a new RunId" }
            if ((Invoke-Local "check-input-$name" $python @("-c", "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok', 'SQLite integrity check failed'", $db)) -ne 0) { throw "Input database integrity check failed for $name" }
            if ($input -and $dataManifest.input_sha256 -ne $identity.sha256) { throw "Input changed since $name was prepared; use a new RunId" }
            $calibrationDir = Join-Path $run "calibration"
            if (-not (Test-Path (Join-Path $calibrationDir "summary.json"))) {
                $calibration = @("-m", "prediction_app.scripts.run_all_models", "--db", $db, "--run-dir", $calibrationDir,
                                 "--models", "persistence", "--metrics", "cpu", "--history-steps", "$HistorySteps", "--period-seconds", "$PeriodSeconds", "--horizons") + @($Horizons | ForEach-Object { "$_" }) + @(
                                 "--seed", "$seed", "--epochs", "1", "--source-label", $(if ($UseBitbrains) { "bitbrains-calibration" } elseif ($input) { "local-calibration" } else { "synthetic-calibration" }))
                if ((Invoke-Local "calibrate-persistence" $python $calibration $prediction) -ne 0) { throw "Bounded local calibration failed" }
            }
            $sweep = @("-m", "prediction_app.scripts.run_all_models", "--db", $db, "--run-dir", (Join-Path $jobDir "forecast"),
                       "--models") + $Models + @("--metrics") + $Metrics + @("--seed", "$seed", "--epochs", "$Epochs", "--period-seconds", "$PeriodSeconds", "--history-steps", "$HistorySteps", "--horizons") + @($Horizons | ForEach-Object { "$_" }) + @("--source-label", $(if ($UseBitbrains) { "bitbrains-fastStorage" } elseif ($input) { "local-export" } else { "synthetic-$scenario" }))
            if ($Tune) { $sweep += "--tune" }
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
                if (-not (Test-PpoResult $policyFile $seed $TrainingSteps)) {
                    if (Test-Path -LiteralPath $policyFile) { Log "Discarding incomplete PPO result for $name"; Remove-Item -LiteralPath $policyFile -Force }
                    $ppo = @((Join-Path $repo "services/rl-service/cli.py"), "--train", "--multi-objective", "--seed", "$seed", "--timesteps", "$TrainingSteps", "--output", $policyFile)
                    $policyCode = Invoke-Local "ppo-$name" $python $ppo
                    if ($policyCode -eq 0 -and -not (Test-PpoResult $policyFile $seed $TrainingSteps)) { $policyCode = 1; Log "PPO result validation failed for $name" }
                    $jobs += @{ name = $name; type = "ppo"; exit_code = $policyCode; output = "$name/ppo.json" }
                    if ($policyCode -ne 0) { $failed += "ppo-$name" }
                } else {
                    $jobs += @{ name = $name; type = "ppo"; exit_code = 0; output = "$name/ppo.json"; resumed = $true }
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
    $status = if ($failed.Count -gt 0) { "incomplete" } else { "completed" }
    if ($failed.Count -gt 0) { SaveJson $failurePath @{ timestamp = (Stamp); failed = $failed } }
    elseif (Test-Path -LiteralPath $failurePath) { Remove-Item -LiteralPath $failurePath }
    SaveJson (Join-Path $run "state.json") @{ schema_version = 1; updated_at = (Stamp); status = $status; jobs = $jobs; failed = $failed }
    $manifest = @{ schema_version = 1; status = $status; created_at = (Stamp); run_id = $RunId; synthetic = (-not [bool]$input -and -not $UseBitbrains); jobs = $jobs;
                   failed = $failed; input = $identity; archive = "$run.zip"; note = "Offline forecasting and simulation; no live cluster evidence" }
    SaveJson (Join-Path $run "manifest.json") $manifest
    Log "ARCHIVE $run.zip manifest=$(Join-Path $run 'manifest.json')"
    Compress-Archive -Path (Join-Path $run "*") -DestinationPath "$run.zip" -Force
    if ($failed.Count -gt 0) { exit 2 }
} catch {
    if ($resumeRejected) { throw }
    Log "FAILURE $($_.Exception.Message)"
    $errorMessage = $_.Exception.Message
    SaveJson $failurePath @{ timestamp = (Stamp); error = $errorMessage }
    SaveJson (Join-Path $run "state.json") @{ schema_version = 1; updated_at = (Stamp); status = "failed"; jobs = $jobs; failed = @("runner"); error = $errorMessage }
    SaveJson (Join-Path $run "manifest.json") @{ schema_version = 1; created_at = (Stamp); run_id = $RunId; status = "failed"; jobs = $jobs; failed = @("runner"); error = $errorMessage; archive = "$run.zip" }
    Compress-Archive -Path (Join-Path $run "*") -DestinationPath "$run.zip" -Force
    throw
}
