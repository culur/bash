#!/usr/bin/env python3
import atexit
import itertools
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
            "pct_diff": pct_diff,
        }

    return metrics


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
    if status:
        out.append(f"{C_CYAN}{status}{C_RESET}")
    else:
        out.append("")  # padding

    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()


def spinner_wait(message, condition_func=None, timeout=5.0, check_interval=0.1):
    spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
    start = time.time()
    sys.stdout.write("\033[?25l")  # hide cursor
    while time.time() - start < timeout:
        if condition_func:
            res = condition_func()
            if res:
                sys.stdout.write("\r\033[K")  # clear line
                sys.stdout.flush()
                return res
        sys.stdout.write(f"\r{C_CYAN}{next(spinner)}{C_RESET} {message}")
        sys.stdout.flush()
        time.sleep(check_interval)
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

        def refresh_data(is_initial=False):
            msg = "Querying /usage..." if is_initial else "Refreshing..."

            tmux_send_keys("Escape")
            spinner_wait(msg, timeout=1.0)
            tmux_send_keys("'/usage' Enter")
            spinner_wait(msg, timeout=1.0)

            def check_usage():
                text = tmux_capture()
                if "Weekly Limit" in text:
                    return text
                return None

            text = spinner_wait(msg, check_usage, timeout=10.0)
            if not text:
                text = tmux_capture()

            data = parse_all_usage(text)
            return {k: calculate_metrics_for_group(v) for k, v in data.items()}

        all_metrics = refresh_data(is_initial=True)

        esc_pending = False
        current_group = "GEMINI MODELS"
        show_five_hour = False

        render_tui(all_metrics, header_info, current_group, show_five_hour)

        while True:
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
                        render_tui(
                            all_metrics, header_info, current_group, show_five_hour
                        )
                        continue

                    if esc_pending:
                        break  # Exit
                    else:
                        esc_pending = True
                        render_tui(
                            all_metrics,
                            header_info,
                            current_group,
                            show_five_hour,
                            status="Press Esc again to exit",
                        )
                        continue
                elif ch == "\t":
                    current_group = (
                        "CLAUDE AND GPT MODELS"
                        if current_group == "GEMINI MODELS"
                        else "GEMINI MODELS"
                    )
                    esc_pending = False
                    render_tui(all_metrics, header_info, current_group, show_five_hour)
                    continue
                elif ch.lower() == "f":
                    show_five_hour = not show_five_hour
                    esc_pending = False
                    render_tui(all_metrics, header_info, current_group, show_five_hour)
                    continue
                elif ch.lower() == "r" or ch in ("\n", "\r"):
                    esc_pending = False
                    all_metrics = refresh_data(is_initial=False)
                    render_tui(all_metrics, header_info, current_group, show_five_hour)
                    continue
                else:
                    esc_pending = False
                    render_tui(all_metrics, header_info, current_group, show_five_hour)
            else:
                pass

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
