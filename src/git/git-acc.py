#!/usr/bin/env python3
"""
git-acc: Interactive Git commit account manager and switcher.
Switch, add, edit, and safely delete Git commit identities (user.name & user.email).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configure Windows console UTF-8 & ANSI support
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    os.system("")  # Enable VT100 / ANSI escape sequence processing


# Resolve paths relative to src/git/git-acc.py
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
CONFIGS_DIR = REPO_ROOT / "configs"
ACCOUNTS_FILE = CONFIGS_DIR / "git-accounts.json"

# ANSI Color & Style Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[90m"
CYAN = "\033[36m"
BOLD_CYAN = "\033[1;36m"
GREEN = "\033[32m"
BOLD_GREEN = "\033[1;32m"
YELLOW = "\033[33m"
BOLD_YELLOW = "\033[1;33m"
RED = "\033[31m"
BOLD_RED = "\033[1;31m"
WHITE = "\033[37m"
BOLD_WHITE = "\033[1;37m"


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


atexit.register(show_cursor)


def signal_handler(_sig: int, _frame: Any) -> None:
    show_cursor()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, signal_handler)


def read_key() -> str:
    """Read a single keypress without waiting for Enter."""
    if sys.platform == "win32":
        import msvcrt
        import time

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # Special key / arrow / Del (Windows scan code)
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "UP"
            elif ch2 == b"P":
                return "DOWN"
            elif ch2 == b"S":
                return "DEL"
            return ""
        elif ch == b"\x1b":  # ESC or VT100 sequence (e.g. \x1b[A, \x1b[B, \x1b[3~)
            time.sleep(0.02)
            if msvcrt.kbhit():
                ch2 = msvcrt.getch()
                if ch2 in (b"[", b"O") and msvcrt.kbhit():
                    ch3 = msvcrt.getch()
                    if ch3 == b"A":
                        return "UP"
                    elif ch3 == b"B":
                        return "DOWN"
                    elif ch3 == b"3":
                        if msvcrt.kbhit():
                            msvcrt.getch()  # consume '~'
                        return "DEL"
                return ""
            return "QUIT"
        elif ch in (b"\r", b"\n"):
            return "ENTER"
        elif ch in (b"e", b"E"):
            return "EDIT"
        elif ch in (b"d", b"D"):
            return "DEL"
        elif ch in (b"q", b"Q"):
            return "QUIT"
        elif ch == b"k":
            return "UP"
        elif ch == b"j":
            return "DOWN"
        return ""
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    rest = sys.stdin.read(2)
                    if rest in ("[A", "OA"):
                        return "UP"
                    elif rest in ("[B", "OB"):
                        return "DOWN"
                    elif rest == "[3":
                        r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r2 and sys.stdin.read(1) == "~":
                            return "DEL"
                return "QUIT"
            elif ch in ("\r", "\n"):
                return "ENTER"
            elif ch in ("e", "E"):
                return "EDIT"
            elif ch in ("d", "D"):
                return "DEL"
            elif ch in ("q", "Q"):
                return "QUIT"
            elif ch == "k":
                return "UP"
            elif ch == "j":
                return "DOWN"
            return ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def get_current_git_identity() -> tuple[str, str]:
    """Retrieve current global Git user.name and user.email (fallback to local)."""
    name = ""
    email = ""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        res_name = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True,
            check=False,
        )
        name = res_name.stdout.strip()

    with contextlib.suppress(OSError, subprocess.SubprocessError):
        res_email = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        )
        email = res_email.stdout.strip()

    if not name or not email:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if not name:
                r = subprocess.run(
                    ["git", "config", "user.name"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                name = r.stdout.strip()
            if not email:
                r = subprocess.run(
                    ["git", "config", "user.email"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                email = r.stdout.strip()

    return name, email


def set_global_git_identity(name: str, email: str) -> None:
    """Set git config --global user.name and user.email."""
    subprocess.run(["git", "config", "--global", "user.name", name], check=True)
    subprocess.run(["git", "config", "--global", "user.email", email], check=True)


def load_accounts() -> list[dict[str, str]]:
    """Load accounts from configs/git-accounts.json."""
    if not ACCOUNTS_FILE.exists():
        return []
    with (
        contextlib.suppress(OSError, json.JSONDecodeError),
        open(ACCOUNTS_FILE, "r", encoding="utf-8") as f,
    ):
        data = json.load(f)
        if isinstance(data, list):
            return [
                {
                    "name": str(item.get("name", "")).strip(),
                    "email": str(item.get("email", "")).strip(),
                }
                for item in data
                if isinstance(item, dict) and item.get("name") and item.get("email")
            ]
    return []


def save_accounts(accounts: list[dict[str, str]]) -> None:
    """Save accounts atomically to configs/git-accounts.json."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = ACCOUNTS_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp_file.replace(ACCOUNTS_FILE)


def init_accounts_if_empty() -> list[dict[str, str]]:
    """Auto-import current Git identity if accounts list is empty."""
    accounts = load_accounts()
    if not accounts:
        curr_name, curr_email = get_current_git_identity()
        if curr_name and curr_email:
            accounts = [{"name": curr_name, "email": curr_email}]
            save_accounts(accounts)
    return accounts


def list_accounts_cli() -> None:
    """Print configured accounts and current active identity non-interactively."""
    accounts = init_accounts_if_empty()
    curr_name, curr_email = get_current_git_identity()

    print(f"Git Accounts ({ACCOUNTS_FILE}):")
    if not accounts:
        print("  (No accounts configured. Run 'git acc' to add your first account.)")
        return

    for i, acc in enumerate(accounts, 1):
        is_active = acc["name"] == curr_name and acc["email"] == curr_email
        badge = f" {BOLD_GREEN}✔ [active]{RESET}" if is_active else ""
        print(f"  {i:2d}. {acc['name']} <{acc['email']}>{badge}")


def show_current_cli() -> None:
    """Print current active Git identity non-interactively."""
    curr_name, curr_email = get_current_git_identity()
    if curr_name or curr_email:
        print(
            f"Active Git Identity: {curr_name or '<not set>'} <{curr_email or '<not set>'}>"
        )
    else:
        print("No Git identity currently configured in git config --global.")


def prompt_add_account(
    accounts: list[dict[str, str]],
) -> tuple[list[dict[str, str]], bool]:
    """
    Prompt user to enter a new account.
    Returns (updated_accounts, whether_activated_and_should_exit).
    """
    show_cursor()
    print()
    print(f"{BOLD_CYAN}--- Thêm Tài khoản Git Mới ---{RESET}")
    new_name = ""
    while not new_name:
        new_name = input("Nhập username: ").strip()
        if not new_name:
            print(f"{YELLOW}⚠ Username không được để trống.{RESET}")

    new_email = ""
    while not new_email or "@" not in new_email:
        new_email = input("Nhập email: ").strip()
        if not new_email or "@" not in new_email:
            print(f"{YELLOW}⚠ Vui lòng nhập địa chỉ email hợp lệ.{RESET}")

    accounts.append({"name": new_name, "email": new_email})
    save_accounts(accounts)

    switch_now = (
        input("Kích hoạt tài khoản này cho Git ngay bây giờ? [Y/n]: ").strip().lower()
    )
    if switch_now in ("", "y", "yes"):
        set_global_git_identity(new_name, new_email)
        print(f"{BOLD_GREEN}✔ Đã chuyển đổi danh tính Git sang:{RESET}")
        print(f"  user.name  = {BOLD_WHITE}{new_name}{RESET}")
        print(f"  user.email = {CYAN}{new_email}{RESET}")
        return accounts, True

    return accounts, False


def prompt_edit_account(
    accounts: list[dict[str, str]], idx: int, curr_name: str, curr_email: str
) -> tuple[str, str, str]:
    """
    Prompt user to edit account at idx.
    Returns (notice_msg, updated_curr_name, updated_curr_email).
    """
    show_cursor()
    target = accounts[idx]
    old_name = target["name"]
    old_email = target["email"]
    was_active = old_name == curr_name and old_email == curr_email

    print()
    print(f"{BOLD_CYAN}--- Sửa Tài khoản Git (#{idx + 1}) ---{RESET}")
    new_name = input(f"Nhập username mới [{old_name}]: ").strip()
    if not new_name:
        new_name = old_name

    new_email = input(f"Nhập email mới [{old_email}]: ").strip()
    if not new_email:
        new_email = old_email

    accounts[idx] = {"name": new_name, "email": new_email}
    save_accounts(accounts)

    if was_active:
        set_global_git_identity(new_name, new_email)
        curr_name, curr_email = new_name, new_email
        msg = f"Đã cập nhật tài khoản và đồng bộ Git: {new_name} <{new_email}>"
    else:
        msg = f"Đã cập nhật tài khoản: {new_name} <{new_email}>"

    return msg, curr_name, curr_email


def handle_delete_account(
    accounts: list[dict[str, str]], idx: int, curr_name: str, curr_email: str
) -> tuple[list[dict[str, str]], str, str, str]:
    """
    Handle deletion of account at idx with safety rules.
    Returns (accounts, notice_msg, updated_curr_name, updated_curr_email).
    """
    show_cursor()
    total = len(accounts)
    target = accounts[idx]
    target_name = target["name"]
    target_email = target["email"]
    was_active = target_name == curr_name and target_email == curr_email

    # Rule: If it's the only account left, require adding a replacement first
    if total <= 1:
        print()
        print(
            f"{BOLD_YELLOW}⚠ Không thể xóa tài khoản duy nhất trong danh sách.{RESET}"
        )
        print(f"Bạn phải nhập tài khoản thay thế trước khi xóa '{target_name}'.")
        print()

        rep_name = ""
        while not rep_name:
            rep_name = input("Nhập username thay thế (hoặc Ctrl+C để hủy): ").strip()

        rep_email = ""
        while not rep_email or "@" not in rep_email:
            rep_email = input("Nhập email thay thế: ").strip()
            if not rep_email or "@" not in rep_email:
                print(f"{YELLOW}⚠ Vui lòng nhập địa chỉ email hợp lệ.{RESET}")

        accounts[0] = {"name": rep_name, "email": rep_email}
        save_accounts(accounts)

        if was_active:
            set_global_git_identity(rep_name, rep_email)
            curr_name, curr_email = rep_name, rep_email

        msg = (
            f"Đã thay thế '{target_name}' bằng tài khoản mới: {rep_name} <{rep_email}>"
        )
        return accounts, msg, curr_name, curr_email

    # Rule: Confirm deletion
    print()
    confirm = (
        input(f"Bạn có chắc chắn muốn xóa '{target_name}' <{target_email}>? [y/N]: ")
        .strip()
        .lower()
    )
    if confirm not in ("y", "yes"):
        return accounts, "Đã hủy thao tác xóa.", curr_name, curr_email

    # If deleting active account: switch to next account
    if was_active:
        next_idx = idx + 1 if idx < total - 1 else idx - 1
        next_acc = accounts[next_idx]
        set_global_git_identity(next_acc["name"], next_acc["email"])
        curr_name, curr_email = next_acc["name"], next_acc["email"]
        msg = f"Đã xóa '{target_name}'. Tự động chuyển active sang: {next_acc['name']} <{next_acc['email']}>"
    else:
        msg = f"Đã xóa tài khoản: {target_name} <{target_email}>"

    accounts.pop(idx)
    save_accounts(accounts)
    return accounts, msg, curr_name, curr_email


def interactive_menu() -> None:
    """Main interactive menu loop."""
    accounts = init_accounts_if_empty()

    # If still empty, prompt for first account
    if not accounts:
        accounts, should_exit = prompt_add_account(accounts)
        if should_exit:
            return

    curr_name, curr_email = get_current_git_identity()

    # Pre-select active account index
    selected_index = 0
    for i, acc in enumerate(accounts):
        if acc["name"] == curr_name and acc["email"] == curr_email:
            selected_index = i
            break

    notice_msg = ""
    lines_rendered = 0

    # Flush any stray keystrokes from launching the command
    if sys.platform == "win32":
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getch()

    while True:
        total_accounts = len(accounts)
        total_options = total_accounts + 1  # accounts + "Add new"

        if selected_index >= total_options:
            selected_index = total_options - 1
        selected_index = max(selected_index, 0)

        # Clear previous render in-place
        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A\033[J")
            sys.stdout.flush()

        lines = 0
        # Header
        sys.stdout.write(
            f"{BOLD_CYAN}┌──────────────────────────────────────────────────────────────┐{RESET}\n"
        )
        lines += 1
        sys.stdout.write(
            f"{BOLD_CYAN}│{RESET} {BOLD}Git Account Manager (git acc){RESET}                                {BOLD_CYAN}│{RESET}\n"
        )
        lines += 1
        sys.stdout.write(
            f"{BOLD_CYAN}└──────────────────────────────────────────────────────────────┘{RESET}\n"
        )
        lines += 1

        # Current active identity
        if curr_name or curr_email:
            sys.stdout.write(
                f"  Active Identity: {BOLD_GREEN}{curr_name}{RESET} <{CYAN}{curr_email}{RESET}>\n"
            )
        else:
            sys.stdout.write(
                f"  Active Identity: {YELLOW}(Chưa cấu hình trong git config --global){RESET}\n"
            )
        lines += 1
        sys.stdout.write("\n")
        lines += 1

        # Render list of accounts
        for i, acc in enumerate(accounts):
            is_active = acc["name"] == curr_name and acc["email"] == curr_email
            badge = f" {BOLD_GREEN}✔ [active]{RESET}" if is_active else ""

            if i == selected_index:
                sys.stdout.write(
                    f" {BOLD_CYAN}❯{RESET} {BOLD_WHITE}{i + 1:2d}. {acc['name']}{RESET} {CYAN}<{acc['email']}>{RESET}{badge}\n"
                )
            else:
                sys.stdout.write(
                    f"    {i + 1:2d}. {acc['name']} <{acc['email']}>{badge}\n"
                )
            lines += 1

        # Render "Add new account" option
        if selected_index == total_accounts:
            sys.stdout.write(
                f" {BOLD_CYAN}❯{RESET} {BOLD_GREEN}➕ Thêm tài khoản mới (Add new){RESET}\n"
            )
        else:
            sys.stdout.write(f"    {GREEN}➕ Thêm tài khoản mới (Add new){RESET}\n")
        lines += 1

        # Keybindings footer
        sys.stdout.write("\n")
        lines += 1
        sys.stdout.write(
            f"{DIM}────────────────────────────────────────────────────────────────{RESET}\n"
        )
        lines += 1
        sys.stdout.write(
            f"{DIM}↑/↓: Di chuyển • Enter: Chọn • e: Sửa • Del/d: Xóa • q: Thoát{RESET}\n"
        )
        lines += 1

        # Notice message (if any)
        if notice_msg:
            sys.stdout.write(f"{BOLD_GREEN}ℹ {notice_msg}{RESET}\n")
            lines += 1
            notice_msg = ""

        sys.stdout.flush()
        lines_rendered = lines

        hide_cursor()
        key = read_key()

        if key == "UP":
            selected_index = (selected_index - 1 + total_options) % total_options
        elif key == "DOWN":
            selected_index = (selected_index + 1) % total_options
        elif key == "ENTER":
            if selected_index == total_accounts:
                # Add new account
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                    sys.stdout.flush()
                    lines_rendered = 0
                accounts, should_exit = prompt_add_account(accounts)
                if should_exit:
                    return
                selected_index = len(accounts) - 1
            else:
                # Switch active account
                chosen = accounts[selected_index]
                set_global_git_identity(chosen["name"], chosen["email"])
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                    sys.stdout.flush()
                print(f"{BOLD_GREEN}✔ Đã chuyển đổi tài khoản Git thành công:{RESET}")
                print(f"  user.name  = {BOLD_WHITE}{chosen['name']}{RESET}")
                print(f"  user.email = {CYAN}{chosen['email']}{RESET}")
                return
        elif key == "EDIT":
            if selected_index == total_accounts:
                # Trigger add new
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                    sys.stdout.flush()
                    lines_rendered = 0
                accounts, should_exit = prompt_add_account(accounts)
                if should_exit:
                    return
                selected_index = len(accounts) - 1
            else:
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                    sys.stdout.flush()
                    lines_rendered = 0
                notice_msg, curr_name, curr_email = prompt_edit_account(
                    accounts, selected_index, curr_name, curr_email
                )
        elif key == "DEL":
            if selected_index < total_accounts:
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                    sys.stdout.flush()
                    lines_rendered = 0
                accounts, notice_msg, curr_name, curr_email = handle_delete_account(
                    accounts, selected_index, curr_name, curr_email
                )
                if selected_index >= len(accounts):
                    selected_index = max(0, len(accounts) - 1)
        elif key == "QUIT":
            if lines_rendered > 0:
                sys.stdout.write(f"\033[{lines_rendered}A\033[J")
                sys.stdout.flush()
            show_cursor()
            print("Đã thoát.")
            return


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="git acc",
        description="Tiện ích tương tác quản lý và chuyển đổi danh tính Git commit (user.name & user.email).",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Hiển thị danh sách tài khoản đã cấu hình (non-interactive).",
    )
    parser.add_argument(
        "-c",
        "--current",
        action="store_true",
        help="Hiển thị danh tính Git global đang kích hoạt.",
    )

    args = parser.parse_args()

    if args.list:
        list_accounts_cli()
        return

    if args.current:
        show_current_cli()
        return

    interactive_menu()


if __name__ == "__main__":
    main()
