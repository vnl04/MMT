# CO3093 / CO3094 — AsynapRous (Assignment 1)

**Trường:** Đại học Bách Khoa TP.HCM (HCMUT) · Khoa Khoa học & Kỹ thuật Máy tính  

Dự án triển khai **HTTP server không chặn (non-blocking)**, **xác thực HTTP** và **ứng dụng chat lai (client–server + P2P)** theo framework **AsynapRous** (Python, chủ yếu thư viện chuẩn `socket`).

---

## Yêu cầu môi trường

- **Python 3** (khuyến nghị 3.10+)
- Chạy từ **thư mục gốc** của repo này (để import `daemon`, `apps`, `chat` đúng).

```bash
cd CO3094-asynaprous
```

---

## Chạy nhanh — Webapp + giao diện chat

1. Khởi động server webapp (mặc định cổng **2026**):

```bash
python start_sampleapp.py
```

Tùy chỉnh:

```bash
python start_sampleapp.py --server-ip 0.0.0.0 --server-port 2026
```

2. Mở trình duyệt (nên dùng tab **ẩn danh** khi thử cookie/session):

- Trang đăng nhập: `http://127.0.0.1:2026/login.html`
- Trang chat: `http://127.0.0.1:2026/chat.html`

3. **Tài khoản demo** (xem `apps/sampleapp.py`, `USER_DB`):

| Username | Password   |
|----------|------------|
| admin    | admin123   |
| student  | hcmut2026  |
| alice    | alice123   |
| bob      | bob123     |
| guest    | guest      |

Sau khi đăng nhập, cần **đăng ký cổng lắng nghe P2P** trên giao diện chat (ví dụ `7001`, `7002` cho hai người dùng khác nhau) để `/send-peer` có thể mở TCP trực tiếp tới peer.

---

## Các tiến trình khác (theo kiến trúc đề bài)

| Script | Mô tả | Cổng mặc định (tham khảo) |
|--------|--------|---------------------------|
| `start_sampleapp.py` | Webapp AsynapRous + REST chat | **2026** |
| `start_backend.py` | Backend HTTP đơn giản | **9000** |
| `start_proxy.py` | Reverse proxy (đọc `config/proxy.conf`) | **8080** |
| `start_tracker.py` | Tracker P2P (giao thức dòng lệnh TCP) | **6000** |
| `start_peer.py` | Peer CLI: đăng ký tracker + chat P2P | peer port tùy chọn |

Ví dụ demo **tracker + peer** (hai terminal):

```bash
python start_tracker.py
python start_peer.py --username alice --peer-port 7001
```

---

## Bố cục mã nguồn (rút gọn)

| Thư mục / file | Nội dung |
|----------------|----------|
| `daemon/` | `backend.py`, `httpadapter.py`, `request.py`, `response.py`, `asynaprous.py` — lõi HTTP |
| `apps/sampleapp.py` | REST: login, peer registry, channel, P2P (`_direct_send`), messages |
| `chat/` | Tracker + peer cho demo P2P dòng lệnh |
| `www/` | `login.html`, `chat.html`, … |
| `static/` | CSS, JS, hình |
| `config/proxy.conf` | Cấu hình proxy |
| `docs/Giai_thich_Yeu_cau_BTL.md` | Giải thích yêu cầu (tiếng Việt) |

---

## Non-blocking (mục 2.1 đề)

Trong `daemon/backend.py`, biến toàn cục **`mode_async`** chọn một trong:

- `"threading"` — mỗi kết nối một luồng (mặc định trong bản hiện tại)
- `"callback"` — vòng lặp `selectors` + callback
- `"coroutine"` — `asyncio` (StreamReader / StreamWriter)

Đổi giá trị rồi chạy lại `start_sampleapp.py` để demo cơ chế tương ứng.

---

## API REST chính (mục 2.3 — đối chiếu đề)

Các handler được khai báo trong `apps/sampleapp.py` (đường dẫn không bắt buộc dấu `/` cuối):

- `POST /login` — đăng nhập, cookie `session=` + token JSON
- `POST /logout` — hủy phiên (client nên gửi `token` trong body như `www/chat.html`)
- `POST /submit-info` — đăng ký IP/port lắng nghe của peer
- `GET /get-list` — danh sách peer đang hoạt động
- `POST /add-list` — tham gia kênh
- `POST /connect-peer` — thử kết nối TCP trực tiếp (probe `PING`)
- `POST /send-peer`, `POST /broadcast-peer` — tin nhắn P2P qua TCP
- `GET|POST /messages` — đọc log tin nhắn đã lưu theo kênh (UI dùng `POST` kèm body `channel`)
- `POST /ping` — heartbeat giữ peer trong registry

---

## Giấy phép & học thuật

Mã nguồn gốc thuộc khóa **CO3093/CO3094** (HCMUT), dùng cho mục đích học tập theo license kèm theo trong đề coursework. Kiểm tra file **LICENSE** (nếu có trong gói) trước khi tái sử dụng ngoài lớp.

---

## Báo cáo / nộp bài

Nén **cả thư mục mã nguồn** kèm báo cáo theo hướng dẫn LMS (tên file dạng `assignment_STUDENTID.zip`). Chi tiết chấm điểm và rubric xem đề Assignment 1 trên portal môn học.
