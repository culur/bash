#!/usr/bin/env bash

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
Usage: git out [COMMIT | NUMBER] [OPTIONS]

Arguments:
  COMMIT                  Commit hash, branch, or ref (e.g. HEAD~1, ~1, feat/abc, a1b2c3d)
  NUMBER                  Number of recent commits to display in interactive menu (e.g. 5, 20)

Options:
  -h, --help              Show this help message and exit
  -a, --all, --acc, --accumulation
                          Find all files changed from selected commit up to HEAD (accumulate changes)

Examples:
  git out                 Interactively select 1 commit from last 50
  git out 5               Interactively select 1 commit from last 5
  git out ~1              Pull files out of the commit HEAD~1
  git out HEAD~2          Pull files out of the commit HEAD~2
  git out feat/abc        Pull files out of the commit at branch feat/abc
  git out a1b2c3d         Pull files out of the commit hash a1b2c3d
  git out ~1 -a           Pull files out of ~1 and all subsequent commits up to HEAD
EOF
}

TARGET_COMMIT=""
MULTIPLE_MODE=0
INTERACTIVE_LIMIT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h | --help)
      show_help
      exit 0
      ;;
    -a | --all | --acc | --accumulation | -r | --range | -m | --multiple)
      MULTIPLE_MODE=1
      shift 1
      ;;
    *)
      arg="$1"
      # Expand shorthand ~N to HEAD~N
      if [[ "$arg" =~ ^~[0-9]+$ ]]; then
        arg="HEAD${arg}"
      fi

      if [[ -z "$TARGET_COMMIT" && -z "$INTERACTIVE_LIMIT" ]]; then
        ensure_git_exists
        ensure_inside_a_git_repository
        if [[ "$arg" =~ ^[0-9]+$ ]]; then
          INTERACTIVE_LIMIT="$arg"
        elif TARGET_COMMIT=$(git rev-parse --verify "${arg}^{commit}" 2> /dev/null); then
          : # Target commit resolved via positional argument
        else
          echo "Error: Invalid commit ref or number '${1}'." >&2
          show_help
          exit 1
        fi
      else
        echo "Error: Unexpected argument '${1}'." >&2
        show_help
        exit 1
      fi
      shift 1
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

if [[ -z "$TARGET_COMMIT" ]]; then
  LIMIT="${INTERACTIVE_LIMIT:-50}"
  commit_list=$(git log --oneline --max-count="$LIMIT")
  if [[ -z "$commit_list" ]]; then
    echo "Error: No commits found." >&2
    exit 1
  fi

  echo "Select a commit:"
  if ! selection=$(echo "$commit_list" | gum choose --limit=1); then
    echo "Info: no selection made. Nothing to do."
    exit 0
  fi

  if [[ -z "$selection" ]]; then
    echo "Info: no selection made. Nothing to do."
    exit 0
  fi

  TARGET_COMMIT_HASH=$(echo "$selection" | awk '{print $1}')
  TARGET_COMMIT=$(git rev-parse "$TARGET_COMMIT_HASH")
fi

if [[ -z "$TARGET_COMMIT" ]]; then
  echo "Error: You must specify a commit to pick out. See --help for options." >&2
  exit 1
fi

if ! git diff --cached --quiet; then
  echo "Error: Please unstage all files before running the script (only unstaged files or a clean working directory are allowed)." >&2
  exit 1
fi

echo "Selected commit: $TARGET_COMMIT"

if git rev-parse --verify "${TARGET_COMMIT}~1" > /dev/null 2>&1; then
  base_commit="${TARGET_COMMIT}~1"
  rebase_base="${base_commit}"
else
  # Empty tree hash for root commit
  base_commit="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
  rebase_base="--root"
fi

get_accumulated_changes() {
  local base=$1
  local end=$2

  git log --reverse --name-status --no-renames -m --format="" "${base}..${end}" \
    | grep -v '^$' \
    | awk -f "${script_dir}/git-out-accumulate-changes.awk" \
    | sort -k2
}

if [[ "${MULTIPLE_MODE}" -eq 1 ]]; then
  choices=$(get_accumulated_changes "${base_commit}" "HEAD")
else
  choices=$(get_accumulated_changes "${base_commit}" "${TARGET_COMMIT}")
fi

if [[ -z "${choices}" ]]; then
  echo "Info: no changed files found for the selected range."
  exit 0
fi

echo "Select file(s) to pick out:"
if ! selection=$(printf '%s\n' "${choices}" | gum filter --no-limit); then
  echo "Info: no selection made. Nothing to do."
  exit 0
fi

if [[ -z "$selection" ]]; then
  echo "Info: no selection made. Nothing to do."
  exit 0
fi

ESC=$'\033'
# Strip ANSI escape codes, carriage returns, and status prefix to get raw file names
selected_files_raw=$(printf '%s\n' "$selection" | tr -d '\r' | sed -E "s/${ESC}\[[0-9;]*[a-zA-Z]//g" | sed -E 's/^\[[^]]*\][[:space:]]*//')

# Calculate accumulated status from base to HEAD for final output
final_accumulated=$(get_accumulated_changes "${base_commit}" "HEAD")

echo "Selected files (with accumulated status up to HEAD):"
selected_files_array=()
while IFS= read -r file; do
  file=$(printf '%s' "$file" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  [ -z "$file" ] && continue
  selected_files_array+=("$file")
  line=$(echo "$final_accumulated" | awk -v f="$file" 'substr($0, index($0, " ") + 1) == f { print $0; exit }')
  if [[ -n "$line" ]]; then
    echo "$line"
  else
    echo "[?] $file"
  fi
done <<< "$selected_files_raw"

ORIGINAL_HEAD=$(git rev-parse HEAD)

# Snapshot current entire working tree to check integrity later
TEMP_INDEX=$(mktemp)
GIT_INDEX_FILE=$TEMP_INDEX git read-tree HEAD
GIT_INDEX_FILE=$TEMP_INDEX git add -A
ORIGINAL_WORKTREE_TREE=$(GIT_INDEX_FILE=$TEMP_INDEX git write-tree)
rm -f "$TEMP_INDEX"

echo ""
if ! gum confirm "Are you sure you want to pick out these files and rewrite the commit history?"; then
  echo "Operation canceled."
  exit 0
fi

has_unstaged=0
if ! git diff --quiet; then
  has_unstaged=1
  git stash push -q -u -m "git-out temp stash"
fi

echo "Starting rebase process..."
export GIT_SEQUENCE_EDITOR="sed -i.bak 's/^pick /edit /g'"
git rebase -i ${rebase_base} > /dev/null 2>&1 || true

if ! test -d "$(git rev-parse --git-path rebase-merge 2> /dev/null)"; then
  echo ""
  gum style --foreground 196 --bold "Error: Failed to start rebase process!"
  if [ "$has_unstaged" -eq 1 ]; then
    git stash apply -q > /dev/null 2>&1 || true
    git stash drop -q > /dev/null 2>&1 || true
  fi
  gum style --foreground 82 "Reverted to original state."
  exit 1
fi

commit_index=0
while test -d "$(git rev-parse --git-path rebase-merge 2> /dev/null)"; do
  current_hash=$(git rev-parse HEAD)
  current_msg=$(git log -1 --format=%s HEAD)

  echo "Processing commit #$commit_index - $current_hash: $current_msg"

  for file in "${selected_files_array[@]}"; do
    rm -rf "$file" 2> /dev/null || true
    if git cat-file -e "HEAD~1:${file}" 2> /dev/null; then
      git checkout HEAD~1 -- "$file" > /dev/null 2>&1 || true
      git add "$file" > /dev/null 2>&1 || true
    else
      git rm -rf --cached --ignore-unmatch "$file" > /dev/null 2>&1 || true
    fi
  done

  if git diff-index --cached --quiet HEAD~1; then
    if gum confirm "Commit #$commit_index - $current_hash: $current_msg has become empty. Do you want to drop this commit?"; then
      git reset --hard HEAD~1 > /dev/null
    else
      git commit --amend --allow-empty --no-edit > /dev/null
    fi
  else
    git commit --amend --no-edit > /dev/null
  fi

  git reset --hard > /dev/null

  while ! git rebase --continue > /dev/null 2>&1; do
    if ! test -d "$(git rev-parse --git-path rebase-merge 2> /dev/null)"; then
      break
    fi

    unmerged=$(git diff --name-only --diff-filter=U)
    if [ -z "$unmerged" ]; then
      break
    fi

    other_conflicts=0
    for uf in $unmerged; do
      is_selected=0
      for sf in "${selected_files_array[@]}"; do
        if [ "$uf" = "$sf" ]; then
          is_selected=1
          break
        fi
      done
      if [ "$is_selected" -eq 0 ]; then
        other_conflicts=1
        break
      fi
    done

    if [ "$other_conflicts" -eq 1 ]; then
      git rebase --abort > /dev/null 2>&1 || true
      if [ "$has_unstaged" -eq 1 ]; then
        git stash apply -q > /dev/null 2>&1 || true
        git stash drop -q > /dev/null 2>&1 || true
      fi
      echo ""
      gum style --foreground 196 --bold "Error: Conflict detected in non-selected files! Rebase aborted."
      gum style --foreground 82 "Reverted to original state."
      exit 1
    else
      for f in $unmerged; do
        rm -rf "$f" 2> /dev/null || true
        if git cat-file -e "HEAD:${f}" 2> /dev/null; then
          git checkout HEAD -- "$f" > /dev/null 2>&1 || true
          git add "$f" > /dev/null 2>&1 || true
        else
          git rm -rf --cached --ignore-unmatch "$f" > /dev/null 2>&1 || true
        fi
      done
    fi
  done

  commit_index=$((commit_index + 1))
done

echo "Restoring file states..."
for file in "${selected_files_array[@]}"; do
  rm -rf "$file" 2> /dev/null || true
  if git cat-file -e "${ORIGINAL_HEAD}:${file}" 2> /dev/null; then
    git restore --source="$ORIGINAL_HEAD" --staged --worktree -- "$file" > /dev/null 2>&1 || true
  else
    git rm -rf --cached --ignore-unmatch "$file" > /dev/null 2>&1 || true
  fi
done

if [ "$has_unstaged" -eq 1 ]; then
  git stash apply --index -q > /dev/null 2>&1 || git stash apply -q > /dev/null 2>&1 || true
fi

TEMP_INDEX=$(mktemp)
GIT_INDEX_FILE=$TEMP_INDEX git read-tree HEAD
GIT_INDEX_FILE=$TEMP_INDEX git add -A
FINAL_WORKTREE_TREE=$(GIT_INDEX_FILE=$TEMP_INDEX git write-tree)
rm -f "$TEMP_INDEX"

if [ "$ORIGINAL_WORKTREE_TREE" = "$FINAL_WORKTREE_TREE" ]; then
  if [ "$has_unstaged" -eq 1 ]; then
    git stash drop -q > /dev/null 2>&1 || true
  fi
  echo ""
  gum style --foreground 82 "Success! Commit history has been rewritten."
  echo "Picked-out files are now Staged. Original unstaged files remain Unstaged."
else
  echo ""
  gum style --foreground 196 --bold "Error: Final file states deviate from the original state!"
  echo "Deviating file states between original and rewritten worktree:"
  git diff-tree -r --name-status "$ORIGINAL_WORKTREE_TREE" "$FINAL_WORKTREE_TREE" | sed 's/^/  /'
  echo ""
  git reset --hard "$ORIGINAL_HEAD" > /dev/null
  if [ "$has_unstaged" -eq 1 ]; then
    git stash apply -q > /dev/null 2>&1 || true
    git stash drop -q > /dev/null 2>&1 || true
  fi
  gum style --foreground 82 "Reverted to original state."
  exit 1
fi
