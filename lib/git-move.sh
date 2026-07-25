#!/usr/bin/env bash
# git-move: Interactively select and move one or multiple commits after a target commit in history.

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
script_dir="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"

# shellcheck disable=SC1091
source "${script_dir}/preconditions.sh"

ensure_git_exists
ensure_gum_exists
ensure_inside_a_git_repository
ensure_at_least_one_commit
ensure_no_git_operation_in_progress
ensure_not_detached_head

cd "$(git rev-parse --show-toplevel)"

show_help() {
  cat << EOF
Usage: git move [NUMBER] [OPTIONS]

Arguments:
  NUMBER                  Number of recent commits to display in interactive menu (default: 50)

Options:
  -h, --help              Show this help message and exit

Examples:
  git move                Interactively select commit(s) from last 50 to move
  git move 15             Interactively select commit(s) from last 15 to move
EOF
}

LIMIT=50

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h | --help)
      show_help
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        LIMIT="$1"
        shift 1
      else
        echo "Error: Unexpected argument '${1}'." >&2
        show_help
        exit 1
      fi
      ;;
  esac
done

ensure_git_exists
ensure_gum_exists
ensure_inside_a_git_repository
ensure_at_least_one_commit
ensure_no_git_operation_in_progress
ensure_not_detached_head

cd "$(git rev-parse --show-toplevel)"

ORIGINAL_HEAD=$(git rev-parse HEAD)

# Snapshot current entire working tree to check integrity later
TEMP_INDEX=$(mktemp)
GIT_INDEX_FILE=$TEMP_INDEX git read-tree HEAD
GIT_INDEX_FILE=$TEMP_INDEX git add -A
ORIGINAL_WORKTREE_TREE=$(GIT_INDEX_FILE=$TEMP_INDEX git write-tree)
rm -f "$TEMP_INDEX"

has_working_changes=0
if [ -n "$(git status --porcelain)" ]; then
  has_working_changes=1
  git stash push -u -q -m "git-move temp stash"
fi

restore_working_files() {
  if [ "$has_working_changes" -eq 1 ]; then
    git stash apply --index -q > /dev/null 2>&1 || git stash apply -q > /dev/null 2>&1 || true
    git stash drop -q > /dev/null 2>&1 || true
    has_working_changes=0
  fi
}

commit_list=$(git log --oneline --max-count="$LIMIT")
if [[ -z "$commit_list" ]]; then
  echo "Error: No commits found." >&2
  restore_working_files
  exit 1
fi

echo "Select commit(s) to move (Tab/Space to select, Enter to confirm):"
if ! selection=$(echo "$commit_list" | gum choose --no-limit); then
  echo "Info: no selection made. Nothing to do."
  restore_working_files
  exit 0
fi

if [[ -z "$selection" ]]; then
  echo "Info: no selection made. Nothing to do."
  restore_working_files
  exit 0
fi

selected_hashes=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  short_h=$(echo "$line" | awk '{print $1}')
  full_h=$(git rev-parse "$short_h")
  selected_hashes+=("$full_h")
done <<< "$selection"

# Get selected commits in chronological order (oldest first)
mapfile -t ordered_selected_hashes < <(git log --no-walk --topo-order --reverse --format="%H" "${selected_hashes[@]}")

echo ""
echo "Accumulated changes from selected commit(s):"
{
  for h in "${ordered_selected_hashes[@]}"; do
    git diff-tree --no-commit-id --name-status -r --no-renames "$h"
  done
} | awk -f "${script_dir}/git-out-accumulate-changes.awk" | sort -k2
echo ""

# Build list of candidate target commits (LIMIT commits minus selected commits)
target_candidates=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  short_h=$(echo "$line" | awk '{print $1}')
  full_h=$(git rev-parse "$short_h")
  is_selected=0
  for sel_h in "${selected_hashes[@]}"; do
    if [ "$full_h" = "$sel_h" ]; then
      is_selected=1
      break
    fi
  done
  if [ "$is_selected" -eq 0 ]; then
    if [ -z "$target_candidates" ]; then
      target_candidates="$line"
    else
      target_candidates="${target_candidates}
$line"
    fi
  fi
done <<< "$commit_list"

if [ -z "$target_candidates" ]; then
  echo "Error: No candidate target commit available." >&2
  restore_working_files
  exit 1
fi

echo "Select target commit (selected commit(s) will be placed above / after this commit in history):"
if ! target_selection=$(echo "$target_candidates" | gum choose --limit=1); then
  echo "Info: no target selection made. Nothing to do."
  restore_working_files
  exit 0
fi

if [[ -z "$target_selection" ]]; then
  echo "Info: no target selection made. Nothing to do."
  restore_working_files
  exit 0
fi

target_short=$(echo "$target_selection" | awk '{print $1}')
target_hash=$(git rev-parse "$target_short")

# Find the oldest commit among all involved (selected + target)
all_involved_hashes=("${selected_hashes[@]}" "$target_hash")
oldest_involved_hash=$(git log --no-walk --topo-order --reverse --format="%H" "${all_involved_hashes[@]}" | head -n 1)

if git rev-parse --verify "${oldest_involved_hash}~1" > /dev/null 2>&1; then
  rebase_base="${oldest_involved_hash}~1"
else
  rebase_base="--root"
fi

echo "Starting rebase to move commit(s)..."

export PYTHON_SCRIPT=$(cat << 'PYEOF'
import sys, subprocess

selected_hashes = sys.argv[1].split()
target_hash = sys.argv[2].strip()
todo_file = sys.argv[3]

def get_full_hash(short_hash):
    try:
        res = subprocess.run(["git", "rev-parse", short_hash], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return short_hash

with open(todo_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

pick_lines = {}
other_lines = []
non_selected_picks = []

for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        other_lines.append(line)
        continue
    parts = stripped.split()
    action = parts[0]
    if action in ("pick", "p", "edit", "e", "reword", "r", "squash", "s", "fixup", "f"):
        commit_ref = parts[1]
        full_h = get_full_hash(commit_ref)
        pick_lines[full_h] = line
        if full_h not in selected_hashes:
            non_selected_picks.append(full_h)
    else:
        other_lines.append(line)

new_lines = []
target_inserted = False

for h in non_selected_picks:
    new_lines.append(pick_lines[h])
    if h == target_hash:
        target_inserted = True
        for sel_h in selected_hashes:
            if sel_h in pick_lines:
                new_lines.append(pick_lines[sel_h])

if not target_inserted:
    for sel_h in selected_hashes:
        if sel_h in pick_lines:
            new_lines.append(pick_lines[sel_h])

new_lines.extend(other_lines)

with open(todo_file, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
PYEOF
)

export GIT_SEQUENCE_EDITOR="python3 -c \"\$PYTHON_SCRIPT\" \"${ordered_selected_hashes[*]}\" \"$target_hash\""

if ! git rebase -i "${rebase_base}" > /dev/null 2>&1; then
  git rebase --abort > /dev/null 2>&1 || true
  echo ""
  gum style --foreground 196 --bold "Error: Conflict detected during rebase! Rebase aborted."
  restore_working_files
  gum style --foreground 82 "Reverted to original state (staged and unstaged files preserved)."
  exit 1
fi

restore_working_files

TEMP_INDEX=$(mktemp)
GIT_INDEX_FILE=$TEMP_INDEX git read-tree HEAD
GIT_INDEX_FILE=$TEMP_INDEX git add -A
FINAL_WORKTREE_TREE=$(GIT_INDEX_FILE=$TEMP_INDEX git write-tree)
rm -f "$TEMP_INDEX"

if [ "$ORIGINAL_WORKTREE_TREE" = "$FINAL_WORKTREE_TREE" ]; then
  echo ""
  gum style --foreground 82 "Success! Selected commit(s) moved successfully."
else
  echo ""
  gum style --foreground 196 --bold "Error: Final file states deviate from the original state!"
  git reset --hard "$ORIGINAL_HEAD" > /dev/null
  restore_working_files
  gum style --foreground 82 "Reverted to original state."
  exit 1
fi
