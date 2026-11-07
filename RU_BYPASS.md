# Bypass IPv4 Nga cho khách được chọn

Tiện ích riêng cho **relay đã dựng bằng bộ cài trong repo này và đã Restore database LucX**. Không chạy trên exit. Không cần mật khẩu gói khóa để dùng tiện ích này.

Đăng nhập root trên relay. Một lệnh để cài và bật:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/ru-bypass.sh) install --clients 'TEN_KHACH_1,TEN_KHACH_2,TEN_KHACH_3'
```

Thay các tên bằng tên khách chính xác trong LucX, phân cách bằng dấu phẩy. Nếu bỏ `--clients`, tiện ích hỏi tên qua terminal. Chọn từ1 đến20 khách. Khách phải đang bật, có địa chỉ IPv4 `/32` riêng thuộc `10.8.0.0/24` và đã được nạp vào AWG kernel `xui-awg1`.

Sau khi cài:

```bash
ru-bypass status
ru-bypass off
ru-bypass on
```

- `on`: kết nối IPv4 mới tới IP Nga đi trực tiếp qua WAN relay; IP khác tiếp tục qua foreign exit `awg32`. Không tự hết hạn.
- `off`: gỡ riêng rule của tiện ích, trả lưu lượng về tuyến foreign exit cũ.
- `status`: xem trạng thái, danh sách khách và lịch hoàn tác nếu có.

Có thể tắt bằng lệnh tải lại tiện ích:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/ru-bypass.sh) off
```

Sau khi bật/tắt, kết nối lại VPN và mở lại ứng dụng để thay các kết nối cũ. Tiện ích không xóa conntrack toàn máy. Chế độ chỉ tồn tại trong phiên chạy của VPS: **reboot sẽ mất bypass**, sau đó chạy `ru-bypass on` để bật lại. Chưa có tự khởi động hoặc tự cập nhật danh sách.

Tiện ích kiểm tra routing/NAT/hoàn tác trong network namespace biệt lập trước khi cài. Khi bật, nó xác minh khách đang tồn tại, gateway WAN, guard hiện tại và tài nguyên policy routing chưa bị chiếm; có hoàn tác nếu áp dụng thất bại. Không restart panel/tunnel, sửa database, DNS, cấu hình điện thoại hay mở cổng mới. Các khách không được chọn giữ tuyến cũ. Các rule MSS Telegram hiện hữu được giữ nguyên. Không thay danh sách khách khi cài lại trên cùng VPS; tiện ích sẽ dừng nếu phạm vi khác.

Nguồn GeoIP: [Loyalsoldier/geoip](https://github.com/Loyalsoldier/geoip), file `text/ru.txt`, ghim commit `eace600e4e2d6708de3948b047ff9ff7bc5b5b11`, SHA256 `779e867ddeec1aca1e9501cc8cfe45f9c5d77531512a36c58d51e949da49adde`, 13069 dải IPv4. Đây là phân loại **địa chỉ IP**, chưa phải danh sách domain Nga. IPv6 giữ chính sách sẵn có của relay.

Bộ cài công khai không chứa thông tin khách hoặc khóa. Nó đọc tên/IP từ database ngay trên VPS và lưu cấu hình tại `/root/amnezia-relay-deploy/ru-bypass/`; các lần bật có thư mục `runs/` và bản chụp trước thay đổi riêng. Cài lại trên relay có bản thử ba khách tương thích sẽ sử dụng lệnh quản lý hiện hữu, giữ nguyên phạm vi đó.

Đã kiểm tra mạng dữ liệu trong namespace Linux, bao gồm bật/tắt lặp lại. Chưa chứng nhận cho kiến trúc, subnet hoặc firewall ngoài bộ cài của repo. Nếu cấu hình không tương thích, tiện ích dừng thay vì thay thế guard hiện tại.
