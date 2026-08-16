#!/usr/bin/env bash
# git-fixup: stage changes for one file, create "fixup!" commit against a chosen commit,
# then autosquash via interactive rebase with autostash.

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
##! Load scripts - End

ensure_git_exists
ensure_gum_exists
ensure_inside_a_git_repository
ensure_at_least_one_commit
ensure_no_git_operation_in_progress
ensure_not_detached_head

show_help() {
  cat << EOF
Usage: git fixup [NUMBER] [OPTIONS]

Options:
  -h, --help              Show this help message and exit

Examples:
  git fixup               Fix up staged files (or choose modified files interactively if none staged)
  git fixup 15            Search the last 15 commits from the entire history
EOF
}

commit_count_arg=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h | --help)
      show_help
      exit 0
      ;;
    -n | -c | --count | --number)
      if [[ -z "${2:-}" || ! "$2" =~ ^[0-9]+$ ]]; then
        echo "Error: -n/--count requires a numeric argument." >&2
        exit 1
      fi
      commit_count_arg="$2"
      shift 2
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ && -z "$commit_count_arg" ]]; then
        commit_count_arg="$1"
        shift 1
      else
        echo "Unknown option: $1" >&2
        show_help
        exit 1
      fi
      ;;
  esac
done

# Ensure running from repo root for consistent paths
cd "$(git rev-parse --show-toplevel)"

original_branch="$(git rev-parse --abbrev-ref HEAD)"

# Check for staged files first; if present, automatically select them.
mapfile -t staged_files < <(git diff --name-only --cached)

use_staged=false
if [ "${#staged_files[@]}" -gt 0 ]; then
  use_staged=true
  selected_files=("${staged_files[@]}")
  echo "Staged file(s) detected and automatically selected:"
  printf '  %s\n' "${selected_files[@]}"
else
  # If no staged files exist, list modified and untracked files for selection.
  modified_files="$(
    {
      git diff --name-only
      git ls-files --others --exclude-standard
    } | sort -u
  )"

  if [ -z "${modified_files}" ]; then
    echo "No modified or staged files found." >&2
    exit 0
  fi

  # Choose file(s) to fix up
  mapfile -t selected_files < <(
    printf "%s\n" "${modified_files}" \
      | sed '/^$/d' \
      | gum choose --no-limit --header "Choose file(s) to fix up"
  )

  ESC=$'\033'
  cleaned_files=()
  for f in "${selected_files[@]}"; do
    f_clean=$(printf '%s' "$f" | tr -d '\r' | sed -E "s/${ESC}\[[0-9;]*[a-zA-Z]//g" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -n "$f_clean" ] && cleaned_files+=("$f_clean")
  done
  selected_files=("${cleaned_files[@]}")

  if [ "${#selected_files[@]}" -eq 0 ]; then
    echo "No files selected." >&2
    exit 1
  fi
fi

ESC=$'\033'
selected_display="$(
  printf "%s\n" "${selected_files[@]}" | paste -sd ", " -
)"

commit_line=""
##! Use -c <number> when a specific number of commits should be considered
if [ -n "${commit_count_arg}" ]; then
  # Show N recent commits from the entire history
  commit_count="${commit_count_arg}"
  echo "Searching last ${commit_count} commits, checking relation to ${selected_display}..."

  # Pipe the commit processing logic directly into gum choose.
  # This avoids creating an intermediate string variable and potential quoting issues.
  commit_line="$(
    git log \
      --no-merges \
      -n "${commit_count}" \
      --date=short \
      --pretty=format:"%H %h %ad %s" \
      | {
        while IFS= read -r log_line; do
          full_hash=$(printf "%s" "${log_line}" | awk '{print $1}')
          short_hash=$(printf "%s" "${log_line}" | awk '{print $2}')
          display_line=$(printf "%s" "${log_line}" | cut -d' ' -f3-)

          # Get file status (A, M, D, R, etc.) for the chosen file in this commit.
          # We check against the parent commit.
          file_status=$(
            git diff-tree --no-commit-id --name-status -r --root "${full_hash}" -- "${selected_files[@]}" 2> /dev/null \
              | awk '{print $1}' | sort -u | paste -sd "," -
          )

          # Format the line for gum: [M] hash date subject
          if [ -n "${file_status}" ]; then
            printf "%s [%s] %s\n" "${short_hash}" "${file_status}" "${display_line}"
          else
            printf "%s %s\n" "${short_hash}" "${display_line}"
          fi
        done
      } | gum choose --header "Choose the commit to fix up"
  )"
else
  # Show last 10 commits that touched the selected file
  commit_count=10
  echo "Searching for the last ${commit_count} commits related to ${selected_display}..."
  if [ "${#selected_files[@]}" -eq 1 ]; then
    commit_line="$(
      git log \
        --follow \
        --no-merges \
        -n "${commit_count}" \
        --date=short \
        --pretty=format:"%h %ad %s" \
        -- "${selected_files[0]}" \
        | gum choose --header "Choose the commit to fix up"
    )"
  else
    commit_line="$(
      git log \
        --no-merges \
        -n "${commit_count}" \
        --date=short \
        --pretty=format:"%h %ad %s" \
        -- "${selected_files[@]}" \
        | gum choose --header "Choose the commit to fix up"
    )"
  fi
fi

if [ -z "${commit_line}" ]; then
  echo "No commit selected." >&2
  exit 1
fi

commit_hash="$(printf "%s" "${commit_line}" | tr -d '\r' | sed -E "s/${ESC}\[[0-9;]*[a-zA-Z]//g" | awk '{print $1}')"
# commit_subject="$(git show -s --format=%s "${commit_hash}")"

if ! "${use_staged}"; then
  # Stage files when -s is not used
  git add -- "${selected_files[@]}"
fi

# Create the fixup commit
git commit --fixup "${commit_hash}"

backup_commit_created=false
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add .
  git commit -m "chore: backup"
  backup_commit_created=true
fi

# Create a temporary backup branch pointing to the pre-rewrite tip
backup_branch="fixup-backup/$(date +%Y%m%d-%H%M%S)"
git branch "${backup_branch}" > /dev/null 2>&1 || {
  echo "Failed to create backup branch ${backup_branch}." >&2
  exit 1
}
echo "Created backup branch ${backup_branch} at $(git rev-parse --short HEAD)."

# Determine rebase base: parent of target or --root if target is the root
if git rev-parse -q --verify "${commit_hash}^" > /dev/null 2>&1; then
  base_ref="${commit_hash}^"
else
  base_ref="--root"
fi

# Run interactive rebase with autosquash and autostash. Avoid opening editor.
if ! GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash --autostash "${base_ref}"; then
  echo ""
  gum style --foreground 196 --bold "Error: Interactive rebase failed or encountered conflicts!"
  echo "Your backup branch is preserved at: ${backup_branch}"
  echo "To abort the rebase and return to original state, run:"
  echo "  git rebase --abort"
  echo "  git reset --hard ${backup_branch}"
  exit 1
fi

echo "Rebase completed on branch ${original_branch}."

if [ "${backup_commit_created}" = true ]; then
  git reset --soft HEAD~1
  git restore --staged .
fi

# Offer to delete the backup branch
if gum confirm "Delete temporary backup branch '${backup_branch}' now?"; then
  if git branch -D "${backup_branch}" > /dev/null 2>&1; then
    echo "Deleted temporary branch ${backup_branch}."
  else
    echo "Failed to delete temporary branch ${backup_branch}." >&2
    exit 1
  fi
else
  echo "To delete the temporary branch later, run:"
  echo "  git branch -D ${backup_branch}"
fi

echo "All done. You remain on ${original_branch}."
