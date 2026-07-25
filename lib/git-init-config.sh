#!/usr/bin/env bash
set -euo pipefail

# Display help message
show_help() {
  cat << 'EOF'
git init-config (or git-init-config)

Interactively generate and initialize .gitattributes and .gitignore files for your project by fetching official templates from GitHub repositories.

USAGE:
  git init-config [OPTIONS]
  git-init-config [OPTIONS]

OPTIONS:
  -h, --help    Show this help message and exit.

DESCRIPTION:
  1. Checks if .gitattributes exists in the current project and prompts for confirmation to overwrite if present.
  2. Fetches available .gitattributes templates from https://github.com/gitattributes/gitattributes.
  3. Prompts for multi-selection of languages/environments using gum.
  4. Generates .gitattributes with a SUMMARY header, structured sections, and a professional Custom section at the end.
  5. Repeats the process for .gitignore templates from https://github.com/github/gitignore.

PREREQUISITES:
  Requires curl, jq, and gum installed on your system.
EOF
  exit 0
}

# Parse command line arguments
for arg in "$@"; do
  case "$arg" in
    -h | --help)
      show_help
      ;;
  esac
done

# Check required dependencies
for cmd in curl jq gum; do
  if ! command -v "$cmd" &> /dev/null; then
    echo "Error: Command '$cmd' is not installed." >&2
    exit 1
  fi
done

# Temporary directory for cached responses
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo ""
gum style --foreground 212 --bold "🚀 Initializing Git configuration (.gitattributes & .gitignore)"
echo ""

# ==============================================================================
# PHASE 1: .gitattributes
# ==============================================================================
GENERATE_ATTRIBUTES=true

if [ -f ".gitattributes" ]; then
  if ! gum confirm "File .gitattributes already exists. Do you want to overwrite it?"; then
    gum style --foreground 244 "⏩ Skipped .gitattributes initialization."
    GENERATE_ATTRIBUTES=false
  fi
fi

if [ "$GENERATE_ATTRIBUTES" = true ]; then
  ATTR_TREE_FILE="$TMP_DIR/gitattributes_tree.json"

  gum spin --spinner dot --title "Fetching .gitattributes template list from GitHub..." -- \
    curl -sSf "https://api.github.com/repos/gitattributes/gitattributes/git/trees/master?recursive=1" -o "$ATTR_TREE_FILE"

  # Extract list of language paths (ending in .gitattributes, excluding root .gitattributes)
  ATTR_PATHS=$(jq -r '.tree[] | select(.type=="blob" and (.path | endswith(".gitattributes")) and .path != ".gitattributes") | .path' "$ATTR_TREE_FILE")

  # Create menu options by stripping .gitattributes suffix
  ALL_ATTR_LANGS="${ATTR_PATHS//.gitattributes/}"

  # Sort order: Common first, then Global/*, then community/*, then others
  COMMON_ITEMS=$(echo "$ALL_ATTR_LANGS" | grep '^Common$' || true)
  GLOBAL_ATTR_ITEMS=$(echo "$ALL_ATTR_LANGS" | grep '^Global/' | sort -f || true)
  COMMUNITY_ATTR_ITEMS=$(echo "$ALL_ATTR_LANGS" | grep '^community/' | sort -f || true)
  OTHER_ATTR_ITEMS=$(echo "$ALL_ATTR_LANGS" | grep -v '^Common$' | grep -v '^Global/' | grep -v '^community/' | sort -f || true)

  ATTR_LANGS=$(printf "%s\n%s\n%s\n%s\n" "$COMMON_ITEMS" "$GLOBAL_ATTR_ITEMS" "$COMMUNITY_ATTR_ITEMS" "$OTHER_ATTR_ITEMS" | sed '/^$/d')

  echo ""
  gum style --foreground 99 --bold "📌 Select one or more languages/configurations for .gitattributes (Use Tab/Space to select, Enter to confirm):"

  SELECTED_ATTR_LANGS=$(echo "$ATTR_LANGS" | gum filter --no-limit --selected="Common" --placeholder "Type to search .gitattributes...") || SELECTED_ATTR_LANGS=""

  # Sort selected items in guaranteed order: Common first, Global/* second, community/* third, others last
  SORTED_SELECTED_ATTR_LANGS=""
  if [ -n "$SELECTED_ATTR_LANGS" ]; then
    SORTED_SELECTED_ATTR_LANGS=$(
      {
        echo "$SELECTED_ATTR_LANGS" | grep '^Common$' || true
        echo "$SELECTED_ATTR_LANGS" | grep '^Global/' | sort -f || true
        echo "$SELECTED_ATTR_LANGS" | grep '^community/' | sort -f || true
        echo "$SELECTED_ATTR_LANGS" | grep -v '^Common$' | grep -v '^Global/' | grep -v '^community/' | sort -f || true
      } | sed '/^$/d'
    )
  fi

  # Initialize empty .gitattributes
  # shellcheck disable=SC2188
  > .gitattributes

  if [ -n "$SORTED_SELECTED_ATTR_LANGS" ]; then
    {
      echo "#! ----- ----- ----- SUMMARY ----- ----- ----- !#"
      while IFS= read -r lang; do
        [ -n "$lang" ] && echo "# ${lang}"
      done <<< "$SORTED_SELECTED_ATTR_LANGS"
    } >> .gitattributes

    while IFS= read -r lang; do
      [ -z "$lang" ] && continue
      path="${lang}.gitattributes"
      raw_url="https://raw.githubusercontent.com/gitattributes/gitattributes/master/${path}"
      blob_url="https://github.com/gitattributes/gitattributes/blob/master/${path}"

      gum style --foreground 39 "⬇️  Downloading: ${path}"

      {
        echo "#! ----- ----- ----- ----- ----- ${lang} ----- ----- ----- ----- ----- !#"
        echo "#? ${blob_url}"
        curl -sSf "$raw_url" || echo "# [Error downloading content]"
        echo ""
      } >> .gitattributes
    done <<< "$SORTED_SELECTED_ATTR_LANGS"
  fi

  # Append professional Custom section
  {
    echo "#! ----- ----- ----- ----- ----- Custom ----- ----- ----- ----- ----- !#"
    echo "# Custom repository-specific rules and overrides"
  } >> .gitattributes

  gum style --foreground 82 "✅ Successfully initialized .gitattributes"
  echo ""
fi

# ==============================================================================
# PHASE 2: .gitignore
# ==============================================================================
GENERATE_GITIGNORE=true

if [ -f ".gitignore" ]; then
  if ! gum confirm "File .gitignore already exists. Do you want to overwrite it?"; then
    gum style --foreground 244 "⏩ Skipped .gitignore initialization."
    GENERATE_GITIGNORE=false
  fi
fi

if [ "$GENERATE_GITIGNORE" = true ]; then
  IGNORE_TREE_FILE="$TMP_DIR/gitignore_tree.json"

  gum spin --spinner dot --title "Fetching .gitignore template list from GitHub..." -- \
    curl -sSf "https://api.github.com/repos/github/gitignore/git/trees/main?recursive=1" -o "$IGNORE_TREE_FILE"

  # Extract list of language paths (ending in .gitignore, excluding root .gitignore)
  IGNORE_PATHS=$(jq -r '.tree[] | select(.type=="blob" and (.path | endswith(".gitignore")) and .path != ".gitignore") | .path' "$IGNORE_TREE_FILE")

  # Create menu options by stripping .gitignore suffix
  ALL_IGNORE_LANGS="${IGNORE_PATHS//.gitignore/}"

  # Sort order: Global/* first, then community/*, then others
  GLOBAL_ITEMS=$(echo "$ALL_IGNORE_LANGS" | grep '^Global/' | sort -f || true)
  COMMUNITY_ITEMS=$(echo "$ALL_IGNORE_LANGS" | grep '^community/' | sort -f || true)
  OTHER_ITEMS=$(echo "$ALL_IGNORE_LANGS" | grep -v '^Global/' | grep -v '^community/' | sort -f || true)

  IGNORE_LANGS=$(printf "%s\n%s\n%s\n" "$GLOBAL_ITEMS" "$COMMUNITY_ITEMS" "$OTHER_ITEMS" | sed '/^$/d')

  echo ""
  gum style --foreground 99 --bold "📌 Select one or more languages/environments for .gitignore (Use Tab/Space to select, Enter to confirm):"

  SELECTED_IGNORE_LANGS=$(echo "$IGNORE_LANGS" | gum filter --no-limit --selected="Global/macOS,Global/Windows,Global/Linux" --placeholder "Type to search .gitignore...") || SELECTED_IGNORE_LANGS=""

  # Sort selected items in the required order: Global/* first, community/* second, others last
  SORTED_SELECTED_IGNORE_LANGS=""
  if [ -n "$SELECTED_IGNORE_LANGS" ]; then
    SORTED_SELECTED_IGNORE_LANGS=$(
      {
        echo "$SELECTED_IGNORE_LANGS" | grep '^Global/' | sort -f || true
        echo "$SELECTED_IGNORE_LANGS" | grep '^community/' | sort -f || true
        echo "$SELECTED_IGNORE_LANGS" | grep -v '^Global/' | grep -v '^community/' | sort -f || true
      } | sed '/^$/d'
    )
  fi

  # Initialize empty .gitignore
  # shellcheck disable=SC2188
  > .gitignore

  if [ -n "$SORTED_SELECTED_IGNORE_LANGS" ]; then
    {
      echo "#! ----- ----- ----- SUMMARY ----- ----- ----- !#"
      while IFS= read -r lang; do
        [ -n "$lang" ] && echo "# ${lang}"
      done <<< "$SORTED_SELECTED_IGNORE_LANGS"
    } >> .gitignore

    while IFS= read -r lang; do
      [ -z "$lang" ] && continue
      path="${lang}.gitignore"
      raw_url="https://raw.githubusercontent.com/github/gitignore/main/${path}"
      blob_url="https://github.com/github/gitignore/blob/main/${path}"

      gum style --foreground 39 "⬇️  Downloading: ${path}"

      {
        echo "#! ----- ----- ----- ----- ----- ${lang} ----- ----- ----- ----- ----- !#"
        echo "#? ${blob_url}"
        curl -sSf "$raw_url" | sed $'s/Icon\\[\r\\]/Icon?/g' || echo "# [Error downloading content]"
        echo ""
      } >> .gitignore
    done <<< "$SORTED_SELECTED_IGNORE_LANGS"
  fi

  # Append professional Custom section
  {
    echo "#! ----- ----- ----- ----- ----- Custom ----- ----- ----- ----- ----- !#"
    echo "# Custom repository-specific ignore rules and patterns"
  } >> .gitignore

  gum style --foreground 82 "✅ Successfully initialized .gitignore"
  echo ""
fi

gum style --foreground 212 --bold "🎉 Git configuration setup completed!"
