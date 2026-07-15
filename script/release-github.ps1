<#
.SYNOPSIS
    Release hex-bridge firmware to GitHub with a version tag.

.DESCRIPTION
    Usage examples (copy & paste directly):
      .\script\release-github.ps1 v1.0.0                  # release version v1.0.0
      .\script\release-github.ps1 v1.0.0 -Message "Fix CAN issue"   # custom release notes
      .\script\release-github.ps1 v1.0.0 -DryRun          # preview without changes

    Prerequisites:
      - GitHub CLI (gh) for creating releases — install via: winget install GitHub.cli
#>

param(
    [Parameter(Mandatory, Position = 0, HelpMessage = "Release version (e.g. v1.0.0)")]
    [string]$Version,

    [Parameter(HelpMessage = "Release notes / commit message")]
    [string]$Message = "Release $Version",

    [Parameter(HelpMessage = "Dry run: show what would happen without making changes")]
    [switch]$DryRun,

    [Parameter(HelpMessage = "Branch name (default: master)")]
    [string]$Branch = "master",

    [Parameter(HelpMessage = "GitHub repo (e.g. owner/repo)")]
    [string]$Repo = "dotLinePlane-com/hex-bridge",

    [Parameter(HelpMessage = "Firmware binary file to attach (default: build\hex-bridge.bin)")]
    [string]$Asset = "build\hex-bridge.bin"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================"
Write-Host " hex-bridge GitHub Release Script"
Write-Host "============================================"
Write-Host ""

function Invoke-Step {
    param([string]$Description, [ScriptBlock]$Action)
    Write-Host ">>> $Description" -ForegroundColor Cyan
    if ($DryRun) {
        Write-Host "    [DRY RUN] $($Action.ToString().Trim())" -ForegroundColor DarkGray
    } else {
        & $Action
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            Write-Host "    FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    Write-Host ""
}

Write-Host "Version  : $Version"
Write-Host "Message  : $Message"
Write-Host "Branch   : $Branch"
Write-Host "Repo     : $Repo"
Write-Host "Asset    : $Asset"
Write-Host "Dry Run  : $($DryRun.IsPresent)"
Write-Host ""

# Step 1: Check asset exists
if (-not (Test-Path $Asset)) {
    Write-Host ">>> WARNING: Asset file not found at '$Asset' — will create release without binary." -ForegroundColor Yellow
    Write-Host ""
}

# Step 2: Ensure clean git state
$gitStatus = if ($DryRun) { @() } else { @(git status --porcelain) }
if ($gitStatus.Count -gt 0) {
    Write-Host ">>> Uncommitted changes detected:" -ForegroundColor Yellow
    $gitStatus | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Write-Host ""
    Invoke-Step "Staging all changes" {
        git add -A
    }
    Invoke-Step "Creating commit" {
        git commit -m $Message
    }
} else {
    Write-Host ">>> Working tree clean — no commit needed." -ForegroundColor Green
    Write-Host ""
}

# Step 3: Create & push tag
Invoke-Step "Creating tag '$Version'" {
    git tag -a $Version -m $Message
}

Invoke-Step "Pushing branch '$Branch'" {
    git push origin $Branch
}

Invoke-Step "Pushing tag '$Version'" {
    git push origin $Version
}

# Step 4: Create GitHub release
$ghAvailable = if ($DryRun) { $true } else {
    try {
        $null = Get-Command gh -ErrorAction Stop
        $true
    } catch { $false }
}

if (-not $ghAvailable) {
    Write-Host ">>> GitHub CLI (gh) not found — skipping release creation." -ForegroundColor Yellow
    Write-Host "    Install: winget install GitHub.cli" -ForegroundColor Yellow
    $assetArg = if (Test-Path $Asset) { "`"$Asset`"" } else { "" }
    Write-Host "    Then run: gh release create $Version $assetArg --repo $Repo --title `"$Message`" --notes `"$Message`"" -ForegroundColor Yellow
    Write-Host ""
} else {
    $ghArgs = @("release", "create", $Version, "--repo", $Repo, "--title", $Message, "--notes", $Message)
    if (Test-Path $Asset) {
        $ghArgs += $Asset
    }
    Invoke-Step "Creating GitHub release '$Version'" {
        & gh $ghArgs
    }
}

Write-Host "============================================"
Write-Host " Done — hex-bridge $Version released."
Write-Host "============================================"
