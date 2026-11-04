# AWG relay installer

Khôi phục tuyến **AWG legacy điện thoại → AWG kernel trên relay → Linux routing/SNAT → AWG 3.1 → Linux NAT trên exit**.

## Một lệnh

Đăng nhập **root** trên VPS Ubuntu 24.04 amd64 rồi chạy:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/install.sh)
```

Bộ cài hỏi công việc, IP công khai của relay/exit và **mật khẩu khôi phục riêng**. Mật khẩu không hiển thị khi nhập, không được lưu trên GitHub. Cần có `curl` để chạy lệnh đầu; các phụ thuộc còn lại được cài tự động.

Bản `v1.1.1` sửa lỗi đọc terminal khiến bản `v1.1.0` dừng ngay sau menu với thông báo “Cần terminal tương tác”. Nếu gặp lỗi này, chạy lại lệnh trên để tải bản sửa; gói mã hóa và mật khẩu khôi phục giữ nguyên.

## Thứ tự khi đổi cả hai VPS

1. Trên **exit mới**, chạy lệnh và chọn **1 — Cài exit mới**. Không cần cài LucX để riêng backhaul hoạt động.
2. Trên **relay mới**, chạy cùng lệnh và chọn **2 — Cài relay mới**. Bộ cài tự tải LucX `v3.11.0-lucx.339`, kiểm tra SHA256, cài panel, module kernel và hạ tầng. **Bạn không cần cài LucX trước.**
3. Khi hoàn tất, terminal in **URL panel HTTPS, username và password** mới. Mở URL đó rồi **Restore/Import database** bằng file `.db` mới nhất đã tải từ panel cũ. Chọn **Keep host settings** để giữ URL/HTTPS mới; tài khoản đăng nhập có thể trở về tài khoản trong backup.
4. Chạy lại cùng lệnh, chọn **3 — Kiểm tra relay** hoặc **4 — Kiểm tra exit**. Thử điện thoại, DNS/web, IP thoát và traffic; kiểm tra sau reboot trên VPS mới trước khi bỏ máy cũ.

Khách dùng IP phải đổi Endpoint sang `IP_RELAY_MỚI:2445`. Khách dùng domain có thể giữ Endpoint khi DNS được đổi sang relay mới (DNS only).

Panel mới dùng HTTPS với chứng chỉ tự ký: trình duyệt sẽ yêu cầu chấp nhận chứng chỉ lần đầu. Thông tin đăng nhập được lưu riêng trên relay tại `/etc/x-ui/awg-installer-panel.json`, không đưa lên GitHub. Nếu đã có LucX, bộ cài giữ nguyên database, phiên bản và tài khoản; không tự nâng cấp hoặc reset.

Firewall của nhà cung cấp cần cho phép **UDP 2445 và TCP 2053 trên relay**, **UDP 8443 trên exit chỉ từ IP relay**. Bộ cài chỉ quản lý firewall trong VPS; nếu UFW đang bật, nó cho phép thêm TCP 2053 để mở panel, không tự bật UFW.

## Nếu chỉ thay một máy

- **Chỉ thay exit:** dựng exit mới, sau đó trên relay đang giữ chọn **5 — Đổi IP exit**. Điện thoại giữ nguyên Endpoint.
- **Chỉ thay relay:** trên exit đang giữ chọn **6 — Cho phép IP relay mới**, cập nhật cả firewall nhà cung cấp nếu có, rồi dựng relay mới và Restore `.db`.

Không chạy lựa chọn cài mới trên VPS đang có tunnel `awg32`; bộ cài sẽ dừng. Các lựa chọn kiểm tra và đổi IP được dùng trên máy đang hoạt động.

## Lưu những gì?

- **Một lần:** địa chỉ repo này và mật khẩu khôi phục riêng. Nên giữ thêm bản offline của gói hạ tầng.
- **Khi thay đổi khách:** tải file **`.db` đầy đủ bằng Backup của LucX relay**, nhất là sau thêm/xóa/gia hạn/đổi quota và ngay trước khi chuyển VPS.

Repo không chứa database khách, tài khoản panel hay khóa VPN ở dạng rõ. File `infrastructure.enc` chứa hạ tầng cố định được mã hóa AES-256-GCM, khóa dẫn xuất bằng scrypt; không có mật khẩu thì không phục hồi được. Mã hóa dùng thư viện [cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/). Installer xác thực dữ liệu trước khi giải nén/chạy, dùng thư mục tạm riêng và xóa bản giải mã tạm khi hoàn tất.

Thêm/sửa khách chỉ cần backup `.db` mới. Nếu đổi khóa backhaul, subnet/ID inbound, MTU/MSS hoặc engine/routing thì cần tạo phiên bản hạ tầng mới. Phiên bản này giữ subnet `10.8.0.0/24`, inbound legacy ID 1 và UDP 2445.

## Tùy chọn

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/main/install.sh) --help
```

Có thể truyền `--role exit|relay|check-relay|check-exit|repoint-relay|allow-relay`, `--relay-ip`, `--exit-ip`, `--nic`; mật khẩu vẫn được hỏi ẩn. `--dry-run` dùng cho relay/exit, cần cài sẵn phụ thuộc và không thay đổi hạ tầng.

Gói có engine/tools amd64 đã chạy và mã nguồn upstream tương ứng; module kernel được biên dịch lại cho kernel của relay mới bằng DKMS. LucX và geodata được tải trực tiếp từ bản upstream đã ghim, kiểm tra kích thước/SHA256; không làm phình gói khóa mã hóa. Lần đầu relay tải khoảng 163 MB LucX và 28 MB geodata. Cần APT/Internet và headers khớp kernel. Module đã dùng trên kernel 6.8; kernel khác cần kiểm tra tương thích. Không tự reboot hoặc tự gỡ module AWG khác đang nạp.

CI kiểm tra nhập menu/IP qua terminal Linux thật và stdin dạng pipe, mã hóa/giải mã, mật khẩu sai/dữ liệu hỏng, checksum, giải nén an toàn, dry-run và cài LucX thật trên Ubuntu runner: mở HTTPS, đăng nhập, tải/Restore database trống và khởi động lại panel. Chưa chứng nhận phục hồi đầy đủ cả hai VPS/backhaul trên VPS trắng; không chạy lại installer trên hệ thống sản xuất chỉ để kiểm tra.
