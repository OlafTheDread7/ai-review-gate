<#
.SYNOPSIS
  Installs or updates the AI Review ship gate in one or more repos.

.DESCRIPTION
  Copies the gate's files from files\github\ (this kit) into each repo's .github\
  folder. The repo's own .github\ai-review\CONTEXT.md and surface.json are never
  touched unless you pass -Context or -Surface. Runs no git commands: you commit
  and push each repo yourself.

  Without -Go it only shows what would change. With -Go it writes.

.EXAMPLE
  .\Install-AIReview.ps1 -Repo C:\code\my-site
  .\Install-AIReview.ps1 -Repo C:\code\my-site -Go

.EXAMPLE
  # Every repo under a folder that already has the gate, to roll out a new version
  .\Install-AIReview.ps1 -All -Root C:\code
  .\Install-AIReview.ps1 -All -Root C:\code -Go
  .\Install-AIReview.ps1 -All -Root C:\code -Exclude old-app,legacy-api -Go

.EXAMPLE
  # A new repo, with its reviewer notes and settings
  .\Install-AIReview.ps1 -Repo C:\code\new-app -Context .\notes\CONTEXT.md -Surface .\notes\surface.json -Go
#>
[CmdletBinding()]
param(
  [string[]]$Repo,
  [switch]$All,
  [string]$Root,
  [string[]]$Exclude = @(),
  [string]$Context,
  [string]$Surface,
  [switch]$Go
)

$ErrorActionPreference = 'Stop'
if (($Context -or $Surface) -and ($All -or $Repo.Count -ne 1)) { throw '-Context and -Surface work with exactly one -Repo.' }
if ($All -and -not $Root) { throw '-All needs -Root <folder that holds your repos>.' }
foreach ($f in @($Context, $Surface)) { if ($f -and -not (Test-Path $f)) { throw "Not found: $f" } }
$kitFiles = Join-Path $PSScriptRoot 'files\github'
if (-not (Test-Path $kitFiles)) { throw "Kit files not found at $kitFiles" }

# The files this kit owns, relative to .github\
$owned = @(
  'workflows\ai-review.yml',
  'ai-review\prepare.sh',
  'ai-review\checks.py',
  'ai-review\enforce.py',
  'ai-review\gitleaks.toml',
  'ai-review\REVIEW.md'
)

if ($All) {
  $Repo = Get-ChildItem -Path $Root -Directory -Recurse -Depth 4 -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq '.github' -and (Test-Path (Join-Path $_.FullName 'workflows\ai-review.yml')) } |
    ForEach-Object { $_.Parent.FullName } |
    Where-Object { $_ -notmatch '[\\/](_archive|node_modules)[\\/]' } |
    Sort-Object -Unique
}
if ($Exclude.Count -gt 0) {
  $Repo = @($Repo | Where-Object { $r = $_; -not ($Exclude | Where-Object { (Split-Path $r -Leaf) -ieq $_ }) })
  Write-Host ("Leaving out: " + ($Exclude -join ', ')) -ForegroundColor Yellow
}
if (-not $Repo -or $Repo.Count -eq 0) { throw 'Give -Repo <path> (one or more) or -All -Root <folder>.' }

$mode = if ($Go) { 'WRITING' } else { 'PREVIEW (add -Go to write)' }
Write-Host "AI Review kit -> $($Repo.Count) repo(s). $mode" -ForegroundColor Cyan

$totalChanged = 0
foreach ($r in $Repo) {
  $r = (Resolve-Path $r).Path
  if (-not (Test-Path (Join-Path $r '.git'))) { Write-Host "SKIP $r (not a git repo; run git init first)" -ForegroundColor Yellow; continue }
  $changes = @()
  foreach ($rel in $owned) {
    $src = Join-Path $kitFiles $rel
    $dst = Join-Path (Join-Path $r '.github') $rel
    if (-not (Test-Path $dst)) { $changes += [pscustomobject]@{ File = ".github\$rel"; State = 'new' }; continue }
    $a = (Get-FileHash $src -Algorithm SHA256).Hash
    $b = (Get-FileHash $dst -Algorithm SHA256).Hash
    if ($a -ne $b) { $changes += [pscustomobject]@{ File = ".github\$rel"; State = 'updated' } }
  }
  # Per-repo files, installed only when given
  $extras = @()
  if ($Context) { $extras += [pscustomobject]@{ Src = $Context; File = '.github\ai-review\CONTEXT.md' } }
  if ($Surface) { $extras += [pscustomobject]@{ Src = $Surface; File = '.github\ai-review\surface.json' } }
  foreach ($x in $extras) {
    $dst = Join-Path $r $x.File
    $state = if (-not (Test-Path $dst)) { 'new' } elseif ((Get-FileHash $x.Src).Hash -ne (Get-FileHash $dst).Hash) { 'updated' } else { $null }
    if ($state) { $changes += [pscustomobject]@{ File = $x.File; State = $state; Src = $x.Src } }
  }
  if ($changes.Count -eq 0) { Write-Host "OK   $r (already current)" -ForegroundColor Green; continue }
  $totalChanged++
  Write-Host "$(if ($Go) {'DONE'} else {'WILL'}) $r" -ForegroundColor $(if ($Go) {'Green'} else {'White'})
  foreach ($c in $changes) {
    Write-Host ("       {0,-8} {1}" -f $c.State, $c.File)
    if ($Go) {
      $src = if ($c.PSObject.Properties['Src'] -and $c.Src) { $c.Src } else { Join-Path $kitFiles ($c.File -replace '^\.github\\', '') }
      $dst = Join-Path $r $c.File
      New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
      Copy-Item -LiteralPath $src -Destination $dst -Force
    }
  }
  $hasContext = Test-Path (Join-Path $r '.github\ai-review\CONTEXT.md')
  if (-not $hasContext) { Write-Host '       note     no .github\ai-review\CONTEXT.md yet (the reviewer works without one, but better with it)' -ForegroundColor Yellow }
}

if ($totalChanged -gt 0) {
  if ($Go) {
    Write-Host "`nWritten. Commit and push each repo listed above (git add the .github files named under it)." -ForegroundColor Cyan
  } else {
    Write-Host "`nNothing written. Run again with -Go to install." -ForegroundColor Cyan
  }
}
