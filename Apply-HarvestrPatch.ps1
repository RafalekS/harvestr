param()
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host ""
Write-Host "=== Harvestr Install Script ===" -ForegroundColor Cyan
Write-Host ""

$defaultClone = "C:\Scripts\Media\harvestr"
$cloneDir = Read-Host "Clone destination (Enter for '$defaultClone')"
if ([string]::IsNullOrWhiteSpace($cloneDir)) { $cloneDir = $defaultClone }
$cloneDir = $cloneDir.Trim('"').Trim("'")

# Warn if deploying to the source folder
$resolvedClone  = (Resolve-Path $cloneDir  -ErrorAction SilentlyContinue).Path
$resolvedScript = (Resolve-Path $scriptDir -ErrorAction SilentlyContinue).Path
if ($resolvedClone -and $resolvedScript -and ($resolvedClone -eq $resolvedScript)) {
    Write-Host ""
    Write-Host "WARNING: You are deploying INTO the source folder." -ForegroundColor Yellow
    Write-Host "git clean will delete harvestr-local.patch and other custom files." -ForegroundColor Yellow
    $confirm = Read-Host "Type YES to continue anyway, or Enter to cancel"
    if ($confirm -ne "YES") { Write-Host "Cancelled." -ForegroundColor Red; exit 0 }
}

$defaultPatch = "V:\harvestr\patch\harvestr-local.patch"
$patchFile = Read-Host "Patch file (Enter for '$defaultPatch')"
if ([string]::IsNullOrWhiteSpace($patchFile)) { $patchFile = $defaultPatch }
$patchFile = $patchFile.Trim('"').Trim("'")

$defaultConfig = "Y:\Downloads\metube\harvstr\config.json"
$nasConfig = Read-Host "config.json (Enter for '$defaultConfig')"
if ([string]::IsNullOrWhiteSpace($nasConfig)) { $nasConfig = $defaultConfig }
$nasConfig = $nasConfig.Trim('"').Trim("'")

Write-Host ""
if (-not (Test-Path $patchFile)) {
    Write-Host "ERROR: Patch not found: $patchFile" -ForegroundColor Red; exit 1
}
Write-Host "Patch: $patchFile" -ForegroundColor Green

if (Test-Path "$cloneDir\.git") {
    Write-Host "Repo exists - resetting to clean upstream..." -ForegroundColor Yellow
    Push-Location $cloneDir
    # Back up user files that survive updates
    $launcherSettings = Join-Path $cloneDir "_launcher_settings.json"
    $launcherSettingsBak = $null
    if (Test-Path $launcherSettings) {
        $launcherSettingsBak = Get-Content $launcherSettings -Raw
        Write-Host "Backed up _launcher_settings.json" -ForegroundColor DarkGray
    }
    git checkout -- .
    git clean -fd
    git fetch origin
    git reset --hard origin/main
    Pop-Location
    Write-Host "Reset complete." -ForegroundColor Green
} else {
    if (Test-Path $cloneDir) {
        Write-Host "ERROR: $cloneDir exists but is not a git repo." -ForegroundColor Red; exit 1
    }
    Write-Host "Cloning..." -ForegroundColor Green
    git clone https://github.com/KevinStreetCoder/harvestr.git $cloneDir
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: clone failed." -ForegroundColor Red; exit 1 }
}

Push-Location $cloneDir
try {
    Write-Host ""
    Write-Host "Checking patch..." -ForegroundColor Green
    git apply --check --whitespace=nowarn $patchFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Patch does not apply cleanly. Regenerate from source." -ForegroundColor Red; exit 1
    }
    git apply --whitespace=nowarn $patchFile
    Write-Host "Patch applied." -ForegroundColor Green

    # Restore patch file into the deployed folder so it is not missing after git clean
    $localPatch = Join-Path $cloneDir "harvestr-local.patch"
    if (-not (Test-Path $localPatch)) {
        Copy-Item $patchFile $localPatch -Force
        Write-Host "Patch file restored to $cloneDir" -ForegroundColor DarkGray
    }
    # Restore _launcher_settings.json (user's host/port/config_path survive updates)
    if ($launcherSettingsBak) {
        Set-Content -Path $launcherSettings -Value $launcherSettingsBak -NoNewline
        Write-Host "Restored _launcher_settings.json" -ForegroundColor DarkGray
    }

    Write-Host ""
    $venvPip = Join-Path $cloneDir "venv\Scripts\pip.exe"
    $venvPy  = Join-Path $cloneDir "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Host "Creating venv..." -ForegroundColor Green
        python -m venv venv
    } else {
        Write-Host "Venv exists." -ForegroundColor DarkGray
    }

    Write-Host "Installing packages..." -ForegroundColor Green
    & $venvPip install -r requirements.txt --quiet

    $playwright = Join-Path $cloneDir "venv\Scripts\playwright.exe"
    if (Test-Path $playwright) {
        Write-Host "Installing Playwright chromium..." -ForegroundColor Green
        & $playwright install chromium 2>&1 | Out-Null
    }

    Write-Host ""
    if (Test-Path $nasConfig) {
        $content = Get-Content $nasConfig -Raw
        if ($content -match '"impersonate_target":\s*"chrome(136|-136)"') {
            Write-Host "Fixing impersonate_target -> chrome..." -ForegroundColor Green
            $content -replace '"impersonate_target":\s*"chrome(136|-136)"','"impersonate_target": "chrome"' |
                Set-Content $nasConfig -NoNewline
        } elseif ($content -match '"impersonate_target":\s*"chrome"') {
            Write-Host "impersonate_target already OK." -ForegroundColor DarkGray
        } else {
            Write-Host "WARNING: impersonate_target not found - check manually." -ForegroundColor Yellow
        }
    } else {
        Write-Host "WARNING: config not found at $nasConfig" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=== Done ===" -ForegroundColor Green
    Write-Host "Installed to : $cloneDir"
    Write-Host "Config       : $nasConfig"
    Write-Host "Launch       : $cloneDir\launcher.cmd" -ForegroundColor Cyan
    Write-Host ""
} finally {
    Pop-Location
}
