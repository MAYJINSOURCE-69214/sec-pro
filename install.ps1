param(
    [switch]$InstallDeps,
    [switch]$SkipGsd,
    [string]$CodexHome,
    [string]$SkillsHome,
    [string]$DataDir
)
$ErrorActionPreference = 'Stop'

function Find-Python {
    foreach ($candidate in @('python', 'python3', 'py')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

if ($InstallDeps) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Explicit dependency bootstrap requires Windows App Installer (winget).' }
    if (-not (Find-Python)) {
        & winget install --id Python.Python.3.12 --exact --scope user --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    }
    if (-not $SkipGsd) {
        $nodeOK = $false
        if (Get-Command node -ErrorAction SilentlyContinue) {
            & node -e 'process.exit(Number(process.versions.node.split(".")[0])>=24?0:1)'
            $nodeOK = $LASTEXITCODE -eq 0
        }
        if (-not $nodeOK) {
            & winget install --id OpenJS.NodeJS.LTS --exact --scope user --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Node installation failed; install Node 24+ manually if no user-scope package is available.' }
        }
    }
    # Refresh only this process after explicit package-manager installation.
    $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
}
$pythonCommand = Find-Python
if (-not $pythonCommand) { throw 'Python 3.11+ required. Install manually or explicitly rerun with -InstallDeps.' }
$installerArgs = @((Join-Path $PSScriptRoot 'install.py'))
if ($SkipGsd) { $installerArgs += '--skip-gsd' }
if ($CodexHome) { $installerArgs += @('--codex-home', $CodexHome) }
if ($SkillsHome) { $installerArgs += @('--skills-home', $SkillsHome) }
if ($DataDir) { $installerArgs += @('--data-dir', $DataDir) }
& $pythonCommand @installerArgs
exit $LASTEXITCODE
