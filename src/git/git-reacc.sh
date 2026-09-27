#!/usr/bin/env bash
# git-reacc: Interactively rewrite committer (and optionally author) identity for a range of commits.
# Preserves author timestamp, safeguards working tree (staged & unstaged changes), and rolls back on failure.

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

show_help() {
  cat << EOF
Usage: git reacc [NUMBER] [OPTIONS]

Rewrite committer (and optionally author) identity for a range of commits up to HEAD.

Arguments:
  NUMBER                  Number of recent commits to display in interactive menu (default: 30)

Options:
  -n, -c, --count NUMBER  Specify number of recent commits to display
  -h, --help              Show this help message and exit

Examples:
  git reacc               Choose from the last 30 commits to rewrite up to HEAD
  git reacc 10            Choose from the last 10 commits to rewrite up to HEAD
EOF
}

LIMIT=30

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
      LIMIT="$2"
      shift 2
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

gum style \
  --border rounded \
  --margin "1 0" \
  --padding "0 2" \
  --border-foreground 212 \
  --foreground 212 \
  --bold \
  "🔄 git reacc — Interactive Git Commit Identity Rewriter"

original_head="$(git rev-parse HEAD)"
original_branch="$(git rev-parse --abbrev-ref HEAD)"
original_tree="$(git rev-parse HEAD^{tree})"

# Working tree state handling
has_working_changes=false
if [ -n "$(git status --porcelain)" ]; then
  has_working_changes=true
  gum style --foreground 33 "📦 Stashing uncommitted working tree changes (staged, unstaged, untracked)..."
  git stash push --include-untracked -q -m "git-reacc temp stash: $(date +%Y%m%d-%H%M%S)"
fi

had_working_changes="$has_working_changes"

restore_working_tree() {
  if [ "$has_working_changes" = true ]; then
    echo "Restoring working tree changes (staged and unstaged)..."
    if ! git stash apply --index -q > /dev/null 2>&1; then
      git stash apply -q > /dev/null 2>&1 || true
    fi
    git stash drop -q > /dev/null 2>&1 || true
    has_working_changes=false
  fi
}

cleanup_on_failure() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    echo ""
    gum style --foreground 196 --bold "Operation interrupted or failed! Rolling back..." >&2
    git rebase --abort > /dev/null 2>&1 || true
    git reset --hard "$original_head" > /dev/null 2>&1 || true
    restore_working_tree
    gum style --foreground 82 "Successfully restored original state. No changes were lost."
  fi
}
trap cleanup_on_failure EXIT INT TERM

# Step 1: Load accounts from configs/git-accounts.json (git-acc)
gum style --foreground 99 --bold "👤 Step 1: Select Git Identity (from git-acc)"

accounts_file="${script_dir}/../../configs/git-accounts.json"
py_cmd=""
if command -v python3 > /dev/null 2>&1; then
  py_cmd="python3"
elif command -v uv > /dev/null 2>&1; then
  py_cmd="uv run python"
elif command -v python > /dev/null 2>&1; then
  py_cmd="python"
fi

accounts_list=""
if [ -n "$py_cmd" ] && [ -f "$accounts_file" ]; then
  accounts_list=$($py_cmd -c '
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
        for acc in data:
            name = str(acc.get("name", "")).strip()
            email = str(acc.get("email", "")).strip()
            if name and email:
                print(f"{name} <{email}>")
except Exception:
    pass
' "$accounts_file" 2>/dev/null || true)
fi

choices=()
if [ -n "$accounts_list" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && choices+=("$line")
  done <<< "$accounts_list"
fi

curr_name="$(git config user.name 2>/dev/null || true)"
curr_email="$(git config user.email 2>/dev/null || true)"
if [ -n "$curr_name" ] && [ -n "$curr_email" ]; then
  curr_id="$curr_name <$curr_email> (current git config)"
  is_dup=false
  for c in "${choices[@]}"; do
    if [[ "$c" == "$curr_name <$curr_email>"* ]]; then
      is_dup=true
      break
    fi
  done
  if [ "$is_dup" = false ]; then
    choices+=("$curr_id")
  fi
fi

choices+=("+ [Custom identity / Enter manually]")

if ! account_choice="$(printf '%s\n' "${choices[@]}" | gum choose --header "Select Git identity to apply (from git-acc):")"; then
  echo "Info: No identity selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

if [ -z "$account_choice" ]; then
  echo "Info: No identity selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

if [[ "$account_choice" == *"[Custom identity"* ]]; then
  chosen_name="$(gum input --header "Enter author/committer Name:" --placeholder "e.g. John Doe")"
  if [ -z "$chosen_name" ]; then
    echo "Error: Name cannot be empty." >&2
    exit 1
  fi
  chosen_email="$(gum input --header "Enter author/committer Email:" --placeholder "e.g. john@example.com")"
  if [ -z "$chosen_email" ]; then
    echo "Error: Email cannot be empty." >&2
    exit 1
  fi
else
  clean_choice="$(printf '%s' "$account_choice" | sed -e 's/ (current git config)$//')"
  chosen_name="${clean_choice% <*}"
  chosen_email="${clean_choice##*<}"
  chosen_email="${chosen_email%>}"
fi

# Step 2: Choose rewrite scope
echo ""
gum style --foreground 99 --bold "⚙️  Step 2: Select Rewrite Scope"

if ! scope_choice="$(gum choose --header "Select rewrite scope:" \
  "1. 👤 Committer only  (Keep original author & author timestamp intact)" \
  "2. 👥 Both Author & Committer  (Override author and committer, keep author timestamp)"
)"; then
  echo "Info: No scope selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

if [ -z "$scope_choice" ]; then
  echo "Info: No scope selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

if [[ "$scope_choice" == 1* ]]; then
  rewrite_scope="committer"
  scope_desc="Committer only (Author & Author timestamp preserved)"
else
  rewrite_scope="both"
  scope_desc="Both Author & Committer (Author timestamp preserved)"
fi

# Step 3: Load recent commits with Color-coded Columns
echo ""
gum style --foreground 99 --bold "📍 Step 3: Choose target commit to rewrite from"

commit_list="$(
  git log \
    --date=short \
    --pretty=format:"%h%x1f%ad%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s" \
    -n "$LIMIT" \
    | awk -F'\x1f' '
      BEGIN {
        CYAN = "\033[1;36m"
        DIM = "\033[90m"
        YELLOW = "\033[38;5;220m"
        GREEN = "\033[38;5;82m"
        WHITE = "\033[1;37m"
        RESET = "\033[0m"
      }
      {
        h[NR] = $1
        d[NR] = $2
        a_plain[NR] = ($4 != "") ? sprintf("[A: %s <%s>]", $3, $4) : sprintf("[A: %s]", $3)
        c_plain[NR] = ($6 != "") ? sprintf("[C: %s <%s>]", $5, $6) : sprintf("[C: %s]", $5)
        s[NR] = $7

        if (length(a_plain[NR]) > max_a) max_a = length(a_plain[NR])
        if (length(c_plain[NR]) > max_c) max_c = length(c_plain[NR])
      }
      END {
        for (i = 1; i <= NR; i++) {
          a_padded = sprintf("%-" max_a "s", a_plain[i])
          c_padded = sprintf("%-" max_c "s", c_plain[i])

          h_col = CYAN h[i] RESET
          d_col = DIM d[i] RESET
          a_col = YELLOW a_padded RESET
          c_col = GREEN c_padded RESET
          s_col = WHITE s[i] RESET

          printf "%s  %s  %s  %s  %s\n", h_col, d_col, a_col, c_col, s_col
        }
      }
    '
)"
if [ -z "$commit_list" ]; then
  echo "Error: No commits found." >&2
  exit 1
fi

if ! selected_commit_line="$(echo "$commit_list" | gum choose --header "Select the oldest commit to rewrite from (A = Author, C = Committer):")"; then
  echo "Info: No commit selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

if [ -z "$selected_commit_line" ]; then
  echo "Info: No commit selected. Nothing to do."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

ESC=$'\033'
selected_commit_plain="$(printf '%s' "$selected_commit_line" | tr -d '\r' | sed -E "s/${ESC}\[[0-9;]*[a-zA-Z]//g")"
target_short="$(echo "$selected_commit_plain" | awk '{print $1}')"
target_hash="$(git rev-parse "$target_short")"
target_subject="$(git log -1 --format=%s "$target_hash")"

if git rev-parse -q --verify "${target_hash}^" > /dev/null 2>&1; then
  base_ref="${target_hash}^"
  commit_count="$(git rev-list --count "${base_ref}..HEAD")"
else
  base_ref="--root"
  commit_count="$(git rev-list --count "HEAD")"
fi

# Step 4: Summary Card & Confirmation
summary_card="$(cat << EOF
🎯 Target Identity:  $chosen_name <$chosen_email>
⚙️  Rewrite Scope:    $scope_desc
📍 Starting Commit:  $target_short ($target_subject)
📦 Commit Range:     $commit_count commit(s) up to HEAD
EOF
)"

echo ""
gum style \
  --border rounded \
  --margin "0 1" \
  --padding "1 2" \
  --border-foreground 39 \
  "$summary_card"
echo ""

if ! gum confirm --affirmative="🚀 Rewrite now" --negative="❌ Cancel" "Proceed with rewriting $commit_count commit(s)?"; then
  gum style --foreground 244 "Operation canceled by user. No changes were made."
  restore_working_tree
  trap - EXIT INT TERM
  exit 0
fi

# Step 5: Execute interactive rebase with exec
rebase_extra_args=()
merge_count="$(git rev-list --merges --count "${base_ref}..HEAD" 2>/dev/null || echo 0)"
if [ "$merge_count" -gt 0 ]; then
  rebase_extra_args+=("--rebase-merges")
fi

safe_name="${chosen_name//\'/\'\\\'\'}"
safe_email="${chosen_email//\'/\'\\\'\'}"

export GIT_COMMITTER_NAME="$chosen_name"
export GIT_COMMITTER_EMAIL="$chosen_email"

if [ "$rewrite_scope" = "committer" ]; then
  exec_cmd="GIT_COMMITTER_NAME='$safe_name' GIT_COMMITTER_EMAIL='$safe_email' git commit --amend --no-edit"
else
  export GIT_AUTHOR_NAME="$chosen_name"
  export GIT_AUTHOR_EMAIL="$chosen_email"
  exec_cmd="GIT_COMMITTER_NAME='$safe_name' GIT_COMMITTER_EMAIL='$safe_email' git commit --amend --no-edit --author='$safe_name <$safe_email>'"
fi

echo ""
gum style --foreground 39 --bold "⏳ Rebasing and updating $commit_count commit(s)..."
GIT_SEQUENCE_EDITOR=: git rebase -i "${rebase_extra_args[@]}" "${base_ref}" --exec "${exec_cmd}"

# Step 6: Integrity verification & Restoration
final_tree="$(git rev-parse HEAD^{tree})"
if [ "$original_tree" != "$final_tree" ]; then
  echo ""
  gum style --foreground 196 --bold "Error: Final tree hash does not match original tree hash!" >&2
  exit 1
fi

trap - EXIT INT TERM

restore_working_tree

echo ""
success_card="$(cat << EOF
✔ Successfully rewritten $commit_count commit(s) on branch $original_branch!

  👤 Identity: $chosen_name <$chosen_email>
  ⚙️  Scope:    $scope_desc
EOF
)"

gum style \
  --border rounded \
  --margin "0 1" \
  --padding "1 2" \
  --border-foreground 82 \
  --foreground 82 \
  --bold \
  "$success_card"

if [ "$had_working_changes" = true ]; then
  gum style --foreground 82 "  📦 Working tree: Staged, unstaged, and untracked changes restored."
fi
