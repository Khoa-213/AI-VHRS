# Luồng hủy sau cọc và hoàn tiền trên web

Tài liệu mô tả luồng hủy đơn sau khi đặt cọc và hoàn tiền (FR-19, FR-20, UC-21, UC-28; BR-14, BR-16) như hiện đã nối trên FE. Gồm: luật do backend quyết định, từng màn hình theo role, API đã nối, file code, thông báo liên quan, những gì đã kiểm tra và những giới hạn còn lại.

Nguồn đối chiếu: `BE/docs/FE_API_GUIDE.md` mục 7h (hủy và hoàn tiền) và 7i (ETA), cùng code `BE/app/api/v1/refunds.py`, `BE/app/services/refunds.py`.

## 1. Nguyên tắc

- **Backend quyết định mọi luật và số tiền.** FE chỉ hiển thị kết quả của `cancel-preview` và gửi yêu cầu. FE không tự tính số hoàn.
- **Không có tiền thật nào đi qua hệ thống ở bước hoàn.** Backend chỉ tạo một dòng `REFUND` ở trạng thái chờ. Staff tự chuyển khoản ngoài hệ thống, rồi bấm xác nhận kèm mã giao dịch. Cổng thanh toán (payOS, VNPay, MoMo) không được gọi để hoàn.
- Mọi chữ hiển thị đều có đủ tiếng Anh, Việt, Nhật (quy tắc `FE/AGENTS.md`). Riêng nội dung thông báo trong chuông do backend soạn bằng tiếng Việt.

## 2. Luật hủy và hoàn (backend, BR-14 và BR-16)

Áp dụng cho đơn đã cọc (`CONFIRMED`):

| Lúc hủy (`production_status`) | Được hủy? | Số hoàn | Mã luật (`rule`) |
|---|---|---|---|
| `PENDING_SCHEDULE` (chưa xếp lịch) | Có | 100% tiền cọc | `BR14_BEFORE_SCHEDULE` |
| `SCHEDULED`, `PREPARING` (đã xếp lịch, chưa viết) | Có | Cọc trừ phí setup của báo giá đã duyệt (không âm) | `BR14_AFTER_SCHEDULE` |
| `WRITING` (robot đang viết) | **Không** | không | lỗi `JOB_RUNNING` |
| Đã bắt đầu viết (`PAUSED`, `WRITTEN`, `PHOTO_UPLOADED`, `REWRITE_REQUIRED`, `FAILED`, hoặc đơn viết lại đã từng viết) | Chỉ khi ETA đã dời cộng dồn **vượt ngưỡng** (mặc định 7 ngày) | 100% số đã trả | `BR16_ETA_POSTPONED`; chưa vượt thì lỗi `CANCEL_AFTER_WRITING_STARTED` |
| Xưởng (Staff) hủy vì không làm được | Theo cùng quy tắc thời điểm ở trên | 100% số đã trả | `WORKSHOP_CANCEL` |

- Từ `AWAITING_ACCEPTANCE` trở đi không hủy được.
- Đơn chưa cọc vẫn hủy như cũ (`rule = NO_PAYMENT`), không có khoản hoàn.
- Cọc qua **payOS**: khách bắt buộc nhập tài khoản nhận hoàn khi hủy (`account_required = true`), thiếu thì lỗi `REFUND_ACCOUNT_REQUIRED`.

## 3. Luồng tổng thể

```
Khách cọc xong (CONFIRMED)
        |
        +--> Khách bấm "Hủy đơn" -----------+
        |                                   |
        +--> Staff được giao đơn bấm        |
             "Huỷ đơn (xưởng không làm được)"
                                            v
                  GET .../cancel-preview  (xem trước: có hủy được không, hoàn bao nhiêu)
                                            |
                                  nhập lý do (+ tài khoản nếu payOS)
                                            v
                         POST .../cancel  ->  đơn CANCELLED
                         tạo dòng REFUND, trạng thái PENDING
                         hủy job sản xuất (nếu có)
                                            |
                  thông báo: khách nhận ORDER_CANCELLED + REFUND_REQUESTED
                             Staff được giao nhận REFUND_TO_PROCESS
                             kỹ thuật viên nhận JOB_CANCELLED (nếu đã có job)
                                            |
        Khách thêm / đổi tài khoản nhận tiền (khi còn PENDING)
                                            |
        Staff vào /staff/refunds, tab "Cần chuyển"
        chuyển khoản tay ngoài hệ thống
        bấm "Đánh dấu đã chuyển" + mã giao dịch
                                            v
                  POST /workshop/refunds/{id}/confirm  ->  SUCCESS
                  khách nhận thông báo REFUND_SENT
                  thẻ hoàn của khách đổi thành "Đã hoàn" kèm mã giao dịch
```

## 4. Màn hình theo role

### 4.1 Khách hàng: trang đơn `/orders/{id}/review`

File: [PaidOrderPanel.tsx](../src/pages/order/PaidOrderPanel.tsx), gắn trong [OrderReview.tsx](../src/pages/order/OrderReview.tsx).

Khối nằm ở cột bên phải của trang đơn, hiện với đơn ở các trạng thái `CONFIRMED`, `AWAITING_ACCEPTANCE`, `AWAITING_FINAL_PAYMENT`, `READY_TO_DELIVER`, `DELIVERING`, và `CANCELLED` (để xem khoản hoàn sau khi hủy).

Gồm ba phần:

1. **Ngày giao dự kiến (ETA)**, không hiện với đơn đã hủy: "Dự kiến giao: {ngày}", số ngày đã dời, và nếu vượt ngưỡng thì dòng "bạn có thể huỷ và được hoàn đủ". Có mục xổ ra "Lịch sử đổi ngày giao" gồm ngày cũ, ngày mới, lý do, thời điểm.
2. **Thẻ khoản hoàn** (mỗi dòng `REFUND` một thẻ xanh):
   - Tiêu đề: "Hoàn {số tiền} đang chờ xưởng chuyển" hoặc "Đã hoàn {số tiền}".
   - Luật áp dụng (ví dụ "Chưa xếp lịch: hoàn toàn bộ tiền cọc"), số tiền xưởng giữ lại nếu có.
   - Tài khoản nhận (số tài khoản che, chỉ lộ 4 số cuối), hoặc nhắc "Chưa có tài khoản nhận tiền".
   - Mã giao dịch và giờ xác nhận khi đã chuyển.
   - Khi còn chờ: link **"Thêm tài khoản nhận tiền"** hoặc **"Đổi tài khoản nhận tiền"**, mở form 3 ô (ngân hàng, số tài khoản 6 đến 20 chữ số, chủ tài khoản).
3. **Nút "Hủy đơn"**, chỉ với đơn `CONFIRMED`:
   - Bấm mở hộp xem trước (`cancel-preview`): hoặc báo không hủy được (kèm lý do đã dịch), hoặc "Bạn sẽ được hoàn {số tiền}", luật, số đã trả, số xưởng giữ lại.
   - Khi hủy được: ô lý do (tối đa 500 ký tự). Nếu cọc qua payOS và số hoàn lớn hơn 0 thì hiện thêm form tài khoản.
   - Nút xác nhận chỉ bật khi có lý do, và (nếu cần) tài khoản hợp lệ.
   - Hủy xong: tải lại thẻ hoàn và trang đơn.

Trang đơn tự tải lại khi có thông báo mới liên quan đến đơn đó.

### 4.2 Staff: chi tiết đơn `/staff/review/{id}`

File: [PaidOrderDesk.tsx](../src/pages/staff/PaidOrderDesk.tsx), gắn trong [OrderDetail.tsx](../src/pages/staff/OrderDetail.tsx).

Khối **"Ngày giao và huỷ đơn"** hiện với đơn từ `CONFIRMED` trở đi và `CANCELLED` (ẩn nếu đơn hủy mà chưa từng có khoản hoàn):

- **ETA:** ngày hiện tại, tổng số ngày đã dời so với giới hạn, ETA ước tính nếu xác nhận lúc này, cảnh báo khi vượt ngưỡng, lịch sử đổi kèm người đổi (hệ thống hay nhân viên).
- **Đổi ETA:** chỉ **Staff được giao đơn**, với đơn `CONFIRMED`, `AWAITING_ACCEPTANCE`, `AWAITING_FINAL_PAYMENT`, `READY_TO_DELIVER`. Chọn ngày mới và nhập lý do rồi bấm "Đổi ngày giao".
- **Danh sách khoản hoàn của đơn** (chỉ đọc), kèm tài khoản nhận đầy đủ nếu có.
- **"Huỷ đơn (xưởng không làm được)":** chỉ Staff được giao đơn và chỉ với đơn `CONFIRMED`. Có hộp xem trước và nhập lý do, hoàn 100% theo luật `WORKSHOP_CANCEL`.

Manager mở cùng trang nhưng chỉ **xem**, không có nút đổi ETA hay hủy.

### 4.3 Staff và Manager: trang hoàn tiền `/staff/refunds`

File: [Refunds.tsx](../src/pages/staff/Refunds.tsx). Có mục "Hoàn tiền" (icon tiền) ở thanh bên của Staff và Manager, kèm **số đếm** khoản đang chờ chuyển cộng tiền về sai (cập nhật mỗi 60 giây).

Hai tab: **"Cần chuyển"** (`PENDING`) và **"Đã chuyển"** (`SUCCESS`). Trang tự tải lại mỗi 30 giây. Staff thấy đơn của mình, Manager thấy tất cả.

**Thẻ khoản hoàn:** số đơn (link sang chi tiết đơn), số tiền, luật hoặc lý do, tài khoản nhận đầy đủ, số xưởng giữ lại, mã giao dịch và giờ xác nhận nếu đã chuyển.

**Xác nhận đã chuyển** (chỉ Staff, chỉ khoản đang chờ): nút "Đánh dấu đã chuyển" mở form:
- Mã giao dịch chuyển khoản (**bắt buộc**).
- Ghi chú (không bắt buộc).
- Nếu khách chưa nhập tài khoản: form 3 ô tài khoản **không bắt buộc**. Điền thì phải điền đủ cả 3 ô, bỏ trống hết thì thôi.
- Bấm "Xác nhận đã chuyển tiền".

**Thẻ tiền về sai** (`needs_refund`, thẻ viền đỏ "Cần hoàn tiền"): hiện cổng, loại, số tiền nhận được và trạng thái đơn. Staff bấm "Tạo yêu cầu hoàn tiền", nhập lý do (bắt buộc) và tài khoản (không bắt buộc, đủ 3 ô hoặc bỏ trống). Khoản hoàn luôn bằng **toàn bộ** số tiền nhận được.

## 5. API đã nối

Tất cả dưới `/api/v1`. Code gọi API nằm ở [refunds.ts](../src/services/refunds.ts).

| Role | API | Dùng ở đâu |
|---|---|---|
| Khách | `GET /orders/{id}/cancel-preview` | Hộp xem trước khi bấm "Hủy đơn" |
| Khách | `POST /orders/{id}/cancel` (`reason`, `refund_account?`) | Xác nhận hủy sau cọc |
| Khách | `GET /orders/{id}/payments` | Lấy các dòng `type = REFUND` để dựng thẻ hoàn |
| Khách | `PUT /orders/{id}/refunds/{refund_id}/account` | Thêm hoặc đổi tài khoản nhận hoàn |
| Khách | `GET /orders/{id}/eta` | Khung ETA và lịch sử |
| Staff, Manager | `GET /workshop/orders/{id}/cancel-preview` | Hộp xem trước khi xưởng hủy |
| Staff | `POST /workshop/orders/{id}/cancel` (`reason`) | Xưởng hủy, hoàn 100% |
| Staff, Manager | `GET /workshop/orders/{id}/payments` | Khoản hoàn trong chi tiết đơn |
| Staff, Manager | `GET /workshop/refunds?status=PENDING\|SUCCESS` | Trang hoàn tiền và số đếm thanh bên |
| Staff | `POST /workshop/refunds/{id}/confirm` (`reference`, `note?`, `refund_account?`) | "Đánh dấu đã chuyển" |
| Staff | `POST /workshop/payments/{id}/refund` (`reason`, `amount?`, `refund_account?`) | Tạo yêu cầu hoàn cho tiền về sai |
| Staff, Manager | `GET /workshop/orders/{id}/eta` | Khối ETA của Staff |
| Staff | `POST /workshop/orders/{id}/eta` (`eta`, `reason`) | Đổi ETA |

Các route `webhooks` và cổng thanh toán không liên quan tới luồng này.

## 6. Thông báo liên quan

Hiện trong chuông (xem thêm [NOTIFICATIONS.md](NOTIFICATIONS.md)):

| Ai | Thông báo | Khi nào |
|---|---|---|
| Khách | `ORDER_CANCELLED` | Đơn bị hủy (kèm số tiền hoàn nếu có) |
| Khách | `REFUND_REQUESTED` | Yêu cầu hoàn được tạo |
| Khách | `REFUND_SENT` | Staff xác nhận đã chuyển |
| Khách | MSG11 (`ETA_POSTPONED`) | ETA dời muộn hơn (cũng gửi email) |
| Staff được giao | `REFUND_TO_PROCESS` ("Cần hoàn tiền") | Có đơn hủy cần chuyển hoàn |
| Kỹ thuật viên | `JOB_CANCELLED` | Đơn hủy nên job của mình hủy theo |

Khi bấm thông báo hoàn tiền: Staff được dẫn tới `/staff/refunds`, khách được dẫn tới trang đơn.

## 7. Mã lỗi đã có bản dịch

Thêm vào `ERROR_KEYS` trong [orders.ts](../src/services/orders.ts) và các khóa `err.*`:

`JOB_RUNNING`, `CANCEL_AFTER_WRITING_STARTED`, `REFUND_ACCOUNT_REQUIRED`, `REFUND_NOT_PENDING`, `REFUND_EXISTS`, `ETA_NOT_EDITABLE`, `ETA_IN_PAST`, `ETA_TOO_FAR`, `ETA_UNCHANGED`. Các mã lỗi khác hiển thị đúng thông điệp của backend.

## 8. Danh sách file đã tạo và đã sửa

**Tạo mới**
- `src/services/refunds.ts`: toàn bộ API hủy, hoàn tiền và ETA.
- `src/pages/order/PaidOrderPanel.tsx`: khối hủy, thẻ hoàn, ETA cho khách. Xuất thêm `AccountFields` (3 ô tài khoản) dùng chung với trang Staff.
- `src/pages/staff/PaidOrderDesk.tsx`: ETA, hủy cho xưởng, danh sách khoản hoàn trong chi tiết đơn.
- `src/pages/staff/Refunds.tsx`: trang `/staff/refunds`.

**Sửa**
- `src/pages/order/OrderReview.tsx`: gắn `PaidOrderPanel` (đơn đã cọc và đơn đã hủy), tự tải lại khi có thông báo của đơn.
- `src/pages/staff/OrderDetail.tsx`: gắn `PaidOrderDesk`.
- `src/components/ws/Shell.tsx`: mục "Hoàn tiền" ở thanh bên kèm số đếm.
- `src/App.tsx`: route `/staff/refunds`.
- `src/services/orders.ts`: các mã lỗi mới ở mục 7.
- `src/i18n/en.ts`, `vi.ts`, `ja.ts`: khóa `rf.*`, `eta.*` và `err.*` mới.
- `src/components/ui/notification-bell.css`: kiểu cho danh sách lịch sử ETA (`.eta-history`).

## 9. Đã kiểm tra những gì

- `npx tsc -b`, `npm run i18n:check`, `npm run build` đều qua.
- Đã đối chiếu dữ liệu FE gửi và nhận với schema backend (`ops_schemas.py`, `refunds.py`, `payments.py`) và quy tắc `confirm` và `set_refund_account` (tài khoản khi xác nhận là không bắt buộc).
- **Chưa test bằng trình duyệt hay backend thật.** Các ca test nên chạy xem [REFUND test cases bên dưới](#10-ca-test-gợi-ý).

## 10. Ca test gợi ý

Luồng chính (đã đưa trong hội thoại):
1. **Hủy khi chưa xếp lịch:** hoàn 100% cọc, đơn `CANCELLED`, khách thấy thẻ hoàn chờ chuyển, Staff nhận "Cần hoàn tiền".
2. **Hủy khi đã xếp lịch:** hoàn = cọc trừ phí setup, kỹ thuật viên nhận `JOB_CANCELLED`.
3. **Không cho hủy:** robot đang viết (`WRITING`), đã viết mà ETA chưa dời quá ngưỡng, từ chờ nghiệm thu trở đi.
4. **Tài khoản nhận hoàn:** cọc payOS bắt buộc nhập; số tài khoản sai định dạng khóa nút; khách thấy dạng che, Staff thấy đầy đủ; đổi được khi còn chờ, không đổi được sau khi đã chuyển.
5. **Xưởng xử lý:** xác nhận không tài khoản được; xác nhận hai lần lỗi `REFUND_NOT_PENDING`; Staff chỉ thấy đơn của mình, Manager chỉ xem.
6. **Tiền về sai:** chỉ thử được khi có khoản `needs_refund`; tạo yêu cầu hoàn hai lần cho cùng khoản báo `REFUND_EXISTS`.
7. **Thông báo và thanh bên:** badge "Hoàn tiền" tăng giảm đúng, bấm thông báo mở đúng trang.

## 11. Giới hạn hiện tại

- **Không hoàn qua cổng thanh toán.** Staff phải chuyển khoản tay, đây là thiết kế của backend.
- **Tiền về sai luôn hoàn đủ.** Backend nhận `amount` tùy chọn nhưng FE chưa có ô nhập số tiền riêng.
- **Khách chỉ thấy khoản hoàn trên trang đơn**, chưa có mục "Lịch sử hoàn tiền" trong `/account`.
- **Đơn `COMPLETED`** không hiện khối hủy, hoàn tiền hay ETA cho khách.
- **Nội dung thông báo là tiếng Việt** vì do backend soạn, không dịch theo ngôn ngữ giao diện.
- **Chưa có màn cảnh báo robot cho Manager** và các API backend khác chưa nối (xem danh sách chưa nối trong hội thoại trước). Không ảnh hưởng luồng hoàn tiền.
- **Số đếm thanh bên** cập nhật theo chu kỳ 60 giây, không tức thời.
