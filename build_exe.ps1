$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Get-Version {
    $pyproject = Join-Path $Root 'pyproject.toml'

    if (-not (Test-Path $pyproject)) {
        throw "pyproject.toml not found: $pyproject"
    }

    $text = Get-Content -Raw -Path $pyproject

    if ($text -match '(?m)^\s*version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }

    throw 'Unable to read version from pyproject.toml'
}

$AppName    = 'SponsorScout'
$Version    = Get-Version
$DistDir    = Join-Path $Root 'dist'
$BuildDir   = Join-Path $DistDir $AppName
$ExePath    = Join-Path $BuildDir "$AppName.exe"

# Detect python launcher
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = 'py'
    $PythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = 'python'
    $PythonArgs = @()
} else {
    throw 'python or py launcher not found in PATH'
}

Write-Host "[1/4] Installing build dependencies..." -ForegroundColor Cyan
& $Python @PythonArgs -m pip install --upgrade pip | Out-Null
& $Python @PythonArgs -m pip install -r requirements.txt pyinstaller | Out-Null
& $Python @PythonArgs -m playwright install chromium | Out-Null

Write-Host "[2/4] Running tests..." -ForegroundColor Cyan
& $Python @PythonArgs -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed (exit $LASTEXITCODE). Aborting build."
}

Write-Host "[3/4] Building SponsorScout.exe with PyInstaller..." -ForegroundColor Cyan
if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}

& $Python @PythonArgs -m PyInstaller `
    --clean `
    --noconfirm `
    --windowed `
    --onedir `
    --name $AppName `
    --icon sponsorscout/data/sponsorscout.ico `
    --collect-data sponsorscout `
    --collect-submodules sponsorscout `
    --collect-submodules playwright `
    --collect-submodules google `
    --collect-submodules google.generativeai `
    --collect-submodules openai `
    --hidden-import google.generativeai `
    --hidden-import openai `
    sponsorscout/main.py

if (-not (Test-Path $ExePath)) {
    throw "PyInstaller did not produce $ExePath"
}
Write-Host "Built $ExePath (version $Version)" -ForegroundColor Green

# Bundle Playwright's Chromium so JS-rendered career pages work out of the box.
# Without this, the installed app gets 0 jobs from all SPA career portals
# because Playwright can't find the browser binary. This mirrors the approach
# in build_deb.sh for Linux.
Write-Host "[3.5/4] Bundling Playwright Chromium..." -ForegroundColor Cyan
$PlaywrightBrowsersPath = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
    $env:PLAYWRIGHT_BROWSERS_PATH
} else {
    Join-Path $env:USERPROFILE '.cache\ms-playwright'
}

# Also check LocalAppData for Playwright browsers
$localPlaywrightPath = Join-Path $env:LOCALAPPDATA 'ms-playwright'
$chromiumFound = $false

# Try USERPROFILE cache first, then LOCALAPPDATA
foreach ($candidate in @($PlaywrightBrowsersPath, $localPlaywrightPath)) {
    if (Test-Path $candidate) {
        $chromiumDir = Get-ChildItem -Path $candidate -Directory -Filter 'chromium*' | Select-Object -First 1
        if ($chromiumDir) {
            $targetDir = Join-Path $BuildDir '_playwright'
            if (-not (Test-Path $targetDir)) {
                New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            }
            Write-Host "  Bundling Chromium from $($chromiumDir.FullName)" -ForegroundColor Green
            Copy-Item -Recurse -Path $chromiumDir.FullName -Destination $targetDir
            $chromiumFound = $true
            break
        }
    }
}

if (-not $chromiumFound) {
    Write-Host "  WARNING: No Chromium directory found for Playwright." -ForegroundColor Yellow
    Write-Host "  JS-rendered career pages will return 0 jobs on installed systems." -ForegroundColor Yellow
    Write-Host "  Install Chromium with: playwright install chromium" -ForegroundColor Yellow
}

$InstallerSrcDir = Join-Path $DistDir "$AppName-InstallerFiles"
if (Test-Path $InstallerSrcDir) {
    Remove-Item -Recurse -Force $InstallerSrcDir
}
Copy-Item -Recurse -Path $BuildDir -Destination $InstallerSrcDir
Copy-Item -Path (Join-Path $Root 'sponsorscout\data\sponsorscout.ico') -Destination $InstallerSrcDir -Force

# Step 4: Build Inno Setup installer if ISCC.exe is available
$Iscc = $null

$cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
$CmdSource = $null
if ($cmd) {
    $CmdSource = $cmd.Source
}

$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
    $CmdSource
)

foreach ($candidate in $IsccCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        $Iscc = $candidate
        break
    }
}

if ($Iscc) {
    Write-Host "[4/4] Building Inno Setup installer..." -ForegroundColor Cyan
    $installerOut = Join-Path $DistDir "sponsorscout-$Version-setup.exe"

    # /F flag must match OutputBaseFilename in installer.iss
    & $Iscc "/DMyAppVersion=$Version" "/O$DistDir" "/Fsponsorscout-$Version-setup" (Join-Path $Root 'installer.iss')

    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compiler failed (exit $LASTEXITCODE)."
    }

    if (Test-Path $installerOut) {
        Write-Host "Built $installerOut" -ForegroundColor Green
    } else {
        Write-Host "Inno Setup ran but expected output not found at $installerOut" -ForegroundColor Yellow
    }
}
else {
    Write-Host "[4/4] Inno Setup not found - installer skipped." -ForegroundColor Yellow
    Write-Host "      Install Inno Setup 6 from https://jrsoftware.org/isinfo.php to produce a" -ForegroundColor Yellow
    Write-Host "      proper Windows installer (dist\sponsorscout-$Version-setup.exe)." -ForegroundColor Yellow
    Write-Host "      The raw SponsorScout.exe and Chromium are still in $BuildDir." -ForegroundColor Yellow
}

if (Test-Path $InstallerSrcDir) {
    Remove-Item -Recurse -Force $InstallerSrcDir
}

Write-Host ""
Write-Host "Done. Artifacts in $DistDir :"
Get-ChildItem $DistDir | ForEach-Object { Write-Host ("  " + $_.Name) }