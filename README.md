# `@culur/bash`

> A collection of interactive Bash utilities and custom Git subcommands designed to supercharge your Git workflow.

## 🚀 Prerequisites

These utilities rely on the following CLI dependencies:

- **Git**
- **Bash (>= 4.0)**: Required for features like the `mapfile` (or `readarray`) command. Note that the default pre-installed Bash on macOS is version 3.2.x, which is too old and does not support `mapfile`.
- **[gum](https://github.com/charmbracelet/gum)** (for interactive selection prompts)
- **tmux** & **Python 3** (required for `agy-usage` headless terminal screen capture and parsing)

To install these dependencies (on macOS via Homebrew):

```bash
# Install modern Bash (which includes mapfile support)
brew install bash

# Install gum, tmux, and python3
brew install gum tmux python3
```

---

## ✨ Features & Usage

This package provides interactive commands for Git workflow automation:

### 1. `git fixup` (or `git-fixup`)

Stage changes for a file, commit them as a `fixup!` commit against a target commit, and automatically execute an interactive rebase with autosquash and autostash.

- **Options:**
  - `git fixup [NUMBER]`: Search the last `NUMBER` commits from the entire history (by default, shows the last 10 commits related to the selected files).
  - `-h, --help`: Show help message.

- **How it works:**
  1. Checks if any staged files exist in the repository. If staged files are found, they are automatically selected. Otherwise, prompts you to interactively choose from modified/untracked files.
  2. Displays a list of commits to choose as the target.
     - By default, shows the last 10 commits related to the selected files.
     - If a positional `NUMBER` argument (e.g. `15`) is provided, shows the last `NUMBER` commits from the entire history.
  3. Stages the selected file(s) (if unstaged) and commits them with `fixup! <target commit subject>`.
  4. Backs up the pre-rewrite state to a temporary backup branch `fixup-backup/...` to keep your history safe.
  5. Rebases and autosquashes automatically using `git rebase -i --autosquash --autostash` without opening your editor.
  6. Prompts you to delete the temporary backup branch.

- **Examples:**

  ```bash
  # Fix up staged files (or interactively choose modified files if none staged)
  git fixup
  
  # Search from the last 15 commits in the entire history
  git fixup 15
  ```

### 2. `git out` (or `git-out`)

Interactively pull files out of a selected commit in your history, rewriting the commit history to exclude them and returning the pulled files to your working tree as modifications.

- **Options:**
  - `git out [COMMIT]` or `git out [NUMBER]`: Specify the target commit directly via positional argument (e.g., `HEAD~1`, `~1`, `feat/abc`, `a1b2c3d`) or specify an interactive limit (e.g., `5`, `20`). If omitted, defaults to interactively selecting from the last 50 commits.
  - `-h, --help`: Show help message.
  - `-a, --all, --acc, --accumulation`: Find all files changed from the selected commit up to `HEAD` (accumulate changes across subsequent commits).

- **How it works:**
  1. Identifies files changed in the selected commit (or up to `HEAD` if `-a` is used).
  2. Displays an interactive list allowing you to select (or multi-select) files using `gum`.
  3. Automatically performs an interactive rebase to check out the parent state of the target commit for those selected files (effectively removing them from the commit).
  4. Resolves conflicts cleanly, deletes files if they didn't exist in the parent commit, and handles empty commits gracefully.
  5. Restores the selected files to your working tree as staged modifications.

- **Examples:**

  ```bash
  # Interactively select a commit from the last 50 commits (Default)
  git out
  
  # Interactively select a commit from the last 5 commits
  git out 5
  
  # Pull files out of the commit HEAD~1 using shorthand ~1
  git out ~1
  
  # Pull files out of commit HEAD~2
  git out HEAD~2
  
  # Pull files out of commit at branch feat/abc
  git out feat/abc
  
  # Pull files out of commit hash a1b2c3d
  git out a1b2c3d
  
  # Pull files out of ~1 and all subsequent commits up to HEAD
  git out ~1 -a
  ```

### 3. `git move` (or `git-move`)

Interactively select one or multiple commits from history, preview their accumulated file changes, and move them to be placed directly after a chosen target commit using automated rebase.

- **Options:**
  - `git move [NUMBER]`: Specify the number of recent commits to display in the interactive menu (default: 50).
  - `-h, --help`: Show help message.

- **How it works:**
  1. Checks for staged, unstaged, or untracked changes, creates a working tree integrity snapshot, and stashes uncommitted work to keep the repository clean during rebase.
  2. Displays an interactive menu using `gum` allowing you to multi-select $n$ commits to move.
  3. Displays a summary of total accumulated file changes across only the selected commits.
  4. Prompts you to pick a single target commit (from the recent commits minus the selected ones) to insert the moved commits after.
  5. Executes `git rebase -i` automatically to reorder the commits in history.
     - If conflicts occur, aborts the rebase immediately and restores your initial working tree and file states cleanly.
     - Performs an integrity check on final file states against the pre-rebase snapshot, automatically rolling back and notifying you if any deviation is detected.

- **Examples:**

  ```bash
  # Interactively select commit(s) from the last 50 commits to move (Default)
  git move
  
  # Interactively select commit(s) from the last 15 commits to move
  git move 15
  ```

### 4. `git init-config` (or `git-init-config`)

Interactively generate and initialize `.gitattributes` and `.gitignore` files for your project by fetching official templates from GitHub repositories.

- **Options:**
  - `-h, --help`: Show help message.

- **How it works:**
  1. Checks if `.gitattributes` exists in the current project repository and prompts for confirmation to overwrite if present.
  2. Fetches the complete list of `.gitattributes` templates from [gitattributes/gitattributes](https://github.com/gitattributes/gitattributes).
  3. Prompts you to search and select one or multiple languages/environments using `gum`.
  4. Downloads and appends the selected templates with clear block headers (`#! ----- <Language> ----- !#`) and GitHub source URLs, ending with a professional Custom section.
  5. Repeats the same interactive generation flow for `.gitignore` templates from [github/gitignore](https://github.com/github/gitignore).

- **Examples:**

  ```bash
  # Interactively initialize .gitattributes and .gitignore for your repository
  git init-config
  
  # Display help message
  git init-config --help
  ```

### 5. `agy-usage`

An interactive visualizer for Google Antigravity CLI (`agy`) usage and quota metrics, leveraging headless PTY screen capture to parse TUI output with 0 LLM token cost and 0 API risk.

- **Options:**
  - `--mock`: Run in mock mode with sample data to test visual rendering without invoking `tmux` or `agy`.

- **How it works:**
  1. **Headless Terminal Emulation:** Spawns a background `tmux` PTY session (`agy_usage_<PID>`) at a fixed resolution (120x40) running the `agy` CLI.
  2. **Automated Handshake & Query:** Continuously polls the terminal buffer via `tmux capture-pane`, auto-confirms prompt trust dialogues, and sends the `/usage` TUI command once the CLI is ready.
  3. **Regex Metric Parsing:** Captures pane output upon detecting `/usage` response, extracts remaining Gemini quota percentage and refresh duration, and terminates the `tmux` session cleanly.
  4. **Quota Pacing & Time Analysis:** Calculates elapsed time vs. consumed quota across the 7-day (168-hour) cycle to determine your consumption pace differential (`% token used` vs `% time passed`).
  5. **Rich Terminal Visuals:** Prints ANSI progress bars, status spinners, remaining time metrics, and dynamic color-coded pace warnings before exiting.

- **Examples:**

  ```bash
  # Query real-time agy quota usage and pace once and exit
  agy-usage

  # Run in mock mode to preview UI formatting
  agy-usage --mock
  ```

- **Example Output:**

  ```text
  [1/4] ✓ Starting headless tmux session...
  [2/4] ✓ Launching agy CLI and waiting for sign-in...
  [3/4] ✓ Querying usage via /usage command...
  [4/4] ✓ Capturing screen and parsing quota metrics...

  Weekly Limit
    [███████████████████████████████░░░░░░░░░░░░░░░░░░░] 62.82%

  Weekly Remaining
    [█████████████████████████████████░░░░░░░░░░░░░░░░░] 66.22%
    Passed: 56h (2d 8h) · Remaining: 111h (4d 15h)

    You are using tokens 3.40% faster than time elapsed (be careful, might run out!)
  ```

---

## 📦 Installation

### Step 1: Clone the Repository

Clone the repository to your local machine:

```bash
git clone https://github.com/culur/bash.git
cd bash
```

### Step 2: Grant Executable Permissions

Make sure the scripts have executable permissions. Run this command inside the cloned repository root:

```bash
chmod +x bin/git-fixup bin/git-out bin/git-move bin/git-init-config bin/agy-usage
```

### Step 3: Configure to use the commands

Choose one of the following options to make the commands available in your environment:

#### Option A: Add the `bin/` Directory to your `PATH` (Recommended)

Since the scripts inside the `bin/` directory are prefixed with `git-` (`git-fixup`, `git-out`, and `git-move`), adding the `bin/` directory directly to your shell's `PATH` allows Git to automatically discover them as subcommands.

Add this line to your shell configuration file (e.g., `~/.zshrc` or `~/.bash_profile`), replacing `/path/to/cloned/bash` with the actual absolute path to the directory where you cloned the repository:

```bash
export PATH="/path/to/cloned/bash/bin:$PATH"
```

_(Tip: Or dynamically if you are in the project folder: `export PATH="$(pwd)/bin:$PATH"`)_

Then reload your configuration:

```bash
source ~/.zshrc
```

#### Option B: Register Git Aliases (Alternative)

If you prefer not to modify your shell's `PATH` variable, you can define Git aliases pointing directly to the scripts. Make sure to replace `/path/to/cloned/bash` with the actual absolute path to the directory where you cloned the repository.

##### Global Config (Available in all repositories)

```bash
git config --global alias.fixup "!/path/to/cloned/bash/bin/git-fixup"
git config --global alias.out "!/path/to/cloned/bash/bin/git-out"
git config --global alias.move "!/path/to/cloned/bash/bin/git-move"
git config --global alias.init-config "!/path/to/cloned/bash/bin/git-init-config"
```

##### Local Config (Only available inside a specific repository)

```bash
git config alias.fixup "!/path/to/cloned/bash/bin/git-fixup"
git config alias.out "!/path/to/cloned/bash/bin/git-out"
git config alias.move "!/path/to/cloned/bash/bin/git-move"
git config alias.init-config "!/path/to/cloned/bash/bin/git-init-config"
```

_(Note: The `!` prefix at the start of the alias command is required. It tells Git to run the script in an external shell using its absolute path.)_

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
