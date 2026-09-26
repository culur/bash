$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
uv run "$ScriptDir\..\src\clean-git.py" @args
