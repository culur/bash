$bashCandidates = @(
    "$env:ProgramFiles\Git\bin\bash.exe",
    "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
)

$bash = $null
foreach ($candidate in $bashCandidates) {
    if (Test-Path $candidate) {
        $bash = $candidate
        break
    }
}

if (-not $bash) {
    $cmd = Get-Command sh, bash -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike "*System32*" } | Select-Object -First 1
    if ($cmd) {
        $bash = $cmd.Source
    }
}

if (-not $bash) {
    Write-Error "Git Bash or sh not found. Please install Git for Windows."
    exit 1
}

$scriptPath = Join-Path $PSScriptRoot "..\src\git-r.sh"
& $bash $scriptPath @args
exit $LASTEXITCODE
