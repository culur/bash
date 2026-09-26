$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "..\src\git\git-acc.py"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run "$ScriptPath" @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python "$ScriptPath" @args
} else {
    Write-Error "Neither uv nor python was found on your system."
    exit 1
}
exit $LASTEXITCODE
