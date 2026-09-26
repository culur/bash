#!/usr/bin/env bash

# Ensure git exists
ensure_git_exists() {
  if ! command -v git > /dev/null 2>&1; then
    echo "Error: git is not installed." >&2
    exit 1
  fi
}

# Ensure gum exists
ensure_gum_exists() {
  if ! command -v gum > /dev/null 2>&1; then
    echo "Error: gum is not installed. Install from https://github.com/charmbracelet/gum" >&2
    exit 1
  fi
}

# Ensure inside a git repository
ensure_inside_a_git_repository() {
  if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "Error: not inside a Git repository." >&2
    exit 1
  fi
}

# Ensure there is at least one commit
ensure_at_least_one_commit() {
  if ! git rev-parse --verify HEAD > /dev/null 2>&1; then
    echo "Error: repository has no commits yet." >&2
    exit 1
  fi
}

# Ensure no sequential operation (rebase, merge, cherry-pick, etc.) is in progress.
ensure_no_git_operation_in_progress() {
  local git_dir
  git_dir="$(git rev-parse --git-dir)"
  if [ -d "${git_dir}/sequencer" ] \
    || [ -d "${git_dir}/rebase-apply" ] \
    || [ -d "${git_dir}/rebase-merge" ] \
    || [ -f "${git_dir}/MERGE_HEAD" ]; then
    echo "Error: A git operation (rebase, merge, cherry-pick, etc.) is already in progress." >&2
    echo "Please resolve it before running this script." >&2
    exit 1
  fi
}

# Ensure not in a detached HEAD state.
ensure_not_detached_head() {
  if [ "$(git rev-parse --abbrev-ref HEAD)" = "HEAD" ]; then
    echo "Error: Detached HEAD is not supported. Please checkout a named branch first." >&2
    exit 1
  fi
}
