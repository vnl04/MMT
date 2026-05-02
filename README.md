# CO3093 / CO3094 — AsynapRous (Assignment 1)

**Trường:** Đại học Bách Khoa TP.HCM (HCMUT), Khoa Khoa học & Kỹ thuật Máy tính  

Dự án: **HTTP server không chặn (non-blocking)**, **xác thực HTTP**, **chat lai** (REST + TCP P2P) trên framework **AsynapRous** (Python, chủ yếu thư viện chuẩn `socket`).

**Báo cáo BTL1:** `report/BTL1_Bao_Cao_CO3093.md` (Markdown + sơ đồ Mermaid — xuất PNG tại [mermaid.live](https://mermaid.live) nếu nộp PDF/Word).

### Ghi chú phiên bản

- Chuẩn hoá **`BASE_DIR`** trong `daemon/response.py` để **`www/`** và **`static/`** luôn resolve theo thư mục gốc repo (không phụ thuộc chỗ đứng khi chạy `python ...`).
- Định tuyến **`/login` / `/login/`**; **`401`/`400`** và **`WWW-Authenticate`** cho `POST /login` khi cần; **`POST /logout`** hỗ trợ **`Cookie: session=`**; proxy: timeout **`recv`** backend và **`proxy_pass`** không trùng lặp không cần thiết khi round-robin.

---

## Git — clone và đẩy code

Repo này bao gồm toàn bộ mã trong thư mục clone (đổi tên folder khi clone tùy bạn).

```bash
git clone <URL-repo-cua-ban>.git
cd <ten-thu-muc-repo>
git status
```

Đưa lên nhánh đang làm việc (ví dụ `main`):

```bash
git add -A
git commit -m "Your message"
git push origin main
```

File **`.gitignore`** đã bỏ qua `__pycache__/`, venv, file editor, log. Sau khi pull trên máy khác chỉ cần Python chuẩn, không có dependency `pip` bắt buộc (trừ thư viện chuẩn của Python).

---

## Yêu cầu môi trường

- **Python 3** (khuyến nghị 3.10+)
- Làm việc **trong thư mục gốc clone** của repo để entrypoint import `daemon`, `apps`, `chat` đúng.

---

## Chạy nhanh — Webapp + chat

1. Khởi động webapp (mặc định cổng **2026**):

```bash
python start_sampleapp.py
```

Tùy chỉnh:

```bash
python start_sampleapp.py --server-ip 0.0.0.0 --server-port 2026
```

2. Trình duyệt (nên tab ẩn danh khi thử cookie):

- Đăng nhập: `http://127.0.0.1:2026/login.html`
- Chat: `http://127.0.0.1:2026/chat.html`

3. **Tài khoản demo** (`apps/sampleapp.py`, `USER_DB`):

| Username | Password   |
|----------|------------|
| admin    | admin123   |
| student  | hcmut2026  |
| alice    | alice123   |
| bob      | bob123     |
| guest    | guest      |

Sau khi đăng nhập cần **đăng ký cổng P2P** trên giao diện (ví dụ `7001`, `7002` cho hai user) để `/send-peer` kết nối TCP được.

---

## Các script khác

| Script | Mô tả | Cổng tham khảo |
|--------|--------|----------------|
| `start_sampleapp.py` | Webapp + REST chat | **2026** |
| `start_backend.py` | Backend đơn giản (tutorial) | **9000** |
| `start_proxy.py` | Reverse proxy (`config/proxy.conf`) | **8080** |
| `start_tracker.py` | Tracker P2P | **6000** |
| `start_peer.py` | Peer CLI + tracker | tùy chọn |

Demo tracker:

```bash
python start_tracker.py
python start_peer.py --username alice --peer-port 7001
```

---

## Bố cục mã nguồn

| Thư mục / file | Nội dung |
|----------------|----------|
| `daemon/` | `backend.py`, `httpadapter.py`, `request.py`, `response.py`, `asynaprous.py`, `proxy.py` |
| `apps/sampleapp.py` | REST: login, peer registry, kênh, P2P, messages |
| `chat/` | Tracker + peer dòng lệnh |
| `www/` | `login.html`, `chat.html`, `index.html` |
| `static/` | CSS và tài nguyên tĩnh |
| `config/proxy.conf` | Cấu hình proxy |
| `docs/Giai_thich_Yeu_cau_BTL.md` | Giải thích yêu cầu (tiếng Việt) |

---

## Non-blocking (`daemon/backend.py`)

Biến **`mode_async`**: `"threading"` | `"callback"` | `"coroutine"`. Đổi rồi chạy lại `start_sampleapp.py`.

---

## API REST chính

Xem chi tiết trong `apps/sampleapp.py`:

- `POST /login`, `POST /logout`, `POST /submit-info`, `GET /get-list`, `POST /add-list`
- `POST /connect-peer`, `POST /send-peer`, `POST /broadcast-peer`
- `GET|POST /messages`, `POST /ping`

---

## Kiểm thử

**1.** Cú pháp Python (không cần bật server):

```bash
python -m compileall apps chat daemon start_sampleapp.py start_proxy.py -q
```

**2.** Chạy `python start_sampleapp.py`, sau đó kiểm tra trên browser (`login.html`, `chat.html`).

**3.** Tracker / peer / proxy — theo bảng các script phía trên.

**PowerShell (Windows):** không dùng `&&`; chạy từng lệnh hoặc `Set-Location ...; python ...`.

---

## Giấy phép & học thuật

Mã nguồn khóa **CO3093/CO3094** (HCMUT), học tập theo đề và license coursework. Kiểm tra **LICENSE** nếu có trước khi tái sử dụng ngoài lớp.

---

## Nộp bài

Thu gọn/ghi zip theo hướng dẫn LMS (vd. `assignment_STUDENTID.zip`). Chi tiết chấm xem Assignment 1 trên portal.
