# `@culur/bash`

> A collection of interactive Bash utilities and custom Git subcommands designed to supercharge your Git workflow.

---

## 💻 Platform Compatibility Matrix

| Command | Type | macOS | Windows | Key Requirements & Notes |
| :--- | :--- | :---: | :---: | :--- |
| **`git fixup`** | Git Subcommand | ✅ | ✅ | `gum`, `bash >= 4.0` (On Windows: run via Git for Windows + Git Alias) |
| **`git out`** | Git Subcommand | ✅ | ✅ | `gum`, `bash >= 4.0` (On Windows: run via Git for Windows + Git Alias) |
| **`git move`** | Git Subcommand | ✅ | ✅ | `gum`, `bash >= 4.0` (On Windows: run via Git for Windows + Git Alias) |
| **`git init-config`** | Git Subcommand | ✅ | ✅ | `gum`, `bash >= 4.0`, `curl` |
| **`git r`** | Git Subcommand | ✅ | ✅ | `bash >= 4.0` (On Windows: run via Git for Windows + Git Alias or `git-r.cmd`/`git-r.ps1`) |
| **`git acc`** | Git Subcommand / CLI | ✅ | ✅ | `python >= 3.10` or `uv`. Interactive commit account switcher. |
| **`git reacc`** | Git Subcommand | ✅ | ✅ | `gum`, `bash >= 4.0` (On Windows: run via Git for Windows + Git Alias or `git-reacc.cmd`/`git-reacc.ps1`) |
| **`clean-git`** | Standalone CLI | ✅ | ✅ | `uv`, `python >= 3.10`. Native Windows console (UTF-8 & VT100 ANSI) supported. |
| **`ai-usage`** | Standalone CLI | ✅ | ❌ | `tmux`, `python 3`, POSIX `termios`/`tty`. **macOS/Linux only.** |
| **`agy-usage`** | Standalone CLI | ✅ | ❌ | `tmux`, `python 3`. **macOS/Linux only (Deprecated).** |
| **`tscale`** | Standalone CLI | ✅ | ❌ | Tailscale CLI + Microsoft GSA integration for macOS `launchd`. **macOS only.** |

---

## 🚀 Prerequisites

> [!IMPORTANT]
> **Tool Management Rule: Always install via `mise` first**
> Developer tools and language runtimes (such as **`uv`**, **`python`**, **`node`**, **`pnpm`**) MUST always be installed and managed through **[mise](https://mise.jdx.dev/)** first:
>
> ```bash
> # Install runtimes via mise (Both macOS & Windows)
> mise use -g uv
> mise use -g node@lts   # (optional, for code formatting tools)
> mise use -g pnpm       # (optional, for package management)
> ```
>
> Only use system package managers for OS-level utilities that are not managed by `mise` (e.g. `git`, `bash`, `gum`, `tmux`). Use **Homebrew** on macOS. On Windows, install with **Scoop** first; use **WinGet** only when Scoop cannot be used.

### 1. Developer Toolchains (via `mise` - Both macOS & Windows)

Ensure `mise` is installed ([mise installation guide](https://mise.jdx.dev/getting-started.html)), then install the required tools:

```bash
# Required for Python scripts (clean-git, ai-usage, agy-usage) and dependency management
mise use -g uv

# (Optional) For Prettier/JavaScript formatting
mise use -g node@lts
mise use -g pnpm
```

### 2. System Utilities (via OS Package Managers)

#### 🍏 On macOS (Homebrew)

```bash
# Modern Bash (>= 4.0 with mapfile support), gum interactive selector, tmux & python3
brew install bash gum tmux python3
```

#### 🪟 On Windows (Scoop preferred; WinGet fallback)

Install Windows utilities through [Scoop](https://scoop.sh/) first:

   ```powershell
   scoop install git charm-gum
   ```

This installs **[Git for Windows](https://gitforwindows.org/)** (including MSYS2 GNU Bash 5.x) and **[gum](https://github.com/charmbracelet/gum)** for interactive prompts. If Scoop is unavailable in your environment, use WinGet instead:

   ```powershell
   winget install Git.Git
   winget install charmbracelet.gum
   ```

---

## ✨ Features & Usage

### 1. `git fixup` (or `git-fixup`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias)

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

---

### 2. `git out` (or `git-out`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias)

Interactively select files from a specific commit or range of commits to pull them out of history and restore them into your working directory as uncommitted changes.

- **Options:**
  - `git out [COMMIT_HASH|SHORTHAND]`: Target a specific commit (e.g., `HEAD~1`, `~2`, or commit hash). If omitted, defaults to the parent commit (`HEAD~1`).
  - `-a, --all`: Pull files out of the target commit and **all subsequent commits** up to `HEAD`.
  - `-h, --help`: Show help message.

- **How it works:**
  1. Checks for staged or uncommitted changes, stashing them if necessary.
  2. Displays an interactive menu using `gum` to let you select which files to pull out from the target commit (or commit range).
  3. Extracts the selected files and places them as uncommitted changes in your working tree.
  4. Automatically rebases history to rewrite the commits as if the selected files were never part of them.
  5. If conflict arises or tests fail, aborts safely and restores your repository to its exact prior state.

- **Examples:**

  ```bash
  # Pull files out of the previous commit (HEAD~1)
  git out

  # Pull files out of the commit HEAD~1 using shorthand ~1
  git out ~1

  # Pull files out of ~1 and all subsequent commits up to HEAD
  git out ~1 -a
  ```

---

### 3. `git move` (or `git-move`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias)

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

---

### 4. `git init-config` (or `git-init-config`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias)

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

---

### 5. `git r` (or `git-r`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias or `git-r.ps1` / `git-r.cmd`)

Temporarily toggle the Git remote `origin` up or down so your repository behaves as a local-only repository (e.g. to test local workflows, prevent accidental pushes, or simulate an untracked local repository) without losing branch tracking configurations or remote commit history.

> [!NOTE]
> This command strictly supports only repositories with a single remote named `origin`. If multiple remotes exist or the remote is not named `origin`, the script halts immediately with an error.

- **Options:**
  - `git r` or `git r status`: Display current status of `origin` (`[UP]` or `[DOWN]`) along with its URL (Default).
  - `git r down`: Disable the active `origin` remote and detach upstream branch tracking.
  - `git r up`: Re-enable the disabled `origin` remote and restore upstream branch tracking.
  - `-h, --help`: Show help message.

- **How it works:**
  1. **Strict Single-Origin Safety:** Validates repository remotes upfront and fails fast if the repository has multiple remotes or a non-`origin` remote.
  2. **Safe Native Config Toggling:** Renames the remote configuration section between `remote.origin` and `disabled-remote.origin` using `git config --rename-section`, ensuring file safety, concurrency locking, and full reversibility.
  3. **Upstream Branch Tracking Preservation:** Stashes branch tracking mappings (`branch.<name>.remote` -> `branch.<name>.disabled-remote`) so `git status` and `git push` treat branches as clean local branches without remote destinations.
  4. **Conflict Diagnostic & Safe Abort:** If a new `origin` is added while the original is disabled (e.g. via GUI/IDE action), `git r up` safely aborts without altering any configuration, logging a detailed diagnostic report with old vs new URLs, tracked branches, and existing remote refs.
  5. **Zero History Loss:** Does not delete cached remote tracking refs or commit objects, keeping them safe from garbage collection and avoiding any need to re-fetch from the network upon re-enabling.

- **Examples:**

  ```bash
  # Check status of origin
  git r

  # Disable origin remote (switch to local-only mode)
  git r down

  # Re-enable origin remote and restore tracking
  git r up
  ```

---

### 6. `git acc` (or `git-acc`)

> **Platform Support:** ✅ macOS · ✅ Windows (via `git acc`, `git-acc.ps1`, `git-acc.cmd`, or `git-acc.sh`)

Interactively manage and switch your Git commit author identities (`user.name` and `user.email`). Easily toggle between personal, work, and open-source profiles without manually editing `.gitconfig`.

- **Key Highlights:**
  - **Interactive TUI Navigation:** Use `↑`/`↓` (or `k`/`j`) to navigate your accounts list and the "Add new" option; press `Enter` to switch Git's global identity.
  - **Active Profile Badge:** Clearly marks the currently active profile with `✔ [active]`.
  - **Inline Editing (`e`):** Press `e` on any account to edit its username and email; automatically syncs Git global config if the edited account is currently active.
  - **Safe Deletion (`Del` or `d`):** Confirms before deleting. If deleting the active account, automatically activates the next account in the list. If it is the only account remaining, requires adding a replacement account before deletion.
  - **Zero External Dependencies:** Built with Python standard library (`msvcrt` on Windows, `termios` on POSIX); fast startup with no package installs required.
  - **Local Storage:** Saved to `configs/git-accounts.json` inside the repository (gitignored).

- **Keybindings:**
  - `↑` / `↓`, `k` / `j`: Navigate accounts and "Add new"
  - `Enter`: Select and switch active Git account
  - `e`: Edit username and email of selected account
  - `Del` / `d`: Delete selected account (with safety guardrails)
  - `q` / `ESC`: Quit without changes

- **Options:**
  - `git acc`: Open interactive menu (Default).
  - `-l, --list`: Display configured accounts and active identity non-interactively.
  - `-c, --current`: Display current active Git global identity.
  - `-h, --help`: Show help message.

---

### 7. `git reacc` (or `git-reacc`)

> **Platform Support:** ✅ macOS · ✅ Windows (via Git Bash & Alias or `git-reacc.cmd` / `git-reacc.ps1`)

Interactively rewrite commit committer (and optionally author) identity across a range of commits up to `HEAD` using identities configured in `git acc`.

- **Key Highlights:**
  - **Seamless `git acc` Integration:** Automatically loads profiles from `configs/git-accounts.json` with fallback to current Git identity or custom manual input.
  - **Flexible Rewrite Scope:** Choose between rewriting **Committer only** (preserving original author and author timestamp) or **Both Author & Committer** (updating both author and committer identities).
  - **Preserves Author Timestamp:** When updating author identity, uses `--author` to ensure the original author timestamp (`GIT_AUTHOR_DATE`) remains 100% unchanged.
  - **Protects Working Tree State:** Safely stashes uncommitted staged, unstaged, and untracked changes before rewriting, and flawlessly restores index separation (`--index`) upon completion.
  - **Clean & Safe Rollback:** Tracks `ORIGINAL_HEAD` in memory with automated trap handlers for clean rollback if canceled (`Ctrl+C`) or failed—leaving zero leftover backup branches in your repository.
  - **Preserves Merge Structure:** Automatically passes `--rebase-merges` if the commit range contains merge commits.

- **Options:**
  - `git reacc [NUMBER]`: Specify the number of recent commits to display in the interactive menu (default: 30).
  - `-n, -c, --count NUMBER`: Specify the number of commits to display.
  - `-h, --help`: Show help message.

- **Examples:**

  ```bash
  # Interactively select identity, scope, and target commit from the last 30 commits
  git reacc

  # Choose from the last 10 commits
  git reacc 10
  ```

---

### 8. `clean-git`

> **Platform Support:** ✅ macOS · ✅ Windows

A safe, interactive Git workspace cleaner written in Python and executed via `uv`. It scans untracked and gitignored files/directories, calculates space reclaimed, and lets you interactively choose what to delete with `InquirerPy` and `rich`.

- **Key Highlights:**
  - **Safety First:** Automatically protects `.env*` files by default to avoid accidental deletion of credentials.
  - **Dry Run Support:** Review the total space to be reclaimed before performing any deletion.
  - **Cross-Platform:** Native support on both macOS/Linux and Windows (with VT100 ANSI sequences and UTF-8 console output).

- **Options:**
  - `-h, --help`: Show help message.
  - `-e, --exclude PATTERN`: Exclude pattern (defaults to protecting `.env*`). Can be passed multiple times (e.g. `-e secret.json -e "*.local"`).
  - `--dry-run-only`: Show the preview summary table and exit without prompting for deletion.

- **Examples:**

  ```bash
  # Run interactive cleaning
  clean-git

  # Preview files and size without deleting
  clean-git --dry-run-only

  # Exclude custom sensitive files
  clean-git -e "secret.json" -e "*.pem"
  ```

---

### 9. `ai-usage`

> [!WARNING]
> **macOS & Linux only:** This tool relies on background `tmux` sessions, POSIX `termios`, and `tty` I/O multiplexing. It is **not** supported on Windows native terminals.

An interactive, responsive Terminal UI (TUI) dashboard for visualizing AI CLI usage and quota metrics in real-time. **Currently, this command only supports the Google Antigravity CLI (`agy`).**

- **Examples:**

  ```bash
  # Launch the interactive AI Usage dashboard (macOS / Linux)
  ai-usage
  ```

---

### 10. `agy-usage` (Maintain Only / Deprecated)

> [!WARNING]
> **macOS & Linux only (Deprecated):** This is the legacy one-shot print command that relies on headless `tmux` capture. Please use `ai-usage` instead on macOS/Linux.

- **Examples:**

  ```bash
  agy-usage
  agy-usage --mock
  ```

---

### 11. `tscale`

> [!WARNING]
> **macOS only:** Designed specifically for macOS `launchd` and Microsoft Entra Global Secure Access (GSA) coexistence.

Controls Tailscale CLI daemon and inspects VPN status on macOS. See [src/tailscale/README.md](./src/tailscale/README.md) for full architecture and daemon configuration.

---

## 📦 Installation & Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/culur/bash.git
cd bash
```

### Step 2: Install Project Dependencies

Synchronize Python dependencies (CPython 3.14 + `ruff`):

```bash
uv sync
```

*(Optional for Node.js formatting tools if using pnpm):*

```bash
pnpm install
```

---

### Step 3: Platform Configuration

Choose your operating system below:

#### 🍏 For macOS Users

1. **Make scripts executable:**

   ```bash
   chmod +x bin/*
   ```

2. **Option A: Add `bin/` directory to `PATH` (Recommended):**
   Add this line to your `~/.zshrc` or `~/.bash_profile`:

   ```bash
   export PATH="/path/to/cloned/bash/bin:$PATH"
   ```

   Then reload: `source ~/.zshrc`.

3. **Option B: Register Git Aliases:**

   ```bash
   git config --global alias.fixup "!/path/to/cloned/bash/bin/git-fixup"
   git config --global alias.out "!/path/to/cloned/bash/bin/git-out"
   git config --global alias.move "!/path/to/cloned/bash/bin/git-move"
   git config --global alias.init-config "!/path/to/cloned/bash/bin/git-init-config"
   git config --global alias.r "!/path/to/cloned/bash/bin/git-r"
   git config --global alias.acc "!/path/to/cloned/bash/bin/git-acc"
   git config --global alias.reacc "!/path/to/cloned/bash/bin/git-reacc"
   ```

---

#### 🪟 For Windows Users

On Windows, Git subcommands require a two-part setup:

1. **Add `bin/` to User `PATH`**: Makes standalone and cross-platform CLIs `clean-git` (`clean-git.cmd`), `git-r` (`git-r.cmd`/`git-r.ps1`), `git-acc` (`git-acc.cmd`/`git-acc.ps1`), and `git-reacc` (`git-reacc.cmd`/`git-reacc.ps1`) available globally in PowerShell and CMD.
2. **Register Global Git Aliases**: In Git on Windows, repository symlinks in `bin/` are checked out as plain text files, causing `cannot spawn: Exec format error` if executed via PATH directly. Using Git Aliases with `!bash "..."` tells Git for Windows to execute the `.sh` scripts using Git's bundled MSYS2 GNU Bash (v5.x), seamlessly integrating with `gum.exe`.

Run the following commands in **PowerShell** (replace `C:/code/repo-culur/bash` with your actual repository path):

```powershell
# 1. Add bin/ to User PATH (Idempotent: only adds if not already present)
$repoBin = "C:\code\repo-culur\bash\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ';' | Where-Object { $_.TrimEnd('\') -eq $repoBin.TrimEnd('\') }).Count -eq 0) {
    $newUserPath = if ($userPath -and -not $userPath.EndsWith(';')) { "$userPath;$repoBin" } else { "$userPath$repoBin" }
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Write-Host "Added $repoBin to User PATH."
}

# 2. Register Global Git Subcommands
$repoSrc = "C:/code/repo-culur/bash/src/git"
git config --global alias.fixup "!bash `"$repoSrc/git-fixup.sh`""
git config --global alias.out "!bash `"$repoSrc/git-out.sh`""
git config --global alias.move "!bash `"$repoSrc/git-move.sh`""
git config --global alias.init-config "!bash `"$repoSrc/git-init-config.sh`""
git config --global alias.r "!bash `"$repoSrc/git-r.sh`""
git config --global alias.acc "!bash `"$repoSrc/git-acc.sh`""
git config --global alias.reacc "!bash `"$repoSrc/git-reacc.sh`""
```

---

### Step 4: Verification

Test that all tools are working in your shell:

```bash
# 1. Test clean-git CLI
clean-git --help

# 2. Test Git Subcommands
git fixup -h
git out -h
git move -h
git init-config -h
git r -h
git acc -h
git reacc -h
```

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
