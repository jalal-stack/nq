# Imports the local TradeMind MVP into legacy/mvp/ on the integration branch.
#
# The MVP is copied into a quarantine folder that is never imported, packaged, tested or deployed,
# so nothing in backend/trademind, frontend/ or deploy/ can be overwritten. Docker files, virtual
# environments, caches, databases and secrets are not copied. A conflict report is generated
# afterwards. Compatible with Windows PowerShell 5.1 and PowerShell 7.
#
# Usage (from the repository root):
#   .\scripts\import_mvp.ps1 -Source "C:\path\to\TradeMind_AI_MVP_v2\trademind-ai-mvp"
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Destination = "",
    [switch]$Force,
    [switch]$SkipBranchCheck
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IntegrationBranch = "hoplite/vps-vercel-deploy--mvp-integration"
if (-not $Destination) { $Destination = Join-Path $Root "legacy\mvp" }

function Fail([string]$Message) { Write-Host "ERROR: $Message" -ForegroundColor Red; exit 1 }

# 1. Branch guard: never import onto main or the deployment branch.
if (-not $SkipBranchCheck) {
    $branch = (& git -C $Root rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne $IntegrationBranch) {
        Fail "Current branch is '$branch'. Run: git switch $IntegrationBranch"
    }
}

# 2. Locate the MVP root (tolerates an extra folder level from unzipping).
if (-not (Test-Path -LiteralPath $Source -PathType Container)) { Fail "Source folder not found: $Source" }
$Source = (Resolve-Path -LiteralPath $Source).Path
$nested = Join-Path $Source "trademind-ai-mvp"
if (-not (Test-Path (Join-Path $Source "backend")) -and (Test-Path (Join-Path $nested "backend"))) { $Source = $nested }
if (-not (Test-Path (Join-Path $Source "backend\app\main.py")) -and -not (Test-Path (Join-Path $Source "backend/app/main.py"))) {
    Write-Host "WARNING: backend\app\main.py not found under $Source; continuing with whatever is there." -ForegroundColor Yellow
}

# 3. Refuse to overwrite a previous import unless -Force.
if ((Test-Path -LiteralPath $Destination) -and (Get-ChildItem -LiteralPath $Destination -Force | Select-Object -First 1)) {
    if (-not $Force) { Fail "$Destination already contains files. Re-run with -Force to replace the previous import." }
    Remove-Item -LiteralPath $Destination -Recurse -Force
}

# 4. Select files. Excluded: tooling state, caches, local data, secrets, and Docker (not used in this project).
$excludedDirs = @(".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".idea", ".vscode", "htmlcov")
$excludedFilePatterns = @("*.pyc", "*.pyo", "*.db", "*.sqlite", "*.sqlite3", "*.log", "*.pem", "*.key", "*.pfx",
    "Dockerfile", "Dockerfile.*", "docker-compose*.yml", "docker-compose*.yaml", ".dockerignore", ".coverage")

$selected = New-Object System.Collections.Generic.List[object]
$skipped = New-Object System.Collections.Generic.List[string]
foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -File -Force) {
    $rel = $file.FullName.Substring($Source.Length).TrimStart('\', '/')
    $parts = $rel -split '[\\/]'
    $dirParts = $parts[0..($parts.Length - 2)]
    $reason = $null
    if ($parts.Length -gt 1 -and ($dirParts | Where-Object { $excludedDirs -contains $_ -or $_ -like "*.egg-info" })) { $reason = "directory" }
    elseif ($file.Name -like ".env*" -and $file.Name -ne ".env.example") { $reason = "secrets file" }
    else { foreach ($p in $excludedFilePatterns) { if ($file.Name -like $p) { $reason = "excluded type"; break } } }
    if ($reason) { $skipped.Add("$rel ($reason)") } else { $selected.Add([pscustomobject]@{ File = $file; Rel = $rel }) }
}
if ($selected.Count -eq 0) { Fail "No files selected from $Source" }

# 5. Secret scan before copying anything.
$secretPatterns = @(
    'sk-ant-[A-Za-z0-9_-]{10,}', 'sk-[A-Za-z0-9]{20,}', 'AIza[0-9A-Za-z_-]{30,}', 'ghp_[0-9A-Za-z]{30,}',
    '-----BEGIN [A-Z ]*PRIVATE KEY',
    '(?i)(api[_-]?key|api[_-]?secret|secret[_-]?key|password|passwd|private[_-]?key|access[_-]?token)\s*[:=]\s*["'']?[A-Za-z0-9/+_\-]{16,}'
)
$hits = New-Object System.Collections.Generic.List[string]
foreach ($s in $selected) {
    if ($s.File.Length -gt 2MB) { continue }
    $n = 0
    foreach ($line in [System.IO.File]::ReadAllLines($s.File.FullName)) {
        $n++
        foreach ($pat in $secretPatterns) {
            if ($line -match $pat -and $line -notmatch '(?i)(change[-_]?me|example|placeholder|your[-_]|xxx|<.*>)') {
                $hits.Add("$($s.Rel):$n"); break
            }
        }
    }
}
if ($hits.Count -gt 0) {
    Write-Host "Possible secrets found; nothing was copied. Remove or replace them in the MVP folder, then re-run:" -ForegroundColor Red
    $hits | ForEach-Object { Write-Host "  $_" }
    exit 1
}

# 6. Copy and write a manifest (relative paths and SHA-256 only; no absolute paths or user names).
foreach ($s in $selected) {
    $target = Join-Path $Destination $s.Rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $s.File.FullName -Destination $target
}
$manifest = New-Object System.Collections.Generic.List[string]
$manifest.Add("TradeMind MVP import manifest")
$manifest.Add("source_folder: $(Split-Path -Leaf $Source)")
$manifest.Add("imported_utc: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))")
$manifest.Add("files: $($selected.Count)")
$manifest.Add("")
$manifest.Add("[sha256]")
foreach ($s in ($selected | Sort-Object Rel)) {
    $h = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Destination $s.Rel)).Hash.ToLower()
    $manifest.Add("$h  $($s.Rel -replace '\\', '/')")
}
$manifest.Add("")
$manifest.Add("[not imported]")
foreach ($k in ($skipped | Sort-Object)) { $manifest.Add(($k -replace '\\', '/')) }
[System.IO.File]::WriteAllLines((Join-Path $Destination "IMPORT_MANIFEST.txt"), $manifest)

Write-Host "Imported $($selected.Count) files into $Destination ($($skipped.Count) skipped; see IMPORT_MANIFEST.txt)." -ForegroundColor Green

# 7. Conflict report.
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $Root ".venv/bin/python" }
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $Root "scripts/mvp_audit.py") $Destination --out (Join-Path $Root "docs/MVP_INTEGRATION_REPORT.md")
$auditExit = $LASTEXITCODE
if ($auditExit -eq 1) {
    Write-Host "The report lists BLOCKER findings (live trading or key handling). Commit anyway: they are fixed during porting and never deployed from legacy/." -ForegroundColor Yellow
} elseif ($auditExit -ne 0) {
    Fail "Conflict report failed (exit $auditExit)."
}

Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  git status            # only legacy/mvp/ and docs/MVP_INTEGRATION_REPORT.md should change"
Write-Host "  git add legacy/mvp docs/MVP_INTEGRATION_REPORT.md"
Write-Host "  git commit -m `"Import local MVP into legacy/mvp (quarantined, not wired in)`""
Write-Host "  git push origin $IntegrationBranch"
exit 0
