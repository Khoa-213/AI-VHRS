# Thử tay luồng AI-VHRS từ đầu đến cuối

Các bước dưới đây đi hết vòng đời một đơn **OT-3 (viết theo mẫu)**, nhận tại xưởng, thanh toán **MOCK** (không mất tiền thật),
robot **không chạy thật** (kỹ thuật viên chỉ khai báo các bước trên màn hình). Mỗi bước có cột **"Phải thấy"** để bạn đánh dấu đạt / không đạt.

## 0. Chuẩn bị (một lần)

Mở 2 cửa sổ PowerShell.

**Cửa sổ 1 – Backend, dùng DB cục bộ `vhrs_test`** (không đụng Supabase thật; DB đã ở migration 0031 ngày 2026-11-26):

```powershell
cd D:\K9\AI-VHRS\BE
Get-Content .env.test | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v }
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Muốn thử trên dữ liệu thật (Supabase) thì bỏ dòng `Get-Content .env.test ...`; khi đó đơn tạo ra là dữ liệu thật, thử xong nên huỷ.
**Muốn bước 6 chạy robot THẬT thì bắt buộc dùng Supabase**: robot `46`, tài khoản kỹ thuật viên `staff@gmail.com` mà máy trạm
(`robot_agent/agent.json`, `console.json`) đang dùng chỉ có trên Supabase, không có trong `vhrs_test` (kiểm 2026-11-26).
Máy trạm gọi BE ở `http://127.0.0.1:8000`, nên BE phải chạy **trên chính máy nối robot**.
Kiểm tra: mở `http://localhost:8000/docs` thấy Swagger.

**Cửa sổ 2 – Frontend, trỏ vào backend cục bộ:**

```powershell
cd D:\K9\AI-VHRS\FE
$env:VITE_API_PROXY_TARGET = "http://localhost:8000"; npm run dev
```

Mở `http://localhost:5173`. Dùng **4 trình duyệt / cửa sổ ẩn danh riêng** (mỗi vai trò một phiên) để khỏi phải đăng xuất liên tục:

| Vai trò | Tài khoản demo | Trang chính |
|---|---|---|
| Khách | `customer@example.com` (hoặc tự đăng ký tài khoản mới ở bước 1) | `/` |
| Staff | `staff@netviet.vn` | `/staff` |
| Manager | `manager@netviet.vn` | `/staff` (bảng điều khiển Manager) |
| Kỹ thuật viên | `tech@netviet.vn` | `/tech` |
| Admin (tuỳ chọn) | `admin@netviet.vn` | `/admin` |

Mật khẩu: bạn (chủ dự án) đang giữ.

## 1. Khách: tài khoản

| # | Thao tác | Phải thấy |
|---|---|---|
| 1.1 | Trang chủ → Đăng ký bằng email mới | Đăng ký xong được đăng nhập, về trang chủ |
| 1.2 | Đăng xuất → đăng nhập lại; thử sai mật khẩu một lần | Sai mật khẩu báo lỗi, đúng thì vào được |
| 1.3 | `/account` → thêm số điện thoại, xin mã OTP | Chế độ MOCK: không có SMS thật, mã không hiện cho FE (bước này chỉ kiểm tra màn hình báo "đã gửi") |

## 2. Khách: tạo đơn (`/create-order`)

| # | Thao tác | Phải thấy |
|---|---|---|
| 2.1 | Chọn loại **Viết theo mẫu (OT-3)**, số lượng 1 | OT-2 bị khoá (không chọn được) |
| 2.2 | Chọn giấy → bút → mực | Chỉ hiện bút hợp với giấy, mực hợp với bút; có ảnh vật tư |
| 2.3 | Nhập nội dung tiếng Việt có dấu (vd "Chúc mừng năm mới, chúc cả nhà an khang"), chọn mẫu chữ, thử đổi cỡ chữ / căn lề | Ảnh xem trước cập nhật, có khung lề mờ; giá ước tính hiện **khoảng giá** |
| 2.4 | (Tuỳ chọn) Mở trợ lý AI, đồng ý chính sách dữ liệu chat, nhờ sửa nội dung | Trợ lý đề xuất, đơn chỉ đổi khi bấm "Áp dụng" |
| 2.5 | Gửi đơn, tick đồng ý điều khoản | Đơn sang **SUBMITTED**, có mã đơn |
| 2.6 | Thử gửi một đơn thiếu nội dung | Báo thiếu gì (`ORDER_INCOMPLETE`), không gửi được |

## 3. Staff: tiếp nhận, phác thảo, báo giá (`/staff`)

| # | Thao tác | Phải thấy |
|---|---|---|
| 3.1 | Hàng đợi → thấy đơn vừa gửi trong "pool" → **Nhận đơn** | Đơn thành của Staff này |
| 3.2 | **Chấp nhận** đơn | Đơn **ACCEPTED** |
| 3.3 | **Sinh phác thảo** | Có ảnh phác thảo từng trang, dấu nhận diện AI-VHRS, thời gian viết ước tính |
| 3.4 | (Tuỳ chọn) Sửa nét / dời một từ / dùng tẩy → lưu | Ra phiên bản mới; so sánh 2 phiên bản thấy đúng chỗ đổi |
| 3.5 | **Chốt** phác thảo → lập và **gửi báo giá** | Đơn sang **AWAITING_PRIVACY** (hoặc **QUOTED** nếu khách đã đồng ý chính sách) |

## 4. Khách: chính sách riêng tư, duyệt báo giá, đặt cọc

| # | Thao tác | Phải thấy |
|---|---|---|
| 4.1 | Mở đơn (`/orders/{id}/review`) → đọc chính sách → **Đồng ý** | Đơn **QUOTED**, thấy báo giá + ảnh phác thảo + nhãn cấp xem trước |
| 4.2 | Tải PDF báo giá | PDF mở được, số tiền khớp màn hình |
| 4.3 | **Duyệt báo giá** (giữ mức cọc tối thiểu) | Đơn **AWAITING_DEPOSIT** |
| 4.4 | Trang cọc → nhãn **MOCK** → thanh toán **Thành công** | Đơn **CONFIRMED**, có ETA; có thông báo trong chuông |

## 5. Manager: xếp lịch (`/staff/schedule`)

| # | Thao tác | Phải thấy |
|---|---|---|
| 5.1 | Hàng đợi xếp lịch → thấy đơn vừa cọc | Có thời lượng ước tính |
| 5.2 | Xem gợi ý → chọn robot + kỹ thuật viên + khung giờ → **Xếp lịch** | Job **SCHEDULED**; khung giờ ngoài giờ làm / trùng lịch bị từ chối |
| 5.3 | Ghi lại **số job** (Job ID) | Cần cho bước 6 |

Chạy robot thật ở bước 6: phải chọn **robot 46** và kỹ thuật viên **`staff@gmail.com`** (máy trạm đăng nhập bằng tài khoản này và chỉ điều khiển robot 46).
Robot phải ở trạng thái `AVAILABLE` / `BUSY`, không `MAINTENANCE`.

## 6. Kỹ thuật viên: chạy job trên robot FAIRINO FR3 thật

> **An toàn, không bỏ qua:** một người đứng **tay trên nút E-Stop vật lý** suốt lúc robot bật; vùng làm việc không có người;
> giấy A4 kẹp chặt đúng vị trí đã hiệu chuẩn. Nút DỪNG trên màn hình chỉ là dừng phần mềm, **không thay E-Stop**.
> Cảnh báo **đỏ** = bấm E-Stop ngay. Gripper hiện **không có cảm biến lực** (`unsensed_gripper: true`): không có gì tự phát hiện
> bút ép quá mạnh, người đứng cạnh là lớp an toàn duy nhất về lực. Lần chạy trước (2026-10-31) bút ép quá mạnh; độ ép đã giảm còn
> ~0,3 mm (`calibration.json`), **chưa được kiểm lại trên robot**.

Ba chỗ làm việc trong bước này:
- **[MT]** = PowerShell trên máy trạm nối robot, trong thư mục `D:\K9\AI-VHRS\robot_agent`.
- **[WEB]** = trình duyệt đăng nhập `staff@gmail.com`, trang `http://localhost:5173/tech/jobs/<JOB_ID>`.
- **[RB]** = tại robot (mắt nhìn, tay trên E-Stop).

### 6A. Chuẩn bị máy trạm (mỗi buổi một lần)

| # | Ở đâu | Thao tác | Phải thấy |
|---|---|---|---|
| A1 | [RB] | Bật nguồn robot và controller, mở khoá E-Stop, robot ở chế độ tự động; lắp bút, kẹp giấy A4 dọc đúng 3 góc đã đo | Màn hình robot không báo lỗi |
| A2 | [MT] | Kiểm máy trạm cùng mạng với robot: `ping 192.168.58.2` | Có phản hồi |
| A3 | [MT] | BE đang chạy bằng `.env` (Supabase) ở cổng 8000 (bước 0, **không** nạp `.env.test`); mở `http://127.0.0.1:8000/api/v1/health` | Trả `ok` |
| A4 | [MT] | Sửa `console.json`: `"job_id": <JOB_ID của bước 5.3>`, `"mode": "REAL"`; giữ `email` = `staff@gmail.com`, `backend_url` = `http://127.0.0.1:8000` | |
| A5 | [MT] | Mở cửa sổ PowerShell riêng, chạy agent và **để cửa sổ này mở suốt buổi**: `.\.simenv\python.exe -X utf8 scripts\start_agent.py` (nhập mật khẩu nếu được hỏi) | In `Backend link ON (session of staff@gmail.com on robot 46)`, modes có `real` |
| A6 | [MT] | Cửa sổ PowerShell thứ hai: `.\.simenv\python.exe -X utf8 scripts\robot_console.py identify` | Kết quả `DONE`: model `FR3`, controller `V3.8.25-QX`, góc khớp, vị trí TCP. **Lỗi kết nối → dừng**, đừng thử "cho qua" |
| A7 | [WEB] | Mở trang job | Khung "Điều khiển robot" hiện chip **Online** và **REAL** |

### 6B. Chuẩn bị job (robot chưa chuyển động)

| # | Ở đâu | Thao tác | Phải thấy |
|---|---|---|---|
| B1 | [WEB] | Khung "Gói job" → **Tải gói** | Chip **Đã xác minh**, mã hash SHA-256, dải lực bút (min / mục tiêu / max N), tốc độ tối đa, hình nét từng trang. Có "lệch vật tư" thì đọc kỹ trước khi đi tiếp |
| B2 | [WEB] | **Chuẩn bị** | Job **SCHEDULED → PREPARING** |
| B3 | [MT] | Gửi hiệu chuẩn (3 điểm giấy, giới hạn chuyển động, hộp an toàn từ `calibration.json`): `.\.simenv\python.exe -X utf8 scripts\robot_console.py calibrate` | Thành công; trên [WEB] mục Hiệu chuẩn thành **Đạt**. Nếu báo còn giá trị `<ĐO>` thì phải đo và điền trước |
| B4 | [WEB] | Khung "Điều khiển robot", bước 1 **Nạp job (LOAD)** | Số trang, số nét, thời gian ước tính; `validation` không có lỗi; ô "Mã xác nhận" hiện gợi ý dạng `AUTHORIZE-<job>-xxxxxxxx` |
| B5 | [MT] | Mở khoá chạy thật cho đúng job này, 30 phút: `.\.simenv\python.exe -X utf8 -m vhrs_agent.cli real-enable --config agent.json --job <JOB_ID> --minutes 30` → gõ `YES` | Báo đã bật REAL cho job, kèm giờ hết hạn. Hết hạn thì chạy lại lệnh này |
| B6 | [WEB] | Bước 2 **Kiểm tra trước (PREFLIGHT REAL)** | `ok`, số lần di chuyển. Robot **không** động. Lỗi `START_ORIENTATION_MISMATCH` → làm B6b |
| B6b | [RB]+[MT] | (Chỉ khi cần) Dùng tay đưa bút tới gần điểm bắt đầu, rồi: `.\.simenv\python.exe -X utf8 scripts\robot_console.py align-start --mode REAL` → `YES` (**robot di chuyển chậm**), rồi làm lại B6 | PREFLIGHT `ok` |
| B7 | [WEB] | Bước 3 **Ghi kết quả mô phỏng** | Mục Mô phỏng thành **Đạt**. BE tự dựng lại kế hoạch và có thể đổi thành **Không đạt** → đọc lỗi, dừng |

### 6C. Chạy thử nhấc bút (DRY_RUN): cánh tay CHUYỂN ĐỘNG THẬT, bút không chạm giấy

| # | Ở đâu | Thao tác | Phải thấy |
|---|---|---|---|
| C1 | [WEB] | Dán mã `AUTHORIZE-...` (lấy ở B4) vào ô "Mã xác nhận" | Nút chạy thử sáng lên |
| C2 | [RB] | Tay trên E-Stop, vùng robot trống | |
| C3 | [WEB] | Bước 4 **Chạy thử pen-up (REAL)** → xác nhận | Robot đi hết quỹ đạo, bút luôn cao hơn giấy (~20 mm), thanh tiến độ và hình 3D chạy theo; kết thúc `DRY_RUN_DONE`, số nét khớp B4 |
| C4 | [RB] | Kiểm bằng mắt: robot có đi ra ngoài tờ giấy, chạm bàn, va giá kẹp, hay đi lạ không? | Không. Có → E-Stop, **dừng buổi test**, ghi lại |

### 6D. Viết thật

| # | Ở đâu | Thao tác | Phải thấy |
|---|---|---|---|
| D1 | [RB] | Đặt **tờ giấy mới** đúng vị trí (nếu tờ ở C đã bị chạm) | |
| D2 | [MT] | (Chỉ khi job này đã từng viết dở trên tờ khác) `.\.simenv\python.exe -X utf8 scripts\robot_console.py reset-progress` → `YES` | Tiến độ về nét đầu |
| D3 | [WEB] | Bước 5 **Bắt đầu viết**; các dấu tick phía dưới phải đủ: đã xác minh gói, đã tải, hiệu chuẩn, mô phỏng, server cho phép | Job **PREPARING → WRITING**; đơn chuyển sang đang sản xuất |
| D4 | [WEB] | Nút lớn **Chạy (RUN)** (mã AUTHORIZE vẫn trong ô) → xác nhận | Robot hạ bút và viết. Màn hình: % tiến độ, nét `k / tổng`, trạng thái agent, lực (gripper không cảm biến thì `–`), toạ độ TCP |
| D5 | [RB] | Theo dõi **nét đầu tiên**: bút lún sâu, kẹt, xé giấy, hay không ra mực? | Bất thường → E-Stop (nguy hiểm) hoặc **Tạm dừng** (để chỉnh); ghi lại |
| D6 | [WEB] | (Tuỳ chọn) thử **Tạm dừng** → **Tiếp tục** một lần | Robot viết nốt nét đang dở, nhấc bút, dừng; Tiếp tục thì viết tiếp đúng nét sau |
| D7 | [WEB] | Chờ tới khi hết bận | Tiến độ 100 %, mục "Lần chạy cuối" không có lỗi |
| D8 | [WEB] | **Viết xong** → xác nhận | Job **WRITTEN**; tồn kho giấy / bút / mực bị trừ |

Cách khác cho 6B–6D (cùng các cổng an toàn, mọi bước làm robot chuyển động vẫn hỏi `YES`), chạy ở [MT]:
`powershell -ExecutionPolicy Bypass -File scripts\write_job.ps1 -DryRunFirst` (vẫn phải làm B1–B3 và B7 trước).
Theo dõi trong terminal: `.\.simenv\python.exe -X utf8 scripts\robot_console.py watch` (Ctrl+C để thoát, không ảnh hưởng robot).

**Khi có sự cố**
- Nguy hiểm hoặc robot không theo lệnh → **E-Stop vật lý** trước, đọc sau.
- Cảnh báo cam (robot đã tự dừng an toàn) → xử lý nguyên nhân theo câu chữ trên màn hình, rồi **Tiếp tục** hoặc **DỪNG**. Nét dở
  không tự chạy lại: muốn viết tiếp từ nét K thì mở "Nâng cao" → "Tiếp tục từ nét" = K rồi bấm RUN.
- Mất liên lạc agent ↔ BE khi đang viết → agent viết nốt nét, nhấc bút, tạm dừng, không tự chạy tiếp.
- Không viết tiếp được → khung "Sự cố" trên [WEB]: chọn loại (ROBOT / MATERIAL / ...), mô tả, trạng thái robot sau sự cố →
  job **FAILED**, đơn về hàng đợi xếp lại của Manager.
- **Giữ nguyên** thư mục `robot_agent\runs\job<JOB_ID>\` (log từng lệnh, cảnh báo) để gửi phân tích.

### 6E. Ảnh thành phẩm + QC

| # | Ở đâu | Thao tác | Phải thấy |
|---|---|---|---|
| E1 | [RB] | Tháo giấy, chụp 1 ảnh **toàn cảnh** và 1 ảnh **cận cảnh** (đặt thước cạnh tờ giấy nếu muốn đo mm) | |
| E2 | [WEB] | Khung ảnh: chọn loại **Toàn cảnh** → chọn file → **Tải lên**; lặp lại với **Cận cảnh** | Ảnh hiện trong danh sách (tối đa 10) |
| E3 | [WEB] | Với từng ảnh chọn QC **Đạt** (hoặc **Không đạt** + ghi chú ≥ 3 ký tự) → **Lưu QC** | |
| E4 | [WEB] | (Tuỳ chọn) **Đánh giá** ảnh so với phác thảo | Có điểm so khớp theo trang |
| E5 | [WEB] | **Gửi ảnh cho khách** → xác nhận | Job **PHOTO_UPLOADED**; khách thấy ảnh ở bước 7 |

### 6F. Báo lại sau buổi chạy
Kết quả `identify` (A6); bút có chạm đúng vị trí trên giấy không, lệch bao nhiêu mm (đo bằng thước); độ ép bút trông thế nào;
thời gian từ lúc bấm DỪNG tới khi robot đứng yên; thư mục `runs\job<JOB_ID>\` và ảnh bản viết.

## 7. Khách: nghiệm thu, thanh toán cuối, nhận hàng

| # | Thao tác | Phải thấy |
|---|---|---|
| 7.1 | Mở đơn → xem ảnh thành phẩm → **Nghiệm thu** | Đơn **AWAITING_FINAL_PAYMENT** |
| 7.2 | Chọn **Nhận tại xưởng**, khung giờ trong giờ làm, SĐT | Lưu được; khung ngoài giờ làm bị từ chối |
| 7.3 | Thanh toán phần còn lại (MOCK, Thành công) | Đơn **READY_TO_DELIVER** |
| 7.4 | (Staff) Mục giao hàng của đơn → nhập mã đơn + SĐT khách → **Xác nhận bàn giao** | Đơn **COMPLETED**; SĐT sai bị từ chối |

Biến thể giao hàng (tuỳ chọn): ở 7.2 chọn **Giao hàng**, nhập địa chỉ (tỉnh → phường/xã), chọn dịch vụ GHN; Staff tạo vận đơn.
Ở chế độ MOCK, trạng thái vận chuyển do nút mô phỏng của Staff đẩy đi.

## 8. Khách: đánh giá

| # | Thao tác | Phải thấy |
|---|---|---|
| 8.1 | Đơn COMPLETED → đánh giá 5 sao + bình luận + 1–2 ảnh | Lưu được; đánh giá lần 2 bị chặn, chỉ sửa được |
| 8.2 | (Manager) `/staff/reviews` → ẩn đánh giá | Đánh giá biến mất khỏi trang công khai |

## 9. Nhánh phụ nên thử thêm (mỗi nhánh một đơn mới)

| Nhánh | Cách thử | Phải thấy |
|---|---|---|
| Đơn OT-1 (sao chép) | Ở bước 2 chọn Sao chép, tải ảnh chữ viết tay | Có cảnh báo chất lượng nếu ảnh xấu; Staff sinh phác thảo phục dựng |
| Xin thêm thông tin | Bước 3.2 bấm **Yêu cầu bổ sung** | Đơn **NEED_INFO**; khách sửa và gửi lại |
| Từ chối đơn | Bước 3.2 bấm **Từ chối** + lý do | Đơn **REJECTED**, khách được báo |
| Từ chối chính sách | Bước 4.1 bấm **Không đồng ý** | Hỏi xác nhận, đơn bị huỷ |
| Huỷ sau cọc | Sau 4.4, khách huỷ đơn | Xem trước tiền hoàn đúng luật; `/staff/refunds` có yêu cầu hoàn |
| Sự cố robot | Ở 6.3 báo sự cố thay vì Viết xong | Job **FAILED**, đơn về hàng đợi xếp lại của Manager |
| Phân quyền | Khách gõ thẳng `/staff`, `/tech`, `/admin` | Bị đẩy về trang của mình |

## 10. Ghi lại kết quả

Với mỗi bước không đạt, ghi: số bước, mã đơn, vai trò, ảnh chụp màn hình và lỗi trong DevTools (tab Network: request đỏ, mã lỗi trong body).
Log backend nằm ở cửa sổ PowerShell 1.
