#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "inquirerpy>=0.3.4",
#     "rich>=13.0.0",
# ]
# ///

import argparse
import fnmatch
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

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
from rich.panel import Panel
from rich.table import Table

console = Console()


def format_size(bytes_size: int) -> str:
    """Format bytes into human-readable size (B, KB, MB, GB)."""
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
        if not path.exists():
            return 0
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        total = 0
        for entry in path.rglob("*"):
            try:
                if entry.is_file() or entry.is_symlink():
                    total += entry.stat().st_size
            except (OSError, PermissionError):
                continue
        return total
    except (OSError, PermissionError):
        return 0


def remove_readonly(func, path, exc_info):
    """Error handler for shutil.rmtree on Windows (clears read-only flag)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def is_git_repo() -> bool:
    """Check if current directory is inside a git work tree."""
    res = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0 and res.stdout.strip() == "true"


def is_excluded(rel_path: str, patterns: List[str]) -> bool:
    """Check if relative path matches any exclusion pattern."""
    p = Path(rel_path)
    for pat in patterns:
        pat_clean = pat.strip()
        if not pat_clean:
            continue
        if fnmatch.fnmatch(p.name, pat_clean):
            return True
        if fnmatch.fnmatch(rel_path, pat_clean):
            return True
        if any(fnmatch.fnmatch(part, pat_clean) for part in p.parts):
            return True
    return False


def get_git_clean_dry_run(exclude_patterns: List[str]) -> Tuple[List[Tuple[str, Path, bool, int]], List[str]]:
    """Run `git clean -ndX`, filter out excluded items, and return parsed items."""
    cmd = ["git", "clean", "-ndX"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        console.print(f"[bold red]❌ Lỗi khi chạy git clean:[/bold red] {res.stderr}")
        return [], []

    items = []
    skipped_excluded = []
    cwd = Path.cwd()

    for line in res.stdout.splitlines():
        match = re.match(r"^Would remove (.+)$", line.strip())
        if match:
            rel_str = match.group(1).strip()
            # Kiểm tra xem có thuộc danh sách loại trừ không
            if is_excluded(rel_str, exclude_patterns):
                skipped_excluded.append(rel_str)
                continue

            full_path = cwd / rel_str
            is_dir = full_path.is_dir()
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

    # 1. Kiểm tra Git repository
    if not is_git_repo():
        console.print("[bold red]❌ Thư mục hiện tại không phải là Git repository![/bold red]")
        sys.exit(1)

    cwd = Path.cwd()
    console.print(
        Panel(
            f"[cyan]Thư mục làm việc:[/cyan] [bold white]{cwd}[/bold white]\n"
            f"[yellow]Được bảo vệ (Loại trừ an toàn):[/yellow] [bold green]{', '.join(exclude_list)}[/bold green]",
            title="[bold green]🧹 Git Clean Interactive (uv)[/bold green]",
            expand=False,
        )
    )

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

    # 6. Thực hiện xóa
    console.print("\n[bold cyan]🚀 Đang tiến hành xóa...[/bold cyan]\n")
    success_count = 0
    fail_count = 0
    freed_size = 0

    for rel_str, full_path, is_dir, size in selected:
        try:
            if not full_path.exists():
                console.print(f"  [dim]⚪ Bỏ qua (không tồn tại): {rel_str}[/dim]")
                continue

            if is_dir:
                shutil.rmtree(full_path, onerror=remove_readonly)
            else:
                try:
                    os.chmod(full_path, stat.S_IWRITE)
                except Exception:
                    pass
                full_path.unlink(missing_ok=True)

            console.print(f"  [bold green][OK][/bold green] Đã xóa: [white]{rel_str}[/white] [dim]({format_size(size)})[/dim]")
            success_count += 1
            freed_size += size
        except Exception as e:
            console.print(f"  [bold red][LỖI][/bold red] Không thể xóa [white]{rel_str}[/white]: [red]{e}[/red]")
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
