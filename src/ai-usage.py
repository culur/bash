#!/usr/bin/env python3
import atexit
import itertools
import json
import os
import re
import select
import subprocess
import sys
import termios
import time
import tty

# Configuration
PID = os.getpid()
TMUX_SESSION = f"ai_usage_{PID}"
TMUX_CMD = f"tmux new-session -d -s {TMUX_SESSION} -x 120 -y 40 agy"
HISTORY_FILE = os.path.expanduser("~/.gemini/antigravity-cli/history.jsonl")
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-cli/brain")

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[90m"
C_CYAN = "\033[36m"
C_BOLD_CYAN = "\033[1;36m"
C_BOLD_WHITE = "\033[1;37m"
C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_BOLD_RED = "\033[1;31m"
C_BOLD_GREEN = "\033[1;32m"
C_BOLD_GRAY = "\033[1;90m"
C_UNDERLINE = "\033[4m"
C_CLEAR = "\033[2J\033[H"  # Clear screen and move to top


def get_latest_token_prompt_info():
    """
    Returns (conversationId, timestamp) for the latest token-consuming prompt in history.jsonl.
    Ignores slash commands like /usage, /model, /help, etc. which do not consume model tokens.
    """
    if not os.path.exists(HISTORY_FILE):
        return None, None

    try:
        with open(HISTORY_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            read_size = min(size, 8192)
            f.seek(size - read_size)
            chunk = f.read().decode("utf-8", errors="ignore")
            lines = chunk.splitlines()

            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "conversationId" in data and data.get("type") != "slash_command":
                        cid = data.get("conversationId")
                        ts = data.get("timestamp")
                        return cid, ts
                except (ValueError, TypeError, KeyError):
                    continue
    except (OSError, UnicodeDecodeError):
        pass
    return None, None


def get_latest_token_prompt_id():
    cid, ts = get_latest_token_prompt_info()
    if cid and ts:
        return f"{cid}_{ts}"
    return None


def is_model_completed(data: dict) -> bool:
    if (
        data.get("source") != "MODEL"
        or data.get("type") != "PLANNER_RESPONSE"
        or data.get("status") != "DONE"
    ):
        return False

    if data.get("tool_calls"):
        return False

    if "content" in data and isinstance(data["content"], str):
        return True

    return "content" not in data and "tool_calls" not in data


class TranscriptWatcher:
    def __init__(self, timeout_sec=120.0):
        self.timeout_sec = timeout_sec
        self.active_transcripts = {}

    def track(self, conversation_id):
        if not conversation_id:
            return

        transcript_path = os.path.join(
            BRAIN_DIR, conversation_id, ".system_generated", "logs", "transcript.jsonl"
        )
        initial_offset = 0
        if os.path.exists(transcript_path):
            try:
                initial_offset = os.path.getsize(transcript_path)
            except OSError:
                initial_offset = 0

        self.active_transcripts[conversation_id] = {
            "path": transcript_path,
            "offset": initial_offset,
            "last_activity": time.time(),
        }

    def check_completions(self):
        """
        Polls active transcripts. Returns True if any conversation
        completed normally OR timed out (which triggers a second /usage query).
        """
        completed = False
        to_remove = []
        now = time.time()

        for cid, info in list(self.active_transcripts.items()):
            path = info["path"]
            offset = info["offset"]

            if not os.path.exists(path):
                if now - info["last_activity"] > self.timeout_sec:
                    to_remove.append(cid)
                    completed = True
                continue

            try:
                cur_size = os.path.getsize(path)
                if cur_size > offset:
                    info["last_activity"] = now  # Reset sliding 120s timeout!
                    with open(path, "rb") as f:
                        f.seek(offset)
                        chunk = f.read(cur_size - offset).decode(
                            "utf-8", errors="ignore"
                        )
                        info["offset"] = cur_size

                    lines = chunk.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if is_model_completed(data):
                                to_remove.append(cid)
                                completed = True
                                break
                        except (ValueError, TypeError, KeyError):
                            continue
            except (OSError, UnicodeDecodeError):
                pass

            if cid not in to_remove and (
                now - info["last_activity"] > self.timeout_sec
            ):
                to_remove.append(cid)
                completed = True

        for cid in to_remove:
            self.active_transcripts.pop(cid, None)

        return completed


def cleanup():
    # Kill tmux session
    subprocess.run(
        ["tmux", "kill-session", "-t", TMUX_SESSION],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    # Ensure cursor is visible
    sys.stdout.write("\033[?25h")
    # Exit alternate screen buffer
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()


atexit.register(cleanup)


def enter_alt_screen():
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)


def tmux_send_keys(keys):
    run_cmd(f"tmux send-keys -t {TMUX_SESSION} {keys}")


def tmux_capture():
    res = run_cmd(f"tmux capture-pane -t {TMUX_SESSION} -p")
    return res.stdout


def extract_header(text):
    ver_match = re.search(r"(Antigravity CLI [\d\.]+)", text)
    version = ver_match.group(1) if ver_match else "Antigravity CLI Unknown"

    email_match = re.search(
        r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+(?:\s+\(.*?\))?)", text
    )
    email = email_match.group(1) if email_match else "Unknown Account"

    return version, email


def format_duration(seconds):
    seconds = max(seconds, 0)
    total_hours = int(seconds // 3600)
    days = total_hours // 24
    rem_hours = total_hours % 24
    if days > 0:
        return f"{total_hours}h ({days}d {rem_hours}h)"
    else:
        rem_mins = int((seconds % 3600) // 60)
        return f"{total_hours}h {rem_mins}m"


def draw_progress_bar(pct, width=50, highlight_start=None, highlight_color=C_RED):
    pct_clamped = max(0.0, min(100.0, pct))
    filled_len = round(width * pct_clamped / 100.0)
    empty_len = width - filled_len

    if highlight_start is not None and highlight_start < filled_len:
        normal_len = highlight_start
        extra_len = filled_len - highlight_start
        bar = (
            f"{C_GREEN}"
            + ("█" * normal_len)
            + f"{highlight_color}"
            + ("█" * extra_len)
            + f"{C_DIM}"
            + ("░" * empty_len)
            + f"{C_RESET}"
        )
    else:
        bar = (
            f"{C_GREEN}"
            + ("█" * filled_len)
            + f"{C_DIM}"
            + ("░" * empty_len)
            + f"{C_RESET}"
        )

    return f"[{bar}] {pct_clamped:.2f}%"


def parse_time_to_sec(time_str):
    hours = 0
    minutes = 0
    h_match = re.search(r"(\d+)h", time_str)
    if h_match:
        hours = int(h_match.group(1))
    m_match = re.search(r"(\d+)m", time_str)
    if m_match:
        minutes = int(m_match.group(1))
    return hours * 3600 + minutes * 60


def parse_all_usage(text):
    groups = ["GEMINI MODELS", "CLAUDE AND GPT MODELS"]
    all_data = {}

    for group in groups:
        group_start = text.find(group)
        if group_start == -1:
            continue

        next_group = text.find("MODELS", group_start + len(group))
        if next_group != -1:
            block = text[group_start:next_group]
        else:
            block = text[group_start:]

        data = {}
        # Try parsing Weekly Limit
        weekly_pct_match = re.search(
            r"Weekly Limit.*?(?:\[.*?\])\s*([\d\.]+)%", block, re.DOTALL
        )
        if weekly_pct_match:
            data["weekly_limit_pct"] = float(weekly_pct_match.group(1))
            weekly_block = block[weekly_pct_match.end() :]

            fiveh_start = weekly_block.find("Five Hour Limit")
            w_subblock = (
                weekly_block[:fiveh_start] if fiveh_start != -1 else weekly_block
            )

            rem_match = re.search(r"(\d+% remaining|Quota available)", w_subblock)
            ref_match = re.search(
                r"Refreshes in\s+((?:(\d+)h\s*)?(?:(\d+)m)?)", w_subblock
            )

            if rem_match:
                data["weekly_rem_str"] = rem_match.group(1)
            else:
                data["weekly_rem_str"] = f"{int(data['weekly_limit_pct'])}% remaining"

            if ref_match:
                ref_str = ref_match.group(1).strip()
                data["weekly_ref_str"] = f"Refreshes in {ref_str}"
                data["weekly_ref_sec"] = parse_time_to_sec(ref_str)
            else:
                data["weekly_ref_str"] = ""
                data["weekly_ref_sec"] = 0

        # Try parsing Five Hour Limit
        fiveh_pct_match = re.search(
            r"Five Hour Limit.*?(?:\[.*?\])\s*([\d\.]+)%", block, re.DOTALL
        )
        if fiveh_pct_match:
            data["fiveh_limit_pct"] = float(fiveh_pct_match.group(1))
            fiveh_block = block[fiveh_pct_match.end() :]

            rem_match = re.search(r"(\d+% remaining|Quota available)", fiveh_block)
            ref_match = re.search(
                r"Refreshes in\s+((?:(\d+)h\s*)?(?:(\d+)m)?)", fiveh_block
            )

            if rem_match:
                data["fiveh_rem_str"] = rem_match.group(1)
            else:
                data["fiveh_rem_str"] = f"{int(data['fiveh_limit_pct'])}% remaining"

            if ref_match:
                ref_str = ref_match.group(1).strip()
                data["fiveh_ref_str"] = f"Refreshes in {ref_str}"
                data["fiveh_ref_sec"] = parse_time_to_sec(ref_str)
            else:
                data["fiveh_ref_str"] = ""
                data["fiveh_ref_sec"] = 0

        if data:
            mod_match = re.search(r"Models within this group:\s*(.*)", block)
            if mod_match:
                data["models_str"] = mod_match.group(1).strip()
            else:
                data["models_str"] = ""
            all_data[group] = data

    return all_data


def calculate_metrics_for_group(data):
    metrics = {}
    metrics["models_str"] = data.get("models_str", "")

    if "weekly_limit_pct" in data:
        limit_pct = data["weekly_limit_pct"]
        ref_sec = data.get("weekly_ref_sec", 0)
        total_cycle = 7 * 24 * 3600
        passed_sec = max(0, total_cycle - ref_sec)
        used_pct = 100.0 - limit_pct
        passed_pct = (passed_sec / total_cycle) * 100.0 if total_cycle else 0
        rem_time_pct = (ref_sec / total_cycle) * 100.0 if total_cycle else 0
        pct_diff = used_pct - passed_pct

        metrics["weekly"] = {
            "limit_pct": limit_pct,
            "rem_str": data.get("weekly_rem_str", ""),
            "ref_str": data.get("weekly_ref_str", ""),
            "rem_time_pct": rem_time_pct,
            "passed_sec": passed_sec,
            "ref_sec": ref_sec,
            "initial_ref_sec": ref_sec,
            "pct_diff": pct_diff,
        }

    if "fiveh_limit_pct" in data:
        limit_pct = data["fiveh_limit_pct"]
        ref_sec = data.get("fiveh_ref_sec", 0)
        total_cycle = 5 * 3600
        passed_sec = max(0, total_cycle - ref_sec)
        used_pct = 100.0 - limit_pct
        passed_pct = (passed_sec / total_cycle) * 100.0 if total_cycle else 0
        rem_time_pct = (ref_sec / total_cycle) * 100.0 if total_cycle else 0
        pct_diff = used_pct - passed_pct

        metrics["fiveh"] = {
            "limit_pct": limit_pct,
            "rem_str": data.get("fiveh_rem_str", ""),
            "ref_str": data.get("fiveh_ref_str", ""),
            "rem_time_pct": rem_time_pct,
            "passed_sec": passed_sec,
            "ref_sec": ref_sec,
            "initial_ref_sec": ref_sec,
            "pct_diff": pct_diff,
        }

    return metrics


def recompute_dynamic_metrics(all_metrics, now_time):
    updated_metrics = {}
    for group, data in all_metrics.items():
        group_copy = dict(data)
        fetch_time = group_copy.get("fetch_time", now_time)
        delta_sec = max(0, int(now_time - fetch_time))

        if "weekly" in group_copy:
            w = dict(group_copy["weekly"])
            initial_ref = w.get("initial_ref_sec", w.get("ref_sec", 0))
            if initial_ref > 0:
                total_cycle = 7 * 24 * 3600
                cur_ref = max(0, initial_ref - delta_sec)
                cur_passed = max(0, total_cycle - cur_ref)
                limit_pct = w["limit_pct"]
                used_pct = 100.0 - limit_pct
                passed_pct = (cur_passed / total_cycle) * 100.0 if total_cycle else 0
                rem_time_pct = (cur_ref / total_cycle) * 100.0 if total_cycle else 0
                pct_diff = used_pct - passed_pct

                w["ref_sec"] = cur_ref
                w["passed_sec"] = cur_passed
                w["rem_time_pct"] = rem_time_pct
                w["pct_diff"] = pct_diff
            group_copy["weekly"] = w

        if "fiveh" in group_copy:
            f = dict(group_copy["fiveh"])
            initial_ref = f.get("initial_ref_sec", f.get("ref_sec", 0))
            if initial_ref > 0:
                total_cycle = 5 * 3600
                cur_ref = max(0, initial_ref - delta_sec)
                cur_passed = max(0, total_cycle - cur_ref)
                limit_pct = f["limit_pct"]
                used_pct = 100.0 - limit_pct
                passed_pct = (cur_passed / total_cycle) * 100.0 if total_cycle else 0
                rem_time_pct = (cur_ref / total_cycle) * 100.0 if total_cycle else 0
                pct_diff = used_pct - passed_pct

                f["ref_sec"] = cur_ref
                f["passed_sec"] = cur_passed
                f["rem_time_pct"] = rem_time_pct
                f["pct_diff"] = pct_diff
            group_copy["fiveh"] = f

        updated_metrics[group] = group_copy
    return updated_metrics


def render_tui(all_metrics, header_info, current_group, show_five_hour, status=""):
    version, email = header_info

    out = [C_CLEAR, f"{C_BOLD_CYAN}AI Usage CLI{C_RESET}"]
    out.append("")
    out.append(f"{C_BOLD_WHITE}{version}{C_RESET}")
    out.append(f"{C_DIM}{email}{C_RESET}")
    out.append("")

    # Prepare Tab labels
    groups = ["GEMINI MODELS", "CLAUDE AND GPT MODELS"]
    tab_labels = []

    for g in groups:
        if g in all_metrics and "weekly" in all_metrics[g]:
            w = all_metrics[g]["weekly"]
            # Color logic based on pct_diff
            pct_color = C_GREEN if w["pct_diff"] <= 0 else C_RED

            if g == current_group:
                group_text = f"{C_UNDERLINE}{C_BOLD_CYAN}{g}{C_RESET}"
            else:
                group_text = f"{C_BOLD_GRAY}{g}{C_RESET}"

            label = f"{group_text} {C_DIM}({C_RESET}{pct_color}{w['limit_pct']:.2f}%{C_RESET}{C_DIM}){C_RESET}"
            tab_labels.append(label)
        else:
            # Fallback if no data
            if g == current_group:
                group_text = f"{C_UNDERLINE}{C_BOLD_CYAN}{g}{C_RESET}"
            else:
                group_text = f"{C_BOLD_GRAY}{g}{C_RESET}"

            label = f"{group_text} {C_DIM}(?%){C_RESET}"
            tab_labels.append(label)

    out.append(" | ".join(tab_labels))

    if current_group in all_metrics:
        metrics = all_metrics[current_group]

        if metrics["models_str"]:
            out.append(
                f"  {C_DIM}Models within this group: {metrics['models_str']}{C_RESET}"
            )
            out.append("")

        width = 50
        if "weekly" in metrics:
            w = metrics["weekly"]
            filled_limit = round(width * max(0.0, min(100.0, w["limit_pct"])) / 100.0)
            filled_remaining = round(
                width * max(0.0, min(100.0, w["rem_time_pct"])) / 100.0
            )

            if filled_remaining > filled_limit:
                limit_bar = draw_progress_bar(w["limit_pct"], width=width)
                remaining_bar = draw_progress_bar(
                    w["rem_time_pct"],
                    width=width,
                    highlight_start=filled_limit,
                    highlight_color=C_RED,
                )
            elif filled_limit > filled_remaining:
                limit_bar = draw_progress_bar(
                    w["limit_pct"],
                    width=width,
                    highlight_start=filled_remaining,
                    highlight_color=C_CYAN,
                )
                remaining_bar = draw_progress_bar(w["rem_time_pct"], width=width)
            else:
                limit_bar = draw_progress_bar(w["limit_pct"], width=width)
                remaining_bar = draw_progress_bar(w["rem_time_pct"], width=width)

            out.append(f"  {C_BOLD_WHITE}Weekly Limit{C_RESET}")
            out.append("  " + limit_bar)
            if w["ref_str"]:
                out.append(f"    {C_DIM}{w['rem_str']} · {w['ref_str']}{C_RESET}")
            else:
                out.append(f"    {C_DIM}{w['rem_str']}{C_RESET}")
            out.append("")
            out.append(f"  {C_BOLD_WHITE}Weekly Remaining{C_RESET}")
            out.append("  " + remaining_bar)

            if w["ref_sec"] > 0:
                out.append(
                    f"  {C_DIM}Passed: {format_duration(w['passed_sec'])} · Remaining: {format_duration(w['ref_sec'])}{C_RESET}"
                )
                if w["pct_diff"] > 0:
                    out.append(
                        f"  You are using tokens {C_BOLD_RED}{w['pct_diff']:.2f}%{C_RESET} {C_BOLD_RED}faster{C_RESET} than time elapsed ({C_BOLD_RED}be careful, might run out!{C_RESET})"
                    )
                else:
                    out.append(
                        f"  You are using tokens {C_BOLD_GREEN}{abs(w['pct_diff']):.2f}%{C_RESET} {C_BOLD_GREEN}slower{C_RESET} than time elapsed ({C_BOLD_GREEN}keep going!{C_RESET})"
                    )
            out.append("")

        if show_five_hour and "fiveh" in metrics:
            f = metrics["fiveh"]
            filled_limit = round(width * max(0.0, min(100.0, f["limit_pct"])) / 100.0)
            filled_remaining = round(
                width * max(0.0, min(100.0, f["rem_time_pct"])) / 100.0
            )

            if filled_remaining > filled_limit:
                limit_bar = draw_progress_bar(f["limit_pct"], width=width)
                remaining_bar = draw_progress_bar(
                    f["rem_time_pct"],
                    width=width,
                    highlight_start=filled_limit,
                    highlight_color=C_RED,
                )
            elif filled_limit > filled_remaining:
                limit_bar = draw_progress_bar(
                    f["limit_pct"],
                    width=width,
                    highlight_start=filled_remaining,
                    highlight_color=C_CYAN,
                )
                remaining_bar = draw_progress_bar(f["rem_time_pct"], width=width)
            else:
                limit_bar = draw_progress_bar(f["limit_pct"], width=width)
                remaining_bar = draw_progress_bar(f["rem_time_pct"], width=width)

            out.append(f"  {C_BOLD_WHITE}Five Hour Limit{C_RESET}")
            out.append("  " + limit_bar)
            if f["ref_str"]:
                out.append(f"    {C_DIM}{f['rem_str']} · {f['ref_str']}{C_RESET}")
            else:
                out.append(f"    {C_DIM}{f['rem_str']}{C_RESET}")
            out.append("")
            out.append(f"  {C_BOLD_WHITE}Five Hour Remaining{C_RESET}")
            out.append("  " + remaining_bar)

            if f["ref_sec"] > 0:
                out.append(
                    f"  {C_DIM}Passed: {format_duration(f['passed_sec'])} · Remaining: {format_duration(f['ref_sec'])}{C_RESET}"
                )
                if f["pct_diff"] > 0:
                    out.append(
                        f"  You are using tokens {C_BOLD_RED}{f['pct_diff']:.2f}%{C_RESET} {C_BOLD_RED}faster{C_RESET} than time elapsed ({C_BOLD_RED}be careful, might run out!{C_RESET})"
                    )
                else:
                    out.append(
                        f"  You are using tokens {C_BOLD_GREEN}{abs(f['pct_diff']):.2f}%{C_RESET} {C_BOLD_GREEN}slower{C_RESET} than time elapsed ({C_BOLD_GREEN}keep going!{C_RESET})"
                    )
            out.append("")

    if not all_metrics:
        out.append(f"  {C_DIM}No limit data found yet. Press 'r' to refresh.{C_RESET}")
        out.append("")

    out.append(
        f"{C_DIM}────────────────────────────────────────────────────────────{C_RESET}"
    )
    out.append(
        f"{C_CYAN}[tab]{C_RESET} Switch Group · {C_CYAN}[f]{C_RESET} Toggle 5-Hour Limit"
    )
    out.append(
        f"{C_CYAN}[r]{C_RESET} or {C_CYAN}[enter]{C_RESET} Refresh · {C_CYAN}[esc]{C_RESET} Exit"
    )
    out.append("")
    if status:
        out.append(status)
    else:
        out.append("")  # padding

    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()


def spinner_wait(
    message, condition_func=None, timeout=5.0, check_interval=0.1, render_func=None
):
    spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
    start = time.time()
    sys.stdout.write("\033[?25l")  # hide cursor
    while time.time() - start < timeout:
        spin_char = next(spinner)
        if condition_func:
            res = condition_func()
            if res:
                if render_func is None:
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                return res
        if render_func:
            render_func(spin_char)
        else:
            sys.stdout.write(f"\r{C_CYAN}{spin_char}{C_RESET} {message}")
            sys.stdout.flush()
        time.sleep(check_interval)
    if render_func is None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
    return None


def main():
    enter_alt_screen()

    sys.stdout.write(f"{C_CLEAR}")
    sys.stdout.flush()

    def check_tmux():
        run_cmd(TMUX_CMD)
        return True

    spinner_wait("Starting tmux session...", check_tmux, timeout=1.0)

    def check_sign_in():
        out = tmux_capture()
        if "Do you trust" in out:
            tmux_send_keys("Enter")
        return ("Signing in" not in out) and (">" in out or "Gemini" in out)

    spinner_wait("Waiting for agy sign-in...", check_sign_in, timeout=30.0)

    out_capture = []

    def check_package():
        out = tmux_capture()
        if re.search(
            r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\s+\(.*?\))", out
        ):
            out_capture.append(out)
            return True
        out_capture.append(out)
        return False

    spinner_wait("Loading account profile...", check_package, timeout=5.0)

    if out_capture:
        out = out_capture[-1]
    else:
        out = tmux_capture()

    header_info = list(extract_header(out))

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    sys.stdout.write("\033[?25l")  # hide cursor
    sys.stdout.flush()

    try:
        tty.setcbreak(fd)

        all_metrics = {}
        current_group = "GEMINI MODELS"
        show_five_hour = False

        def refresh_data(is_initial=False):
            def do_render(spin_char):
                render_tui(
                    recompute_dynamic_metrics(all_metrics, time.time()),
                    header_info,
                    current_group,
                    show_five_hour,
                    status=f"{C_CYAN}{spin_char} Refreshing...{C_RESET}",
                )

            tmux_send_keys("Escape")
            spinner_wait("Refreshing...", timeout=0.5, render_func=do_render)
            tmux_send_keys("'/usage' Enter")
            spinner_wait("Refreshing...", timeout=0.5, render_func=do_render)

            def check_usage():
                text = tmux_capture()
                if "Weekly Limit" in text:
                    return text
                return None

            text = spinner_wait(
                "Refreshing...", check_usage, timeout=10.0, render_func=do_render
            )
            if not text:
                text = tmux_capture()

            data = parse_all_usage(text)
            now_time = time.time()
            res = {}
            for k, v in data.items():
                m = calculate_metrics_for_group(v)
                m["fetch_time"] = now_time
                res[k] = m
            return res

        all_metrics = refresh_data(is_initial=True)
        watcher = TranscriptWatcher(timeout_sec=120.0)

        cid_init, ts_init = get_latest_token_prompt_info()
        last_token_prompt_id = (
            f"{cid_init}_{ts_init}" if (cid_init and ts_init) else None
        )

        esc_pending = False
        last_rendered_sec = -1
        need_rerender = True

        while True:
            now_time = time.time()
            current_sec = int(now_time)

            # 1. Check if a new token-consuming prompt occurred in history.jsonl
            cid_cur, ts_cur = get_latest_token_prompt_info()
            current_token_prompt_id = (
                f"{cid_cur}_{ts_cur}" if (cid_cur and ts_cur) else None
            )

            if (
                last_token_prompt_id is not None
                and current_token_prompt_id is not None
                and current_token_prompt_id != last_token_prompt_id
            ):
                last_token_prompt_id = current_token_prompt_id
                if cid_cur:
                    watcher.track(cid_cur)
                esc_pending = False
                all_metrics = refresh_data(is_initial=False)
                last_rendered_sec = -1
                need_rerender = True
                continue
            elif last_token_prompt_id is None and current_token_prompt_id is not None:
                last_token_prompt_id = current_token_prompt_id
                if cid_cur:
                    watcher.track(cid_cur)

            # 2. Check if any active transcript completed or timed out (120s silence)
            if watcher.check_completions():
                esc_pending = False
                all_metrics = refresh_data(is_initial=False)
                last_rendered_sec = -1
                need_rerender = True
                continue

            # 3. Check if quota reset timer reached 0
            dynamic_metrics = recompute_dynamic_metrics(all_metrics, now_time)
            quota_expired = False
            for g_m in dynamic_metrics.values():
                for limit_key in ("weekly", "fiveh"):
                    if limit_key in g_m:
                        lim = g_m[limit_key]
                        if (
                            lim.get("initial_ref_sec", 0) > 0
                            and lim.get("ref_sec", 0) == 0
                            and now_time - g_m.get("fetch_time", 0) > 5
                        ):
                            quota_expired = True
                            break
                if quota_expired:
                    break

            if quota_expired:
                esc_pending = False
                all_metrics = refresh_data(is_initial=False)
                last_rendered_sec = -1
                need_rerender = True
                continue

            # 3. Check if second changed or rerender needed
            if current_sec != last_rendered_sec or need_rerender:
                last_rendered_sec = current_sec
                need_rerender = False

                status_str = (
                    f"{C_DIM}⠿ Live (watching history.jsonl){C_RESET} {C_RED}(Press Esc again to exit){C_RESET}"
                    if esc_pending
                    else f"{C_DIM}⠿ Live (watching history.jsonl){C_RESET}"
                )

                render_tui(
                    dynamic_metrics,
                    header_info,
                    current_group,
                    show_five_hour,
                    status=status_str,
                )

            # 4. Non-blocking input listen with 0.1s timeout
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                ch = sys.stdin.read(1)
                if ch == "\x1b":  # Esc
                    r_sub, _, _ = select.select([sys.stdin], [], [], 0.01)
                    if r_sub:
                        sys.stdin.read(1)
                        r_sub2, _, _ = select.select([sys.stdin], [], [], 0.01)
                        if r_sub2:
                            sys.stdin.read(1)
                        esc_pending = False
                        need_rerender = True
                        continue

                    if esc_pending:
                        break  # Exit
                    else:
                        esc_pending = True
                        need_rerender = True
                        continue
                elif ch == "\t":
                    current_group = (
                        "CLAUDE AND GPT MODELS"
                        if current_group == "GEMINI MODELS"
                        else "GEMINI MODELS"
                    )
                    esc_pending = False
                    need_rerender = True
                    continue
                elif ch.lower() == "f":
                    show_five_hour = not show_five_hour
                    esc_pending = False
                    need_rerender = True
                    continue
                elif ch.lower() == "r" or ch in ("\n", "\r"):
                    esc_pending = False
                    all_metrics = refresh_data(is_initial=False)
                    last_token_prompt_id = get_latest_token_prompt_id()
                    last_rendered_sec = -1
                    need_rerender = True
                    continue
                else:
                    esc_pending = False
                    need_rerender = True
                    continue

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
