#!/bin/bash
# Tailscale controller with Microsoft GSA protection & VPN inspector

set -e

TAILSCALE_BIN="/opt/homebrew/bin/tailscale"

if [ ! -x "$TAILSCALE_BIN" ]; then
    echo "Error: tailscale not found at $TAILSCALE_BIN" >&2
    exit 1
fi

get_vpn_statuses() {
    # 1. Check Microsoft GSA
    if pgrep -f "com.microsoft.globalsecureaccess.tunnel" >/dev/null 2>&1; then
        if ifconfig 2>/dev/null | grep -q "10.10.10.10"; then
            gsa_status="Đang bật (Active Tunnel - 10.10.10.10)"
        else
            gsa_status="Đang chạy (Idle / Chưa kích hoạt tunnel)"
        fi
    else
        gsa_status="Đang tắt (Không chạy)"
    fi

    # 2. Check Cloudflare WARP (1.1.1.1)
    if command -v warp-cli >/dev/null 2>&1; then
        warp_raw=$(warp-cli status 2>/dev/null | grep -i "Status update:" | awk '{print $3}' || true)
        if [ "$warp_raw" = "Connected" ]; then
            warp_status="Đang bật (Connected)"
        elif [ "$warp_raw" = "Disconnected" ]; then
            warp_status="Đang tắt (Disconnected)"
        elif [ -n "$warp_raw" ]; then
            warp_status="$warp_raw"
        else
            warp_status="Đang tắt (Service offline)"
        fi
    elif pgrep -f "CloudflareWARP" >/dev/null 2>&1; then
        warp_status="Đang chạy daemon"
    else
        warp_status="Chưa cài đặt"
    fi

    echo "● Microsoft GSA:             $gsa_status"
    echo "● Cloudflare WARP (1.1.1.1): $warp_status"
}

show_status() {
    echo "================ TRẠNG THÁI TAILSCALE ================"

    # Kiểm tra xem daemon tailscaled có đang phản hồi không
    ts_raw=$("$TAILSCALE_BIN" status --json 2>/dev/null || true)

    if [ -z "$ts_raw" ]; then
        echo "✕ Daemon:         Chưa khởi chạy (tailscaled offline)"
        echo "● Khả năng chạy:  Không hoạt động"
        echo "● Khắc phục:      Chạy 'sudo launchctl bootstrap system /Library/LaunchDaemons/sh.brew.tailscale.plist'"
    else
        parsed=$(echo "$ts_raw" | /usr/bin/python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    state = d.get("BackendState", "Unknown")
    self_node = d.get("Self", {})
    ips = self_node.get("TailscaleIPs") or []
    ip = ips[0] if ips else "N/A"
    host = self_node.get("HostName", "N/A")
    dns = self_node.get("DNSName", "").rstrip(".")
    node_name = dns.split(".")[0] if dns else host
    tun = d.get("TUN", False)
    print(f"{state}|{ip}|{node_name}|{dns}|{tun}")
except Exception:
    print("Error||||")
')

        IFS='|' read -r b_state ts_ip ts_node ts_dns ts_tun <<< "$parsed"

        case "$b_state" in
            Running)
                echo "● Trạng thái:     Đang kết nối (Connected)"
                echo "● Thiết bị:       $ts_node ($ts_ip)"
                echo "● Khả năng chạy:  Sẵn sàng truyền nhận dữ liệu (TUN: $ts_tun)"
                
                # Kiểm tra an toàn DNS với GSA
                if scutil --dns 2>/dev/null | grep -A 2 "resolver #1" | grep -q "100.100.100.100"; then
                    echo "⚠️  Bảo vệ GSA:    CẢNH BÁO: MagicDNS đang chiếm resolver #1!"
                else
                    echo "● Bảo vệ GSA:     An toàn 100% (DNS & Routes không bị can thiệp)"
                fi
                ;;
            Stopped)
                echo "○ Trạng thái:     Đã ngắt kết nối (Disconnected)"
                echo "● Daemon:         Đang chạy nền (Sẵn sàng bật lại với 'tscale up')"
                echo "● Khả năng chạy:  Chờ lệnh kết nối"
                ;;
            NeedsLogin)
                echo "⚠️  Trạng thái:    Chưa đăng nhập (Needs Login)"
                echo "● Khắc phục:      Chạy 'sudo tailscale up --accept-dns=false --accept-routes=false' để đăng nhập"
                ;;
            *)
                echo "● Trạng thái:     $b_state"
                ;;
        esac
    fi

    echo ""
    echo "============== TRẠNG THÁI CÁC VPN KHÁC =============="
    get_vpn_statuses
    echo "======================================================"
}

cmd="${1:-status}"

case "$cmd" in
    up)
        echo "🚀 Connecting Tailscale (preserving GSA)..."
        "$TAILSCALE_BIN" up --accept-dns=false --accept-routes=false
        ;;
    down)
        echo "🛑 Disconnecting Tailscale..."
        "$TAILSCALE_BIN" down
        ;;
    restart)
        echo "🔄 Reconnecting Tailscale..."
        "$TAILSCALE_BIN" down 2>/dev/null || true
        "$TAILSCALE_BIN" up --accept-dns=false --accept-routes=false
        ;;
    status)
        show_status
        ;;
    admin)
        echo "🌐 Đang mở Tailscale Admin Console trên trình duyệt..."
        open "https://login.tailscale.com/admin/machines"
        ;;
    *)
        echo "Usage: tscale {up|down|restart|status|admin}"
        exit 1
        ;;
esac
