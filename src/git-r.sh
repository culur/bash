#!/usr/bin/env bash
# git-r: Temporarily toggle git remote 'origin' up or down.
# Strictly supports only repositories with a single remote named 'origin'.

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
ensure_inside_a_git_repository

# UI Helper functions
has_gum() {
  command -v gum > /dev/null 2>&1
}

print_success() {
  if has_gum; then
    gum style --foreground 10 "✔ $1"
  else
    printf "\033[32m✔ %s\033[0m\n" "$1"
  fi
}

print_info() {
  if has_gum; then
    gum style --foreground 12 "ℹ $1"
  else
    printf "\033[34mℹ %s\033[0m\n" "$1"
  fi
}

print_warn() {
  if has_gum; then
    gum style --foreground 11 "⚠ $1"
  else
    printf "\033[33m⚠ %s\033[0m\n" "$1"
  fi
}

print_error() {
  if has_gum; then
    gum style --foreground 9 "✖ $1" >&2
  else
    printf "\033[31m✖ %s\033[0m\n" "$1" >&2
  fi
}

show_help() {
  cat << 'EOF'
git r (or git-r)

Temporarily toggle the Git remote 'origin' up or down so your repository
can behave as a local-only repository without losing tracking configuration or refs.

NOTE: This command strictly supports only a single remote named 'origin'.

USAGE:
  git r [COMMAND]
  git-r [COMMAND]

COMMANDS:
  down                  Disable 'origin' remote (switch to local-only mode).
  up                    Re-enable 'origin' remote and restore tracking branches.
  status                Display current status of 'origin' (Default).

OPTIONS:
  -h, --help            Show this help message and exit.

EXAMPLES:
  git r down            Disable 'origin' remote.
  git r up              Re-enable 'origin' remote.
  git r                 Show status of 'origin' (UP / DOWN).
EOF
}

# Check if a remote is active
is_remote_active() {
  local target="$1"
  git config --get-regexp "^remote\.${target}\." > /dev/null 2>&1
}

# Check if a remote is disabled
is_remote_disabled() {
  local target="$1"
  git config --get-regexp "^disabled-remote\.${target}\." > /dev/null 2>&1
}

# Get list of active remotes
get_active_remotes() {
  git remote 2>/dev/null || true
}

# Get list of disabled remote names
get_disabled_remotes() {
  local entries
  entries=$(git config --get-regexp '^disabled-remote\..*\.url$' 2>/dev/null || true)
  if [[ -n "$entries" ]]; then
    while IFS=' ' read -r key _; do
      local name="${key#disabled-remote.}"
      name="${name%.url}"
      echo "$name"
    done <<< "$entries"
  fi
}

# Enforce strict single remote 'origin' rule
validate_single_origin_constraint() {
  local active_list
  active_list=$(get_active_remotes)
  local active_count=0
  if [[ -n "$active_list" ]]; then
    active_count=$(echo "$active_list" | grep -c . || true)
  fi

  local disabled_list
  disabled_list=$(get_disabled_remotes)
  local disabled_count=0
  if [[ -n "$disabled_list" ]]; then
    disabled_count=$(echo "$disabled_list" | grep -c . || true)
  fi

  # Check active remotes
  if [[ $active_count -gt 1 ]]; then
    print_error "Multiple active remotes detected: $(echo "$active_list" | tr '\n' ' ')"
    print_error "git-r strictly supports repositories with only a single remote named 'origin'."
    exit 1
  fi

  if [[ $active_count -eq 1 ]]; then
    local active_name
    active_name=$(echo "$active_list" | head -n 1)
    if [[ "$active_name" != "origin" ]]; then
      print_error "Found single remote '${active_name}', but git-r only supports remote named 'origin'."
      exit 1
    fi
  fi

  # Check disabled remotes
  if [[ $disabled_count -gt 1 ]]; then
    print_error "Multiple disabled remotes detected: $(echo "$disabled_list" | tr '\n' ' ')"
    print_error "git-r strictly supports repositories with only a single remote named 'origin'."
    exit 1
  fi

  if [[ $disabled_count -eq 1 ]]; then
    local disabled_name
    disabled_name=$(echo "$disabled_list" | head -n 1)
    if [[ "$disabled_name" != "origin" ]]; then
      print_error "Found disabled remote '${disabled_name}', but git-r only supports remote named 'origin'."
      exit 1
    fi
  fi
}

# Display status of origin remote
cmd_status() {
  local active_origin=false
  local disabled_origin=false

  if is_remote_active "origin"; then
    active_origin=true
  fi

  if is_remote_disabled "origin"; then
    disabled_origin=true
  fi

  if ! $active_origin && ! $disabled_origin; then
    echo "No remote 'origin' configured (active or disabled) in this repository."
    return 0
  fi

  echo "Git Remote Status:"
  echo ""

  if $active_origin; then
    local url
    url=$(git config "remote.origin.url" 2>/dev/null || echo "unknown")
    if has_gum; then
      echo -e "  $(gum style --foreground 10 --bold "[UP]")   origin\t(${url})"
    else
      echo -e "  \033[32m[UP]\033[0m   origin\t(${url})"
    fi
  fi

  if $disabled_origin; then
    local url
    url=$(git config "disabled-remote.origin.url" 2>/dev/null || echo "unknown")
    if has_gum; then
      echo -e "  $(gum style --foreground 11 --bold "[DOWN]") origin\t(${url})"
    else
      echo -e "  \033[33m[DOWN]\033[0m origin\t(${url})"
    fi
  fi
  echo ""
}

# Disable remote 'origin'
cmd_down() {
  if is_remote_disabled "origin" && ! is_remote_active "origin"; then
    print_warn "Remote 'origin' is already DOWN (disabled)."
    return 0
  fi

  if ! is_remote_active "origin"; then
    print_error "Remote 'origin' does not exist in this repository."
    return 1
  fi

  # Rename remote section: remote.origin -> disabled-remote.origin
  git config --rename-section "remote.origin" "disabled-remote.origin"

  # Move tracking branch references
  local branch_count=0
  local matches
  matches=$(git config --get-regexp '^branch\..*\.remote$' "^origin$" 2>/dev/null || true)

  if [[ -n "$matches" ]]; then
    while IFS=' ' read -r key val; do
      local branch_name="${key#branch.}"
      branch_name="${branch_name%.remote}"
      git config "branch.${branch_name}.disabled-remote" "$val"
      git config --unset "branch.${branch_name}.remote"
      branch_count=$((branch_count + 1))
    done <<< "$matches"
  fi

  print_success "Remote 'origin' is now DOWN (disabled)."
  if [[ $branch_count -gt 0 ]]; then
    print_info "Detached upstream tracking for ${branch_count} branch(es)."
  fi
}

# Re-enable remote 'origin'
cmd_up() {
  local active_exists=false
  local disabled_exists=false

  if is_remote_active "origin"; then
    active_exists=true
  fi

  if is_remote_disabled "origin"; then
    disabled_exists=true
  fi

  # Conflict check: Both active origin and disabled-remote origin exist!
  if $active_exists && $disabled_exists; then
    echo "" >&2
    print_error "Conflict Detected: Cannot restore disabled remote 'origin'!"
    echo "A new remote 'origin' was added while the original remote was disabled." >&2
    echo "" >&2

    local curr_url curr_pushurl
    curr_url=$(git config "remote.origin.url" 2>/dev/null || echo "N/A")
    curr_pushurl=$(git config "remote.origin.pushurl" 2>/dev/null || echo "")

    local old_url old_pushurl
    old_url=$(git config "disabled-remote.origin.url" 2>/dev/null || echo "N/A")
    old_pushurl=$(git config "disabled-remote.origin.pushurl" 2>/dev/null || echo "")

    echo "Current Active Remote (New):" >&2
    echo "  • Name:     origin" >&2
    echo "  • URL:      ${curr_url}" >&2
    [[ -n "$curr_pushurl" ]] && echo "  • Push URL: ${curr_pushurl}" >&2
    echo "" >&2

    echo "Previous Disabled Remote (Old):" >&2
    echo "  • Name:     origin" >&2
    echo "  • URL:      ${old_url}" >&2
    [[ -n "$old_pushurl" ]] && echo "  • Push URL: ${old_pushurl}" >&2
    echo "" >&2

    echo "Branches Tracked by Old Remote:" >&2
    local branch_matches
    branch_matches=$(git config --get-regexp '^branch\..*\.disabled-remote$' "^origin$" 2>/dev/null || true)
    if [[ -n "$branch_matches" ]]; then
      while IFS=' ' read -r b_key _; do
        local b_name="${b_key#branch.}"
        b_name="${b_name%.disabled-remote}"
        local b_merge
        b_merge=$(git config "branch.${b_name}.merge" 2>/dev/null || echo "N/A")
        echo "  • ${b_name}  ->  ${b_merge}" >&2
      done <<< "$branch_matches"
    else
      echo "  (none)" >&2
    fi
    echo "" >&2

    echo "Existing Remote Refs (refs/remotes/origin/*):" >&2
    local ref_list
    ref_list=$(git for-each-ref --format='  • %(refname:short)  ->  %(objectname:short) [%(subject)]' refs/remotes/origin 2>/dev/null || true)
    if [[ -n "$ref_list" ]]; then
      echo "$ref_list" >&2
    else
      echo "  (none)" >&2
    fi
    echo "" >&2

    if has_gum; then
      gum style --foreground 9 --bold "⛔ Action Aborted: No changes were made to your repository." >&2
    else
      printf "\033[31;1m⛔ Action Aborted: No changes were made to your repository.\033[0m\n" >&2
    fi
    echo "To resolve this conflict:" >&2
    echo "  1. If you want to keep the old remote, remove or rename the new active remote:" >&2
    echo "     git config --remove-section remote.origin  (or: git remote rename origin new-origin)" >&2
    echo "  2. Then run 'git r up' again to restore the original remote." >&2
    echo "" >&2
    exit 1
  fi

  if $active_exists && ! $disabled_exists; then
    print_warn "Remote 'origin' is already UP (active)."
    return 0
  fi

  if ! $disabled_exists; then
    print_error "No disabled remote 'origin' found to restore."
    return 1
  fi

  # Rename section back: disabled-remote.origin -> remote.origin
  git config --rename-section "disabled-remote.origin" "remote.origin"

  # Restore tracking branch references
  local branch_count=0
  local matches
  matches=$(git config --get-regexp '^branch\..*\.disabled-remote$' "^origin$" 2>/dev/null || true)

  if [[ -n "$matches" ]]; then
    while IFS=' ' read -r key val; do
      local branch_name="${key#branch.}"
      branch_name="${branch_name%.disabled-remote}"
      git config "branch.${branch_name}.remote" "$val"
      git config --unset "branch.${branch_name}.disabled-remote"
      branch_count=$((branch_count + 1))
    done <<< "$matches"
  fi

  print_success "Remote 'origin' is now UP (enabled)."
  if [[ $branch_count -gt 0 ]]; then
    print_info "Restored upstream tracking for ${branch_count} branch(es)."
  fi
}

# Main entry point
main() {
  local action="status"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help)
        show_help
        exit 0
        ;;
      up)
        action="up"
        shift
        ;;
      down)
        action="down"
        shift
        ;;
      status)
        action="status"
        shift
        ;;
      origin)
        # Explicit 'origin' argument is allowed for convenience
        shift
        ;;
      *)
        print_error "Unexpected argument '$1'."
        print_error "git-r strictly supports only 'origin'. Subcommands: up, down, status."
        show_help
        exit 1
        ;;
    esac
  done

  # Validate single origin constraint
  validate_single_origin_constraint

  case "$action" in
    status)
      cmd_status
      ;;
    down)
      cmd_down
      ;;
    up)
      cmd_up
      ;;
  esac
}

main "$@"
