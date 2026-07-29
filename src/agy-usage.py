#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import threading
import time

mock_mode = False
cache_mode = False
for arg in sys.argv[1:]:
    if arg == "--mock":
        mock_mode = True
    elif arg in ("-c", "--cache"):
        cache_mode = True

CACHE_FILE = os.path.expanduser("~/.cache/agy_usage_cache.json")

# ANSI Color Definitions
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[90m"
C_CYAN = "\033[36m"
C_BOLD_CYAN = "\033[1;36m"
C_BOLD_WHITE = "\033[1;37m"
C_GREEN = "\033[32m"
C_BOLD_GREEN = "\033[1;32m"
C_RED = "\033[31m"
C_BOLD_RED = "\033[1;31m"

class StatusSpinner:
    def __init__(self, step_tag, msg):
        self.step_tag = step_tag
        self.msg = msg
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.stop_event = threading.Event()
        self.thread = None

    def _spin(self):
        idx = 0
        while not self.stop_event.is_set():
            frame = self.frames[idx % len(self.frames)]
            sys.stderr.write(f"\r\033[K{C_BOLD_CYAN}{self.step_tag}{C_RESET} {C_CYAN}{frame}{C_RESET} {C_DIM}{self.msg}{C_RESET}")
            sys.stderr.flush()
            idx += 1
            time.sleep(0.08)

    def __enter__(self):
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        if exc_type is None:
            sys.stderr.write(f"\r\033[K{C_BOLD_CYAN}{self.step_tag}{C_RESET} {C_GREEN}✓{C_RESET} {C_DIM}{self.msg}{C_RESET}\n")
        else:
            sys.stderr.write(f"\r\033[K{C_BOLD_CYAN}{self.step_tag}{C_RESET} {C_RED}✗{C_RESET} {C_DIM}{self.msg}{C_RESET}\n")
        sys.stderr.flush()

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None

def save_cache(reset_timestamp, captured_timestamp):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        data = {
            "reset_timestamp": reset_timestamp,
            "captured_timestamp": captured_timestamp,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except (OSError, TypeError) as e:
        sys.stderr.write(f"{C_DIM}Warning: Could not save cache: {e}{C_RESET}\n")

def format_ago(seconds):
    total_seconds = int(max(0, seconds))
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    total_minutes = total_seconds // 60
    days = total_minutes // (24 * 60)
    rem_minutes = total_minutes % (24 * 60)
    hours = rem_minutes // 60
    mins = rem_minutes % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0 or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts) + " ago"

def format_diff_duration(seconds):
    total_seconds = int(abs(seconds))
    total_minutes = total_seconds // 60
    days = total_minutes // (24 * 60)
    rem_minutes = total_minutes % (24 * 60)
    hours = rem_minutes // 60
    mins = rem_minutes % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0 and days == 0:
        parts.append(f"{mins}m")
    if not parts:
        parts.append("0m")
    return " ".join(parts)

def draw_progress_bar(pct, width=50, indent="  ", highlight_start=None, highlight_color=C_RED):
    pct_clamped = max(0.0, min(100.0, pct))
    filled_len = round(width * pct_clamped / 100.0)
    empty_len = width - filled_len

    if highlight_start is not None and highlight_start < filled_len:
        normal_len = highlight_start
        extra_len = filled_len - highlight_start
        bar = (
            f"{C_GREEN}" + ("█" * normal_len) +
            f"{highlight_color}" + ("█" * extra_len) +
            f"{C_DIM}" + ("░" * empty_len) + f"{C_RESET}"
        )
    else:
        bar = f"{C_GREEN}" + ("█" * filled_len) + f"{C_DIM}" + ("░" * empty_len) + f"{C_RESET}"

    return f"{indent}[{bar}] {C_BOLD}{pct_clamped:.2f}%{C_RESET}"

def format_duration(seconds):
    total_hours = int(seconds // 3600)
    days = total_hours // 24
    rem_hours = total_hours % 24
    return f"{total_hours}h ({days}d {rem_hours}h)"

def capture_tui_screen():
    session_name = f"agy_usage_{os.getpid()}"

    try:
        with StatusSpinner("[1/4]", "Starting headless tmux session..."):
            subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-x", "120", "-y", "40", "agy"], check=True)

        with StatusSpinner("[2/4]", "Launching agy CLI and waiting for sign-in..."):
            ready = False
            for _ in range(20):
                time.sleep(0.5)
                out = subprocess.check_output(["tmux", "capture-pane", "-t", session_name, "-p"]).decode("utf-8")
                if "Do you trust" in out:
                    subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], check=True)
                if "Signing in" not in out and ("Gemini" in out or ">" in out):
                    ready = True
                    break

            if not ready:
                raise RuntimeError("Timeout waiting for agy CLI to sign in and be ready.")

        with StatusSpinner("[3/4]", "Querying usage via /usage command..."):
            subprocess.run(["tmux", "send-keys", "-t", session_name, "/usage", "Enter"], check=True)

        with StatusSpinner("[4/4]", "Capturing screen and parsing quota metrics..."):
            usage_captured = ""
            for _ in range(15):
                time.sleep(0.5)
                out = subprocess.check_output(["tmux", "capture-pane", "-t", session_name, "-p"]).decode("utf-8")
                if "Weekly Limit" in out:
                    usage_captured = out
                    break

            subprocess.run(["tmux", "kill-session", "-t", session_name], stderr=subprocess.DEVNULL, check=False)

            if not usage_captured:
                raise RuntimeError("Failed to capture /usage screen output.")

        return usage_captured

    except Exception as e:  # noqa: BLE001
        subprocess.run(["tmux", "kill-session", "-t", session_name], stderr=subprocess.DEVNULL, check=False)
        sys.stderr.write(f"\n{C_BOLD_RED}Error capturing TUI screen via tmux: {e}{C_RESET}\n")
        sys.exit(1)

def parse_usage_text(text):
    gemini_section = text.split("CLAUDE AND GPT MODELS")[0] if "CLAUDE AND GPT MODELS" in text else text
    match_pct = re.search(r"Weekly Limit\s+\[.*?\]\s+([\d\.]+)%", gemini_section)
    match_refresh = re.search(r"Refreshes in\s+((?:(\d+)h\s*)?(?:(\d+)m)?)", gemini_section)

    if not match_pct or not match_refresh:
        sys.stderr.write(f"{C_BOLD_RED}Failed to parse usage data from TUI output.{C_RESET}\n")
        sys.stderr.write("Raw Screen Capture:\n" + text + "\n")
        sys.exit(1)

    rem_limit_pct = float(match_pct.group(1))

    hours = int(match_refresh.group(2)) if match_refresh.group(2) else 0
    minutes = int(match_refresh.group(3)) if match_refresh.group(3) else 0
    rem_sec = float(hours * 3600 + minutes * 60)

    return rem_limit_pct, rem_sec

def main():
    total_cycle_sec = 7 * 24 * 3600

    if cache_mode:
        cache_data = load_cache()
        if not cache_data or "reset_timestamp" not in cache_data:
            sys.stderr.write(f"{C_BOLD_RED}No cache found. Please run 'agy-usage' without -c first.{C_RESET}\n")
            sys.exit(1)

        reset_ts = cache_data["reset_timestamp"]
        captured_ts = cache_data.get("captured_timestamp", time.time())
        now = time.time()
        rem_sec = reset_ts - now

        if rem_sec <= 0:
            sys.stderr.write(f"{C_BOLD_RED}Cache expired. Please run 'agy-usage' without -c to fetch latest data directly from agy CLI.{C_RESET}\n")
            sys.exit(1)

        rem_sec = min(float(total_cycle_sec), max(0.0, rem_sec))
        passed_sec = total_cycle_sec - rem_sec
        rem_time_pct = (rem_sec / float(total_cycle_sec)) * 100.0
        ago_str = format_ago(now - captured_ts)

        print()
        print(f"{C_BOLD_WHITE}Weekly Remaining{C_RESET}")
        print(draw_progress_bar(rem_time_pct))
        print(f"  {C_GREEN}Passed: {format_duration(passed_sec)} · Remaining: {format_duration(rem_sec)}{C_RESET}")
        print()
        print(f"  {C_DIM}Reset time is cached information from previous query (queried {ago_str}){C_RESET}")
        print()
        sys.exit(0)

    if mock_mode:
        with StatusSpinner("[1/4]", "Starting headless tmux session..."):
            time.sleep(0.3)
        with StatusSpinner("[2/4]", "Launching agy CLI and waiting for sign-in..."):
            time.sleep(0.4)
        with StatusSpinner("[3/4]", "Querying usage via /usage command..."):
            time.sleep(0.3)
        with StatusSpinner("[4/4]", "Capturing screen and parsing quota metrics..."):
            time.sleep(0.3)

        rem_limit_pct = 62.82
        rem_sec = 111 * 3600 + 15 * 60
    else:
        if subprocess.call(["which", "tmux"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            sys.stderr.write(f"{C_BOLD_RED}Error: 'tmux' is required for headless TUI screen capture.{C_RESET}\n")
            sys.exit(1)
        
        screen_text = capture_tui_screen()
        rem_limit_pct, rem_sec = parse_usage_text(screen_text)

    # Total 7-day weekly cycle: 168 hours = 604,800 seconds
    rem_sec = min(float(total_cycle_sec), max(0.0, rem_sec))
    passed_sec = total_cycle_sec - rem_sec

    used_pct = 100.0 - rem_limit_pct
    passed_pct = (passed_sec / float(total_cycle_sec)) * 100.0
    rem_time_pct = (rem_sec / float(total_cycle_sec)) * 100.0

    pct_diff = used_pct - passed_pct

    now = time.time()
    new_reset_ts = now + rem_sec

    cache_data = load_cache()
    reset_msg = None
    if cache_data and "reset_timestamp" in cache_data:
        old_reset_ts = cache_data["reset_timestamp"]
        diff_sec = new_reset_ts - old_reset_ts
        if diff_sec > 3600:
            diff_str = format_diff_duration(diff_sec)
            reset_msg = f"  {C_BOLD_RED}Reset time shifted {diff_str} later compared to previous query{C_RESET}"
        elif diff_sec < -3600:
            diff_str = format_diff_duration(abs(diff_sec))
            reset_msg = f"  {C_BOLD_GREEN}Reset time shifted {diff_str} earlier compared to previous query{C_RESET}"
        else:
            reset_msg = f"  {C_DIM}Reset time unchanged compared to previous query{C_RESET}"

    save_cache(new_reset_ts, now)

    width = 50
    filled_limit = round(width * max(0.0, min(100.0, rem_limit_pct)) / 100.0)
    filled_remaining = round(width * max(0.0, min(100.0, rem_time_pct)) / 100.0)

    if filled_remaining > filled_limit:
        limit_bar = draw_progress_bar(rem_limit_pct, width=width)
        remaining_bar = draw_progress_bar(
            rem_time_pct, width=width, highlight_start=filled_limit, highlight_color=C_RED
        )
    elif filled_limit > filled_remaining:
        limit_bar = draw_progress_bar(
            rem_limit_pct, width=width, highlight_start=filled_remaining, highlight_color=C_CYAN
        )
        remaining_bar = draw_progress_bar(rem_time_pct, width=width)
    else:
        limit_bar = draw_progress_bar(rem_limit_pct, width=width)
        remaining_bar = draw_progress_bar(rem_time_pct, width=width)

    print()
    print(f"{C_BOLD_WHITE}Weekly Limit{C_RESET}")
    print(limit_bar)
    print()
    print(f"{C_BOLD_WHITE}Weekly Remaining{C_RESET}")
    print(remaining_bar)
    print(f"  {C_GREEN}Passed: {format_duration(passed_sec)} · Remaining: {format_duration(rem_sec)}{C_RESET}")
    if reset_msg:
        print()
        print(reset_msg)
    print()

    if pct_diff > 0:
        print(f"  You are using tokens {C_BOLD_RED}{abs(pct_diff):.2f}%{C_RESET} {C_BOLD_RED}faster than time elapsed (be careful, might run out!){C_RESET}")
    else:
        print(f"  You are using tokens {C_BOLD_GREEN}{abs(pct_diff):.2f}%{C_RESET} {C_BOLD_GREEN}slower than time elapsed (keep going!){C_RESET}")
    print()

if __name__ == "__main__":
    main()
