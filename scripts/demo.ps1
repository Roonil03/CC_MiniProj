#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$clusterName = 'dt-ram'
$clusterApiHost = "k3d-$clusterName-serverlb"
$clusterConfig = Join-Path $repoRoot 'infrastructure/k3s/k3d.yaml'
$dockerfile = Join-Path $repoRoot 'Dockerfile.demo'
$image = 'dt-ram/demo:latest'
$containerKubeconfig = '/tmp/dt-ram-kubeconfig'

function Stop-Demo([string] $Message, [int] $ExitCode = 1) {
    [Console]::Error.WriteLine("DT-RAM demo launcher: $Message")
    exit $ExitCode
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-Demo 'Docker CLI is required. Install Docker Desktop or Docker Engine and retry.' 127
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-Demo 'Docker daemon is unavailable. Start Docker Desktop or Docker Engine and retry.'
}
if (-not (Get-Command k3d -ErrorAction SilentlyContinue)) {
    Stop-Demo 'k3d is required to create the local Kubernetes cluster. Install k3d and retry.' 127
}
if (-not (Test-Path -LiteralPath $clusterConfig -PathType Leaf)) {
    Stop-Demo "expected k3d config at $clusterConfig"
}
if (-not (Test-Path -LiteralPath $dockerfile -PathType Leaf)) {
    Stop-Demo "expected demo Dockerfile at $dockerfile"
}

& k3d cluster get $clusterName *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Using existing k3d cluster: $clusterName"
} else {
    Write-Output "Creating k3d cluster: $clusterName"
    & k3d cluster create --config $clusterConfig
    if ($LASTEXITCODE -ne 0) {
        Stop-Demo "could not create k3d cluster '$clusterName'"
    }
}

Write-Output "Building demo image: $image"
& docker build --file $dockerfile --tag $image $repoRoot
if ($LASTEXITCODE -ne 0) {
    Stop-Demo "could not build image '$image'"
}

$kubeconfigPath = Join-Path ([IO.Path]::GetTempPath()) ("dt-ram-kubeconfig-$([guid]::NewGuid().ToString('N')).yaml")
try {
    $kubeconfig = & k3d kubeconfig get $clusterName
    if ($LASTEXITCODE -ne 0) {
        Stop-Demo "could not read kubeconfig for '$clusterName'"
    }
    $kubeconfig = $kubeconfig -join "`n"
    $kubeconfig = [regex]::Replace(
        $kubeconfig,
        'https://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?=:[0-9]+)',
        "https://$clusterApiHost"
    )
    [IO.File]::WriteAllText($kubeconfigPath, $kubeconfig, [Text.UTF8Encoding]::new($false))

    Write-Output "Running shadow-only demo against cluster: $clusterName"
    & docker run --rm `
        "--add-host=${clusterApiHost}:host-gateway" `
        --volume "${kubeconfigPath}:${containerKubeconfig}:ro" `
        $image --kubeconfig $containerKubeconfig @args
    $demoExitCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $kubeconfigPath -Force -ErrorAction SilentlyContinue
}

exit $demoExitCode
