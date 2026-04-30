# Hướng dẫn & Giải thích Yêu cầu Đồ án Mạng Máy Tính (Assignment 1)

Dựa trên đoạn tài liệu bạn vừa cung cấp, bài tập lớn này có quy mô rộng hơn và phức tạp hơn so với bản Chat dòng lệnh (CLI) cơ bản mà chúng ta vừa test. 

Dưới đây là giải thích chi tiết, được bóc tách thành từng module để bạn dễ hình dung:

---

## 1. Bức tranh toàn cảnh (Goal & Content)
Mục tiêu của bài tập là bạn phải tự tay code một **Hệ thống mạng giao tiếp** từ con số 0 (chỉ dùng thư viện `socket` chuẩn của Python, không dùng các framework có sẵn như NodeJS, Express, hay Django). 

Hệ thống này bao gồm 2 mảnh ghép chính:
1. **Một Web Server (HTTP Server)**: Có thể hiểu được các request HTTP (GET, POST, PUT, DELETE) và trả về trang web/dữ liệu. Đóng vai trò làm backend cho ứng dụng.
2. **Ứng dụng Chat P2P (Mạng ngang hàng)**: Cho phép người dùng nhắn tin trực tiếp cho nhau.

---

## 2. Chi tiết 3 Yêu cầu Cốt lõi (Implementation)

### Yêu cầu 2.1: Implement non-blocking mechanisms (Cơ chế không đồng bộ)
- **Đề bài yêu cầu:** Web Server của bạn phải có khả năng xử lý hàng ngàn kết nối cùng lúc mà không bị treo (đứng máy). Bạn phải làm được điều này bằng 3 cách (hoặc hỗ trợ chuyển đổi giữa các cách):
  1. `Multi-threading` (Đa luồng).
  2. `Callback / Event-driven` (Dùng hàm callback và `selectors`).
  3. `Coroutine` (Dùng `async/await` của asyncio).
- **Tình trạng code hiện tại:** Tốt! File `daemon/backend.py` của chúng ta đã có đủ code để đổi qua lại giữa 3 chế độ này (thông qua biến `mode_async`).

### Yêu cầu 2.2: Implement the authentication for HTTP server (Xác thực người dùng)
- **Đề bài yêu cầu:** Server phải biết được ai đang đăng nhập. Có 2 chuẩn phải tuân theo:
  1. Dùng Header `Authorization` (Chuẩn RFC 2617 / 7235).
  2. Dùng `Cookies` và `Set-Cookie` (Chuẩn RFC 6265) để duy trì phiên đăng nhập (Session) trên trình duyệt web.
- **Tình trạng code hiện tại:** Chúng ta đã có phần phân tích Header `Authorization` trong `request.py`. Tuy nhiên, phần tạo/quản lý Cookie cho trình duyệt có thể bạn sẽ phải code thêm vào `response.py` để Web UI hoạt động trơn tru.

### Yêu cầu 2.3: Implement hybrid chat application (Ứng dụng Chat lai)
Đây là phần **Nặng nhất** và **Quan trọng nhất** mà tài liệu của bạn vừa hé lộ. Phiên bản màn hình đen (CLI) lúc nãy chưa đủ để ăn trọn điểm. Đề bài yêu cầu **Phải có Giao diện Web (Web UI)**.

**Kiến trúc Lai (Hybrid) nghĩa là gì?**
1. **Client-Server (Đoạn khởi tạo):** Khi user mở trình duyệt, giao diện Web sẽ gọi API (ví dụ: `POST /login`) lên Python Server để đăng nhập. Server đóng vai trò như Tracker, lưu lại IP của user đó. Để lấy danh sách bạn bè, Web gọi API `GET /get-list`.
2. **Peer-to-Peer (Đoạn nhắn tin):** Khi user muốn chat, gửi thông tin qua các API như `/connect-peer` hoặc `/send-peer`. Backend Python của người gửi sẽ mở Socket **kết nối trực tiếp** sang Backend Python của người nhận, thay vì gửi tin nhắn đi lòng vòng qua Server trung tâm.

**Yêu cầu tính năng cho Giao diện Chat (Channel Management):**
- **Channel listing:** Xem được danh sách các kênh/phòng chat.
- **Message display:** Cửa sổ hiển thị tin nhắn (có thanh cuộn).
- **Message submission:** Ô nhập text và nút Gửi.
- **Notification:** Có thông báo khi tin nhắn mới tới.
- **Frontend Rules:** Chỉ được phép dùng Javascript ở phía Trình duyệt (Client-side) để lấy dữ liệu (Fetch/AJAX) và cập nhật giao diện (Asynchronously). **Nghiêm cấm** dùng framework Backend viết sẵn. Mọi thứ xử lý logic mạng bên dưới phải do Python Socket đảm nhận.

---

## 3. Đánh giá Khối lượng Công việc còn lại

Qua tài liệu trên, có thể thấy code hiện tại của chúng ta mới chỉ đạt được **Phần Khung Xương (Backend Engine)**. 

Để hoàn thành 100% đồ án, bạn sẽ cần làm tiếp:
1. **Code Giao diện Web (HTML/CSS/JS):** Tạo file `chat.html` có khung chat, danh sách bạn bè (Giống với file `login.html` bạn đang có).
2. **Tích hợp API vào Backend:** Chuyển đổi các logic chat từ màn hình đen (`apps/peer.py`) sang các API dạng RESTful trong `sampleapp.py`. Cụ thể, bạn phải viết các hàm `@app.route('/send-peer')`, `@app.route('/get-list')`... để trình duyệt Web có thể bấm nút Gửi tin nhắn và gọi xuống Python.
3. **Xử lý Session/Cookie:** Đảm bảo khi User F5 trình duyệt, server Python vẫn nhận diện được user thông qua Cookie.
