# Bypass IPv4 Nga cho toàn bộ khách AWG

Phiên bản2: **`ru-bypass on` và `ru-bypass off` áp dụng cho toàn bộ khách AWG kernel thuộc subnet `10.8.0.0/24`**. Khi bật, khách tạo mới trong subnet này tự động hưởng cùng chính sách; không cần truyền tên hay chạy lại lệnh. Khách vẫn phải được LucX nạp vào AWG kernel theo trạng thái/quyền sử dụng của họ.

Chạy bằng root trên **relay đã dựng bằng bộ cài trong repo này và đã Restore database LucX**. Không chạy trên exit.

Cài/cập nhật và bật cho tất cả khách:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/ru-bypass.sh) install
```

Nếu chỉ muốn cập nhật lệnh, giữ nguyên chế độ đang chạy:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/ru-bypass.sh) setup
```

Sau khi cập nhật:

```bash
ru-bypass on
ru-bypass off
ru-bypass status
```

- `on`: kết nối IPv4 mới tới IP Nga đi trực tiếp qua WAN relay; IP khác vẫn qua foreign exit `awg32`. Áp dụng cho mọi khách AWG hiện tại và khách mới trong `10.8.0.0/24`. Không tự hết hạn.
- `off`: gỡ riêng bypass IP Nga cho toàn bộ khách, đưa lưu lượng về tuyến foreign exit cũ.
- `status`: xem trạng thái và phạm vi. Nếu vừa nâng cấp từ bản thử theo tên mà chưa chạy `on`, nó báo rõ `LEGACY SELECTED MODE` khi bản thử cũ còn hoạt động.

Không còn dùng `--clients` hoặc danh sách tên khách ở phiên bản2. `on` chuyển bản thử cũ sang toàn subnet bằng một giao dịch nftables; `setup` không tự mở rộng phạm vi đang chạy. Tiện ích nhận diện và giữ trạng thái từ bản quản lý cũ, không cần tự gỡ trước.

Sau khi bật/tắt, kết nối lại VPN và mở lại ứng dụng để thay kết nối cũ. Tiện ích không xóa conntrack toàn máy. **Reboot sẽ mất bypass**; chạy `ru-bypass on` để bật lại. Tự áp dụng cho khách mới không có nghĩa là tự bật sau reboot. Chưa có tự khởi động hoặc tự cập nhật danh sách.

Đây là IPv4 IP-only bypass cho AWG kernel `xui-awg1`; không áp dụng cho VLESS/REALITY, domain, DNS hoặc IPv6. Các quy tắc chặn mạng nội bộ và MSS Telegram hiện hữu được giữ nguyên. Tiện ích không restart panel/tunnel, sửa database/cấu hình điện thoại hay mở cổng mới. Khi bật có kiểm tra tài nguyên policy routing, guard/gateway hiện tại và hoàn tác nếu áp dụng thất bại.

Nguồn GeoIP: [Loyalsoldier/geoip](https://github.com/Loyalsoldier/geoip), `text/ru.txt`, ghim commit `eace600e4e2d6708de3948b047ff9ff7bc5b5b11`, SHA256 `779e867ddeec1aca1e9501cc8cfe45f9c5d77531512a36c58d51e949da49adde`, 13069 dải IPv4. Bộ cài không chứa thông tin khách hoặc khóa.

File được lưu tại `/root/amnezia-relay-deploy/ru-bypass-all-v2/`. Các lần bật có thư mục `runs/`, bản chụp trước thay đổi và script hoàn tác riêng. Đã kiểm tra trong namespace Linux: bật/tắt lặp lại, khách mới tự áp dụng và chuyển từ danh sách khách sang toàn subnet. Chưa chứng nhận cho subnet/kiến trúc/firewall ngoài bộ cài của repo; cấu hình không tương thích sẽ dừng để kiểm tra.
