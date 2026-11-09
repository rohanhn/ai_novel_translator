---
 status: draft
 created_date: 2026/11/09
 version: 0.1
---

# 0. Bối cảnh:

Người đọc/dịch tiểu thuyết mạng Trung Quốc tại Việt Nam hiện thường phải ghép nhiều công cụ rời rạc: QuickTranslator/QuickConverter, VietPhrase/Name dictionary, Google Translate hoặc công cụ tra cứu, Notepad/Word để biên tập, và một reader/website khác để đọc.

Các vấn đề chính:

- Workflow copy-paste, tra cứu, convert, edit và đọc bị phân tán.
- Tên nhân vật, địa danh, môn phái, cảnh giới, công pháp và cách xưng hô thiếu nhất quán giữa các chương.
- Mỗi người có gu văn phong riêng (convert sát nghĩa, Hán–Việt, cổ phong, thuần Việt, ngôn tình hiện đại), nhưng các công cụ hiện tại khó quản trị thành cấu hình theo từng truyện.
- Dữ liệu từ điển, raw, bản nháp, bản edit và tiến độ đọc thường nằm rải rác theo thiết bị/phần mềm.
- Các giải pháp có sẵn đã có nhiều năng lực convert/dictionary/reader; sản phẩm mới không nên cạnh tranh chỉ bằng “dịch Trung–Việt online”.
-
# 1. Ý tưởng:

- Website app cung cấp khả năng dịch truyện mạng, chủ yếu là tiểu thuyết mạng trung quốc từ các trang web cho đọc truyện free hoặc từ nguồn raw do người dùng sưu tầm và upload
- Tính năng dịch tương tự vietphase hay quickstranslator offline: dịch từng chương, lưu trữ tên riêng cho từng truyện, khả năng edit trực tiếp. Khả năng chia sẻ bộ từ điển tên giữa các bộ truyện hoặc tạo riêng từng bộ

# 2. Tầm nhìn:

Xây dựng một **personal translation-and-reading workspace**: không gian riêng tư trên web để người dùng nhập nguồn truyện, dịch nhanh, quản lý glossary/ngữ cảnh, biên tập và đọc lại trong một workflow thống nhất.

# 3. Quy tắc bản quyền và nguồn nội dung:

Sản phẩm được định vị là công cụ xử lý nội dung do người dùng cung cấp hoặc chủ động yêu cầu nhập vào kho riêng. Tuy nhiên, không dùng tuyên bố tuyệt đối “nền tảng không chịu trách nhiệm” như một thay thế cho các biện pháp vận hành.

## Nguyên tắc cần áp dụng

- Library là **private-by-default**; không có URL public, không index cho công cụ tìm kiếm.
- User xác nhận họ có quyền truy cập và sử dụng nội dung trước mỗi lần import URL.
- Chỉ xử lý nội dung mà connector được phép truy cập theo `robots.txt`, điều khoản nguồn và các tín hiệu kỹ thuật tại thời điểm lấy dữ liệu.
- Không truy cập khi gặp login, paywall, CAPTCHA, HTTP 401/403/429, DRM hoặc cấu trúc nguồn không xác định.
- Không lưu raw cache dùng chung giữa nhiều user; mỗi lần import phải có audit record theo user.
- Lưu source URL, source platform, thời điểm import và trạng thái truy cập cho từng truyện/chương.
- Có chức năng xóa dữ liệu và quy trình tiếp nhận/gỡ nội dung bị khiếu nại.

## Xác nhận khi import

- Tôi xác nhận có quyền truy cập và sử dụng nội dung từ URL này trong thư viện riêng của mình. Hệ thống không hỗ trợ truy cập nội dung cần thanh toán, đăng nhập hoặc cơ chế xác thực; nội dung không được công khai lại mặc định.

# 4. Phạm vi crawler/link import 

## 4.1 Luồng chính

```text
User dán URL truyện
→ Hệ thống nhận diện domain/connector
→ Kiểm tra access policy (robots, terms, login, paywall, CAPTCHA)
→ Lấy preview metadata và chapter manifest nếu được phép
→ User xác nhận import vào private library
→ Chỉ tải raw của chương đầu tiên
→ User dịch/edit/đọc chương 1
→ Khi đang tương tác với chương N, hệ thống prefetch raw chương N+1 nếu được phép
→ User bấm cập nhật danh sách chương khi cần
```

## 4.2 Quy tắc crawler

| Tác vụ | Trạng thái MVP | Điều kiện/giới hạn |
|---|---|---|
| Nhập URL truyện | Có | Chỉ domain trong allowlist và connector đã kiểm thử |
| Lấy metadata truyện | Có | Lưu title, author, cover nếu phù hợp, source URL, source platform |
| Lấy chapter manifest | Có | Chỉ metadata/URL chương hiển thị công khai; không tải raw hàng loạt |
| Lấy raw chương đầu | Có | Tối đa 1 raw chapter lúc import |
| Buffer raw chương kế | Có điều kiện | Tối đa 1 chương N+1, chỉ khi user đang đọc/dịch N và nguồn cho phép |
| Tự dịch chương kế | Không | Chỉ buffer raw, không gọi AI trước khi user yêu cầu |
| Cập nhật manifest | Có, thủ công | User-triggered, chỉ delta metadata, có cooldown |
| Auto-update | Không | Không cron, polling hoặc tự theo dõi chương mới |
| Crawl full novel | Không | Không bulk queue hoặc `fetchAllChapters()` |

## 4.3 Trigger prefetch raw chương N+1

Prefetch chỉ khởi chạy khi có ít nhất một tín hiệu:

- User đọc chương hiện tại ít nhất 30–45 giây.
- User đã scroll khoảng 60–70% chương hiện tại.
- User bắt đầu chạy dịch AI cho chương hiện tại.
- User bấm rõ ràng nút “Chuẩn bị chương tiếp theo”.

Điều kiện chặn prefetch:

- Đã có raw buffer cho N+1.
- User đã rời workspace/truyện hoặc chuyển sang chương khác.
- N+1 không tồn tại trong manifest.
- Nguồn chặn automation hoặc xuất hiện login/paywall/CAPTCHA/403/429.
- Hệ thống vượt rate limit/cooldown của domain hoặc user.

## 4.4 Nguồn truyện/connector ưu tiên

Danh sách candidate ban đầu cần được kiểm tra pháp lý, robots.txt, điều khoản, cấu trúc HTML và độ ổn định trước khi đưa vào allowlist:

- Qidian (起点中文网)
- Jinjiang Literature City / JJWXC (晋江文学城)
- Zongheng (纵横中文网)
- 17K (17K小说网)
- Fanqie (番茄小说) hoặc Faloo (飞卢小说网)

**Lưu ý:** đây là danh sách nghiên cứu connector, không phải cam kết hỗ trợ. Một domain chỉ được bật khi access-policy check, legal review và test vận hành đều đạt yêu cầu.

# 5. Yêu cầu sản phẩm:
- Giao diện web, hỗ trợ responsive mobile
- Giao diện đọc tối ưu cho việc đọc sách (thay đổi màu nền, lật trang) tương tự sách điện tử
- độ mượt khi đọc (giảm tối đa chờ load)

