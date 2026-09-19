# Hướng Dẫn Vận Hành Tailscale CLI Song Song Microsoft Entra GSA Trên macOS

Tài liệu này ghi lại kiến trúc, cấu hình dịch vụ daemon và quy trình vận hành thực tế cho **Tailscale CLI độc lập** chạy song song với **Microsoft Entra Global Secure Access (GSA)** trên macOS mà không gây xung đột mạng.

---

## 1. Phân Tích Kiến Trúc & Nguyên Nhân Xung Đột

- **Xung đột Network Extension:**
  Cả Tailscale GUI (App Store/PKG) và Microsoft GSA Client đều sử dụng framework `NetworkExtension` của Apple (`PacketTunnelProvider`). macOS không cho phép hai Packet Tunnel Extensions cùng kiểm soát định tuyến mặc định và xử lý gói tin mà không gây va chạm interface ảo.
- **Xung đột DNS Resolver:**
  Tailscale GUI mặc định bật MagicDNS qua macOS Dynamic Store (`scutil --dns`), ghi đè `100.100.100.100` vào resolver chính. Điều này làm tê liệt khả năng phân giải các FQDN nội bộ của GSA.
- **Giải pháp cốt lõi:**
  1. Gỡ bỏ hoàn toàn bản Tailscale GUI.
  2. Cài đặt **Tailscale CLI** độc lập qua Homebrew (`brew install tailscale`).
  3. `tailscaled` CLI chạy dưới quyền `root`, tạo card mạng ảo native BSD `utun` trực tiếp từ kernel macOS thông qua `ioctl`, hoàn toàn không sử dụng framework `NetworkExtension` $\rightarrow$ **Triệt tiêu 100% xung đột với GSA**.
  4. Khóa tính năng nhận DNS và routes từ Tailnet để bảo vệ cấu hình mạng của công ty.

---

## 2. Cấu Hình Dịch Vụ Nền (`launchd`)

Tệp cấu hình daemon hệ thống:  
`/Library/LaunchDaemons/sh.brew.tailscale.plist`

### 2.1. Nội dung chuẩn của tệp plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>KeepAlive</key>
  <true/>
  <key>Label</key>
  <string>sh.brew.tailscale</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>LoginWindow</string>
    <string>StandardIO</string>
    <string>System</string>
  </array>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/opt/tailscale/bin/tailscaled</string>
    <string>--state=/var/db/tailscale/tailscaled.state</string>
    <string>--socket=/var/run/tailscaled.socket</string>
    <string>--port=41641</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>/opt/homebrew/var/log/tailscaled.log</string>
  <key>StandardOutPath</key>
  <string>/opt/homebrew/var/log/tailscaled.log</string>
</dict>
</plist>
```

### 2.2. Phân quyền và thư mục dữ liệu

```bash
# Phân quyền chuẩn cho plist
sudo chown root:wheel /Library/LaunchDaemons/sh.brew.tailscale.plist
sudo chmod 644 /Library/LaunchDaemons/sh.brew.tailscale.plist

# Tạo thư mục lưu trạng thái chuẩn
sudo mkdir -p /var/db/tailscale
sudo chmod 700 /var/db/tailscale
sudo chown root:wheel /var/db/tailscale
```

> [!NOTE]
> Thư mục cũ `/Library/Tailscale` (dữ liệu rác còn sót lại từ bản GUI cũ) đã được dọn dẹp sạch sẽ để tránh xung đột dữ liệu trạng thái.

---

## 3. Quy Trình Vận Hành & Điều Khiển Hằng Ngày

### 3.1. Cấp độ 1: Bật / Tắt kết nối VPN (Khuyên dùng thường nhật)

Daemon vẫn chạy nền, chỉ ngắt/kết nối luồng mạng:

- **Tắt kết nối:**

  ```bash
  tailscale down
  ```

- **Bật kết nối (Bắt buộc kèm cờ cô lập):**

  ```bash
  tailscale up --accept-dns=false --accept-routes=false
  ```

  - `--accept-dns=false`: Ngăn MagicDNS ghi đè cấu hình DNS của GSA/doanh nghiệp.
  - `--accept-routes=false`: Ngăn các subnet route từ mạng Tailnet làm sai lệch bảng định tuyến nội bộ.

- **Kiểm tra trạng thái:**

  ```bash
  tailscale status
  ```

### 3.2. Cấp độ 2: Quản lý Daemon Hệ Thống (`launchctl`)

Dùng khi cần nạp lại cấu hình plist hoặc dừng hẳn tiến trình nền:

- **Dừng daemon:**

  ```bash
  sudo launchctl bootout system/sh.brew.tailscale
  ```

- **Khởi chạy daemon:**

  ```bash
  sudo launchctl bootstrap system /Library/LaunchDaemons/sh.brew.tailscale.plist
  ```

---

## 4. Công Cụ Điều Khiển: Lệnh `tscale`

Tập lệnh điều khiển độc lập được đặt tại:

- Script thực thi: `/Users/admin/code/repo-culur/bash/src/tailscale/tscale.sh`
- Symlink trong PATH: `/Users/admin/code/repo-culur/bash/bin/tscale`

### Các lệnh hỗ trợ

- `tscale up` : Bật kết nối Tailscale (tự động gắn cờ bảo vệ GSA).
- `tscale down` : Tắt kết nối Tailscale.
- `tscale restart` : Khởi động lại kết nối nhanh.
- `tscale status` : Hiển thị danh sách thiết bị và trạng thái (hoặc chỉ cần gõ `tscale`).

---

## 5. Quy Trình Kiểm Tra & Xác Minh An Toàn (Verification)

Sau khi khởi động hoặc bật kết nối, chạy các lệnh sau để đảm bảo GSA không bị ảnh hưởng:

1. **Kiểm tra DNS không bị cướp:**

   ```bash
   scutil --dns | head -n 20
   ```

   _Yêu cầu:_ `resolver #1` phải giữ nguyên DNS của card mạng vật lý (`en0`), tuyệt đối không chứa địa chỉ `100.100.100.100`.

2. **Kiểm tra Network Extensions:**

   ```bash
   systemextensionsctl list
   ```

   _Yêu cầu:_ `com.microsoft.globalsecureaccess.tunnel` ở trạng thái `[activated enabled]`. Không có Network Extension nào của Tailscale còn hoạt động.

3. **Kiểm tra card mạng và bảng định tuyến:**

   ```bash
   netstat -nr -f inet | head -n 15
   ```

   _Yêu cầu:_
   - Default route trỏ qua gateway vật lý (`en0`).
   - GSA định tuyến qua interface của nó (ví dụ `utun7`).
   - Tailscale chỉ quản lý dải CGNAT `100.64.0.0/10` trên interface riêng của nó (ví dụ `utun8`).
