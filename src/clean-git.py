#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "inquirerpy>=0.3.4",
#     "rich>=13.0.0",
# ]
# ///

import argparse
import contextlib
import fnmatch
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

# Fix Windows console UTF-8 encoding for Vietnamese & Unicode characters
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    os.system("")  # Enable VT100 / ANSI escape processing on Windows console

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console()


def format_size(bytes_size: int) -> str:
    """Format bytes into human-readable size (B, KB, MB, GB, TB)."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        bytes_size /= 1024.0
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
    return f"{bytes_size:.2f} PB"


def get_path_size(path: Path) -> int:
    """Calculate size of a file or directory recursively."""
    try:
        if not path.exists() and not path.is_symlink():
            return 0
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        total = 0
        for entry in path.rglob("*"):
            try:
                if entry.is_symlink() or entry.is_file():
                    total += entry.stat().st_size
            except (OSError, PermissionError):
                continue
        return total
    except (OSError, PermissionError):
        return 0


def safe_remove_path(path: Path) -> tuple[bool, str | None]:
    """Safely remove a file, symlink, or directory across Windows, macOS, and Linux."""
    try:
        if not path.exists() and not path.is_symlink():
            return True, None

        # Trường hợp Symlink (bao gồm Directory Symlink trên Windows)
        if path.is_symlink():
            path.unlink(missing_ok=True)
            return True, None

        if path.is_dir():
            def _remove_readonly(func, p, exc):
                with contextlib.suppress(OSError):
                    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                    func(p)

            shutil.rmtree(path, onexc=_remove_readonly)
            return True, None
        else:
            with contextlib.suppress(OSError):
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            path.unlink(missing_ok=True)
            return True, None
    except OSError as e:
        return False, str(e)


def check_git_repo() -> tuple[bool, str | None]:
    """Check if current directory is inside a valid git work tree and diagnose any errors."""
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=false", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return (
            False,
            (
                "[bold red]❌ Không tìm thấy lệnh 'git' trong PATH![/bold red]\n"
                "[yellow]Trên Windows, hãy cài Git bằng Scoop trước: scoop install git. "
                "Nếu không dùng được Scoop, dùng WinGet: winget install Git.Git. "
                "Sau đó đảm bảo git có trong biến môi trường PATH.[/yellow]"
            ),
        )
    except (subprocess.SubprocessError, OSError) as e:
        return False, f"[bold red]❌ Lỗi khi thực thi git:[/bold red] {e}"

    if res.returncode == 0 and res.stdout.strip() == "true":
        return True, None

    # Phân tích nguyên nhân lỗi cụ thể từ Git stderr
    err = res.stderr.strip() if res.stderr else "Không xác định"
    cwd = Path.cwd()
    dotgit_path = cwd / ".git"

    if "detected dubious ownership" in err:
        msg = (
            f"[bold yellow]⚠️ Phát hiện vấn đề quyền sở hữu Git repository (dubious ownership):[/bold yellow]\n"
            f"[white]{err}[/white]\n\n"
            f"[cyan]💡 Gợi ý khắc phục:[/cyan] Chạy lệnh sau để thêm thư mục này vào danh sách an toàn:\n"
            f"   [bold green]git config --global --add safe.directory \"{cwd.as_posix()}\"[/bold green]"
        )
    elif "bad object" in err or "corrupt" in err.lower():
        msg = (
            f"[bold red]❌ Git repository bị lỗi dữ liệu / hỏng commit object:[/bold red]\n"
            f"[white]{err}[/white]\n\n"
            f"[cyan]💡 Gợi ý khắc phục:[/cyan] Thư mục `.git` bị mất hoặc hỏng object (ví dụ thiếu objects/HEAD). "
            f"Thử kiểm tra lại hoặc clone lại repo."
        )
    elif dotgit_path.exists():
        dotgit_objects = dotgit_path / "objects"
        if not dotgit_objects.exists():
            msg = (
                f"[bold red]❌ Thư mục `.git` tồn tại nhưng thiếu thư mục dữ liệu `.git/objects`![/bold red]\n"
                f"[white]Chi tiết lỗi Git:[/white] {err}\n\n"
                f"[cyan]💡 Gợi ý khắc phục:[/cyan] Repository này đã bị xoá mất thư mục objects hoặc clone chưa hoàn tất. "
                f"Hãy clone lại repository hoặc khởi tạo lại bằng lệnh [bold green]git init[/bold green]."
            )
        else:
            msg = (
                f"[bold red]❌ Thư mục `.git` tồn tại nhưng Git không nhận diện được repository:[/bold red]\n"
                f"[white]Chi tiết lỗi Git:[/white] {err}"
            )
    else:
        msg = (
            f"[bold red]❌ Thư mục hiện tại không phải là Git repository![/bold red]\n"
            f"[dim]Chi tiết từ Git: {err}[/dim]"
        )

    return False, msg


def get_git_info() -> dict[str, Any]:
    """Collect comprehensive Git status information (remote, branch, tracking, ahead/behind, worktree)."""
    def _run_git(args: list[str]) -> tuple[bool, str, str]:
        try:
            r = subprocess.run(
                ["git", "-c", "core.quotepath=false"] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            return r.returncode == 0, r.stdout.rstrip("\r\n"), r.stderr.rstrip("\r\n")
        except (subprocess.SubprocessError, OSError) as e:
            return False, "", str(e)

    # 1. Remotes & Remote URLs
    ok_rem, rem_out, _ = _run_git(["remote", "-v"])
    remotes: dict[str, dict[str, str]] = {}
    if ok_rem and rem_out.strip():
        for line in rem_out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                name, url = parts[0], parts[1]
                t = parts[2] if len(parts) >= 3 else ""
                if name not in remotes:
                    remotes[name] = {}
                if "fetch" in t:
                    remotes[name]["fetch"] = url
                elif "push" in t:
                    remotes[name]["push"] = url
                else:
                    remotes[name]["url"] = url

    # 2. Branch & Detached HEAD detection
    ok_br, br_out, _ = _run_git(["branch", "--show-current"])
    branch = br_out.strip()
    is_detached = False
    if not ok_br or not branch:
        ok_sym, sym_name, _ = _run_git(["symbolic-ref", "--short", "HEAD"])
        if ok_sym and sym_name.strip():
            branch = sym_name.strip()
        else:
            ok_head, head_hash, _ = _run_git(["rev-parse", "--short", "HEAD"])
            if ok_head and head_hash.strip():
                branch = f"HEAD (detached at {head_hash.strip()})"
                is_detached = True
            else:
                branch = "Chưa có commit"

    # 3. Remote Tracking status & Ahead / Behind commit count
    upstream: str | None = None
    ahead = 0
    behind = 0
    has_upstream = False
    if not is_detached and branch not in ("Chưa có commit", "Không xác định", ""):
        ok_up, up_name, _ = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        if ok_up and up_name.strip():
            upstream = up_name.strip()
            has_upstream = True
            ok_cnt, cnt_out, _ = _run_git(["rev-list", "--left-right", "--count", "HEAD...@{u}"])
            if ok_cnt and cnt_out.strip():
                parts = cnt_out.strip().split()
                if len(parts) == 2:
                    try:
                        ahead = int(parts[0])
                        behind = int(parts[1])
                    except ValueError:
                        pass

    # 4. Working Tree status (Uncommitted edits / Staged / Untracked / Conflicts)
    ok_st, st_out, _ = _run_git(["status", "--porcelain=v1"])
    staged_files: list[tuple[str, str]] = []
    unstaged_files: list[tuple[str, str]] = []
    untracked_files: list[str] = []
    conflict_files: list[str] = []
    if ok_st and st_out:
        for line in st_out.splitlines():
            if len(line) < 3:
                continue
            x = line[0]
            y = line[1]
            filepath = line[3:].strip('"')
            if x == "?" and y == "?":
                untracked_files.append(filepath)
            elif x == "U" or y == "U" or (x == "A" and y == "A") or (x == "D" and y == "D"):
                conflict_files.append(filepath)
            else:
                if x in ("M", "A", "D", "R", "C"):
                    staged_files.append((x, filepath))
                if y in ("M", "D", "T"):
                    unstaged_files.append((y, filepath))

    return {
        "remotes": remotes,
        "branch": branch,
        "is_detached": is_detached,
        "has_upstream": has_upstream,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "staged": staged_files,
        "unstaged": unstaged_files,
        "untracked": untracked_files,
        "conflicts": conflict_files,
    }


def render_git_info_panel(git_info: dict[str, Any], exclude_list: list[str]) -> Panel:
    """Format and render a rich Panel containing detailed repository information."""
    cwd = Path.cwd()

    # 1. Format Remote URL
    remotes = git_info["remotes"]
    if remotes:
        remote_lines = []
        for name, urls in remotes.items():
            fetch_url = urls.get("fetch")
            push_url = urls.get("push")
            direct_url = urls.get("url")
            safe_name = escape(name)
            if direct_url:
                remote_lines.append(f"[cyan]{safe_name}:[/cyan] [white]{escape(direct_url)}[/white]")
            elif fetch_url and push_url and fetch_url == push_url:
                remote_lines.append(f"[cyan]{safe_name}:[/cyan] [white]{escape(fetch_url)}[/white]")
            else:
                if fetch_url and push_url:
                    remote_lines.append(f"[cyan]{safe_name} (fetch):[/cyan] [white]{escape(fetch_url)}[/white]\n    [cyan]{safe_name} (push):[/cyan] [white]{escape(push_url)}[/white]")
                elif fetch_url:
                    remote_lines.append(f"[cyan]{safe_name} (fetch):[/cyan] [white]{escape(fetch_url)}[/white]")
                elif push_url:
                    remote_lines.append(f"[cyan]{safe_name} (push):[/cyan] [white]{escape(push_url)}[/white]")
        remote_str = "\n    ".join(remote_lines)
    else:
        remote_str = "[dim]Chưa cấu hình remote[/dim]"

    # 2. Format Branch & Tracking
    branch = git_info["branch"]
    has_upstream = git_info["has_upstream"]
    upstream = git_info["upstream"]
    safe_branch = escape(branch)
    if has_upstream and upstream:
        tracking_str = f"[bold green]Có[/bold green] (theo dõi [cyan]{escape(upstream)}[/cyan])"
    else:
        tracking_str = "[yellow]Không có[/yellow] (chưa liên kết nhánh trên remote)"

    # 3. Format Ahead / Behind
    ahead = git_info["ahead"]
    behind = git_info["behind"]
    if has_upstream:
        if ahead == 0 and behind == 0:
            sync_str = "[bold green]Đồng bộ với remote[/bold green] (0 commit)"
        elif ahead > 0 and behind == 0:
            sync_str = f"[bold yellow]Nhanh hơn remote {ahead} commit[/bold yellow] (Chưa push ↑)"
        elif ahead == 0 and behind > 0:
            sync_str = f"[bold red]Chậm hơn remote {behind} commit[/bold red] (Cần pull ↓)"
        else:
            sync_str = f"[bold magenta]Phân nhánh[/bold magenta] (Nhanh hơn ↑ {ahead} commit, Chậm hơn ↓ {behind} commit)"
    else:
        sync_str = "[dim]N/A (Chưa có nhánh remote)[/dim]"

    # 4. Format Working Tree status
    staged = git_info["staged"]
    unstaged = git_info["unstaged"]
    untracked = git_info["untracked"]
    conflicts = git_info["conflicts"]
    total_dirty = len(staged) + len(unstaged) + len(untracked) + len(conflicts)

    status_lines = []
    if total_dirty == 0:
        worktree_str = "[bold green]✨ Sạch sẽ[/bold green] (Không có thay đổi nào đang sửa/chưa commit)"
    else:
        parts = []
        if staged:
            parts.append(f"[green]{len(staged)} file đã stage[/green]")
        if unstaged:
            parts.append(f"[yellow]{len(unstaged)} file đang sửa/xóa chưa stage[/yellow]")
        if untracked:
            parts.append(f"[cyan]{len(untracked)} file mới chưa track[/cyan]")
        if conflicts:
            parts.append(f"[bold red]{len(conflicts)} file xung đột[/bold red]")
        worktree_str = f"[bold yellow]⚠️ Có {total_dirty} thay đổi chưa commit[/bold yellow] ({', '.join(parts)})"

        items_to_show = []
        for code, path in staged:
            type_name = {"M": "sửa", "A": "thêm mới", "D": "xóa", "R": "đổi tên", "C": "sao chép"}.get(code, code)
            items_to_show.append(f"    [green]• (Đã stage: {type_name})[/green] [white]{escape(path)}[/white]")
        for code, path in unstaged:
            type_name = {"M": "đang sửa", "D": "đã xóa", "T": "đổi kiểu"}.get(code, code)
            items_to_show.append(f"    [yellow]• (Chưa stage: {type_name})[/yellow] [white]{escape(path)}[/white]")
        for path in untracked:
            items_to_show.append(f"    [cyan]• (Chưa track)[/cyan] [white]{escape(path)}[/white]")
        for path in conflicts:
            items_to_show.append(f"    [bold red]• (Xung đột)[/bold red] [white]{escape(path)}[/white]")

        max_display = 8
        displayed_items = items_to_show[:max_display]
        if len(items_to_show) > max_display:
            displayed_items.append(f"    [dim]... và {len(items_to_show) - max_display} file khác[/dim]")
        status_lines = displayed_items

    safe_excludes = [escape(e) for e in exclude_list]
    panel_content = [
        f"[bold cyan]📁 Thư mục làm việc:[/bold cyan] [bold white]{escape(str(cwd))}[/bold white]",
        f"[bold cyan]🌐 Git Remote URL:[/bold cyan] {remote_str}",
        f"[bold cyan]🌿 Nhánh hiện tại:[/bold cyan] [bold white]{safe_branch}[/bold white]",
        f"[bold cyan]📡 Trạng thái Remote:[/bold cyan] {tracking_str}",
        f"[bold cyan]📊 Tiến độ Commit:[/bold cyan] {sync_str}",
        f"[bold cyan]📝 Working Tree:[/bold cyan] {worktree_str}",
    ]
    if status_lines:
        panel_content.extend(status_lines)
    panel_content.append(f"[bold yellow]🛡️  Được bảo vệ (Loại trừ):[/bold yellow] [bold green]{', '.join(safe_excludes)}[/bold green]")

    return Panel(
        "\n".join(panel_content),
        title="[bold green]🧹 Git Clean Interactive (uv)[/bold green]",
        expand=False,
    )


def is_excluded(rel_path: str, patterns: list[str]) -> bool:
    """Check if relative path matches any exclusion pattern across Windows, macOS, and Linux."""
    norm_path = rel_path.replace("\\", "/").strip().rstrip("/")
    if not norm_path:
        return False

    p = Path(norm_path)
    file_name = p.name
    parts = list(p.parts)

    is_win = sys.platform == "win32"

    for pat in patterns:
        pat_clean = pat.strip().replace("\\", "/").rstrip("/")
        if not pat_clean:
            continue

        # Trên Windows: so khớp case-insensitive
        match_pat = pat_clean.lower() if is_win else pat_clean
        target_name = file_name.lower() if is_win else file_name
        target_norm = norm_path.lower() if is_win else norm_path

        # 1. So khớp tên file/folder (ví dụ: ".env*" khớp ".env.local")
        if fnmatch.fnmatch(target_name, match_pat):
            return True

        # 2. So khớp toàn bộ đường dẫn relative (ví dụ: "node_modules" khớp "node_modules")
        if fnmatch.fnmatch(target_norm, match_pat):
            return True

        # 3. So khớp tiền tố thư mục cha (ví dụ: pattern="dist" khớp "dist/index.html")
        if fnmatch.fnmatch(target_norm, f"{match_pat}/*") or fnmatch.fnmatch(target_norm, f"{match_pat}*"):
            return True

        # 4. So khớp từng cấp thư mục con
        for part in parts:
            target_part = part.lower() if is_win else part
            if fnmatch.fnmatch(target_part, match_pat):
                return True

    return False


def get_git_clean_dry_run(exclude_patterns: list[str]) -> tuple[list[tuple[str, Path, bool, int]], list[str]]:
    """Run `git clean -ndX`, filter out excluded items, and return parsed items."""
    # -c core.quotepath=false giúp Git xuất đường dẫn UTF-8 nguyên bản, không bị octal escape (\303...)
    cmd = ["git", "-c", "core.quotepath=false", "clean", "-ndX"]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as e:
        console.print(f"[bold red]❌ Lỗi khi chạy git clean:[/bold red] {e}")
        return [], []

    if res.returncode != 0:
        console.print(f"[bold red]❌ Lỗi khi chạy git clean:[/bold red] {res.stderr.strip()}")
        return [], []

    items = []
    skipped_excluded = []
    cwd = Path.cwd()

    for line in res.stdout.splitlines():
        line_clean = line.strip()
        match = re.match(r"^Would remove (.+)$", line_clean)
        if match:
            rel_str = match.group(1).strip()
            # Bỏ dấu nháy kép bao quanh nếu git bao lại
            if rel_str.startswith('"') and rel_str.endswith('"'):
                rel_str = rel_str[1:-1]

            # Kiểm tra xem có thuộc danh sách loại trừ không
            if is_excluded(rel_str, exclude_patterns):
                skipped_excluded.append(rel_str)
                continue

            full_path = cwd / rel_str
            is_dir = full_path.is_dir() and not full_path.is_symlink()
            size = get_path_size(full_path)
            items.append((rel_str, full_path, is_dir, size))

    return items, skipped_excluded


def main():
    parser = argparse.ArgumentParser(
        description="Dọn dẹp dự án Git an toàn bằng Python & uv - Cho phép chọn lọc các file/thư mục cần xóa."
    )
    parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        default=None,
        help="Pattern loại trừ (mặc định luôn bảo vệ: .env*). Có thể truyền thêm: -e secret.json",
    )
    parser.add_argument(
        "--dry-run-only",
        action="store_true",
        help="Chỉ hiển thị danh sách dry-run rồi thoát, không hỏi xóa.",
    )

    args = parser.parse_args()

    # Mặc định luôn bao gồm .env*
    exclude_list = [".env*"]
    if args.exclude:
        for e in args.exclude:
            if e not in exclude_list:
                exclude_list.append(e)

    # 1. Kiểm tra Git repository và chẩn đoán lỗi nếu có
    is_valid_repo, repo_err_msg = check_git_repo()
    if not is_valid_repo:
        console.print(repo_err_msg)
        sys.exit(1)

    # Thu thập thông tin chi tiết về Git repository
    git_info = get_git_info()
    console.print(render_git_info_panel(git_info, exclude_list))

    # 2. Quét danh sách dry-run
    with console.status("[bold cyan]🔍 Đang quét các file/folder gitignored...[/bold cyan]", spinner="dots"):
        items, skipped_excluded = get_git_clean_dry_run(exclude_list)

    if skipped_excluded:
        console.print(f"[dim]🛡️  Đã tự động bảo vệ {len(skipped_excluded)} mục khớp mẫu loại trừ: {', '.join(skipped_excluded)}[/dim]")

    if not items:
        console.print("\n[bold green]✨ Dự án đã hoàn toàn sạch sẽ! Không có file/folder rác nào để xóa.[/bold green]\n")
        return

    # Sắp xếp theo dung lượng giảm dần
    items.sort(key=lambda x: x[3], reverse=True)
    total_found_size = sum(item[3] for item in items)

    console.print(
        f"\n[bold yellow]📋 Tìm thấy {len(items)} mục[/bold yellow] (Tổng dung lượng ước tính: [bold magenta]{format_size(total_found_size)}[/bold magenta]):\n"
    )

    if args.dry_run_only:
        table = Table(title="Danh sách Dry-run (Chỉ xem)")
        table.add_column("Loại", justify="center", style="cyan")
        table.add_column("Đường dẫn", style="white")
        table.add_column("Dung lượng", justify="right", style="magenta")

        for rel_str, _, is_dir, size in items:
            type_label = "📁 Folder" if is_dir else "📄 File"
            table.add_row(type_label, rel_str, format_size(size))
        console.print(table)
        return

    # 3. Tạo danh sách lựa chọn cho InquirerPy Checkbox
    choices = []
    for rel_str, full_path, is_dir, size in items:
        type_icon = "📁" if is_dir else "📄"
        size_str = f"({format_size(size)})"
        label = f"{type_icon} {rel_str:<45} {size_str:>12}"
        choices.append(Choice(value=(rel_str, full_path, is_dir, size), name=label, enabled=True))

    try:
        console.print("[dim]Phím tắt: [Space] Bật/Tắt | [a] Chọn/Bỏ chọn tất cả | [i] Đảo chọn | [Enter] Xác nhận | [Ctrl+C] Hủy[/dim]\n")
        selected = inquirer.checkbox(
            message="Chọn các thư mục/file bạn muốn XÓA:",
            choices=choices,
            cycle=True,
            instruction="(Dùng phím mũi tên ↑/↓ để di chuyển, Space để chọn/bỏ chọn, Enter để tiếp tục)",
        ).execute()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]🛑 Đã hủy thao tác.[/bold yellow]")
        return

    if not selected:
        console.print("\n[bold yellow]⚠️ Bạn chưa chọn mục nào để xóa. Không có gì thay đổi![/bold yellow]\n")
        return

    # 4. Hiển thị bảng tổng kết các mục đã chọn
    selected_size = sum(item[3] for item in selected)
    table = Table(title=f"🗑️ Danh sách các mục SẼ BỊ XÓA ({len(selected)} mục - {format_size(selected_size)})")
    table.add_column("Loại", justify="center", style="cyan")
    table.add_column("Đường dẫn", style="white")
    table.add_column("Dung lượng", justify="right", style="magenta")

    for rel_str, _, is_dir, size in selected:
        type_label = "📁 Folder" if is_dir else "📄 File"
        table.add_row(type_label, rel_str, format_size(size))

    console.print()
    console.print(table)
    console.print()

    # 5. Xác nhận lần cuối
    try:
        confirm = inquirer.confirm(
            message=f"Bạn có chắc chắn muốn XÓA VĨNH VIỄN {len(selected)} mục trên ({format_size(selected_size)})?",
            default=False,
        ).execute()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]🛑 Đã hủy thao tác.[/bold yellow]")
        return

    if not confirm:
        console.print("\n[bold yellow]🛑 Đã hủy thao tác xóa. Không có gì bị xóa![/bold yellow]\n")
        return

    # 6. Thực hiện xóa an toàn
    console.print("\n[bold cyan]🚀 Đang tiến hành xóa...[/bold cyan]\n")
    success_count = 0
    fail_count = 0
    freed_size = 0

    for rel_str, full_path, is_dir, size in selected:
        if not full_path.exists() and not full_path.is_symlink():
            console.print(f"  [dim]⚪ Bỏ qua (không tồn tại): {rel_str}[/dim]")
            continue

        success, err_msg = safe_remove_path(full_path)
        if success:
            console.print(f"  [bold green][OK][/bold green] Đã xóa: [white]{rel_str}[/white] [dim]({format_size(size)})[/dim]")
            success_count += 1
            freed_size += size
        else:
            console.print(f"  [bold red][LỖI][/bold red] Không thể xóa [white]{rel_str}[/white]: [red]{err_msg}[/red]")
            fail_count += 1

    console.print(
        f"\n[bold green]✅ Hoàn tất dọn dẹp![/bold green] "
        f"Đã xóa thành công [bold white]{success_count}/{len(selected)}[/bold white] mục. "
        f"Giải phóng: [bold magenta]{format_size(freed_size)}[/bold magenta]"
    )
    if fail_count > 0:
        console.print(f"[bold red]⚠️ {fail_count} mục gặp lỗi khi xóa.[/bold red]")
    console.print()


if __name__ == "__main__":
    main()
