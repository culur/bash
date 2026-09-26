#!/usr/bin/env bash
# git-acc.sh: Cross-platform runner for git-acc.py

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
script_dir="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"
py_script="${script_dir}/git-acc.py"

if command -v uv >/dev/null 2>&1; then
  exec uv run "$py_script" "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 "$py_script" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$py_script" "$@"
else
  echo "Error: Neither uv nor python was found on your system." >&2
  exit 1
fi
