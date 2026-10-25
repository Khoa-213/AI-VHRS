# Technical Staff: tích hợp web với API BE

Cập nhật: 23/10/2026. Phạm vi: FE web; không sửa BE, không điều khiển robot vật lý. Giữ Shell, dashboard, card và panel hiện có; bổ sung form theo hợp đồng API.

## Đã nối

- [x] Dashboard, danh sách job và badge QC lấy API theo token Technical Staff.
- [x] Chi tiết tại `/tech/jobs/:jobId`; các alias `/tech/preview/:jobId`, `/tech/qc/:jobId` cũng dùng màn API này.
- [x] Tải binary từ signed URL không bearer/cookies; tính SHA-256 và so với package_hash.
- [x] Xem từng trang quỹ đạo từ file đã kiểm hash và lưu file đã xác minh.
- [x] Chuẩn bị; checklist; zero lực; điểm dò; JSON hiệu chuẩn nâng cao.
- [x] Ghi kết quả mô phỏng do kỹ thuật viên/máy trạm cung cấp, nhãn nhập thủ công, không suy kết quả từ animation.
- [x] Start chỉ mở khi hash đang giữ khớp hash job, đã tải gói, hiệu chuẩn hợp lệ, mô phỏng đạt và BE trả can_start.
- [x] Progress, Pause/Resume, sự kiện an toàn, force summary theo trạng thái BE.
- [x] Finish có xác nhận; không tự kết thúc job bằng đồng hồ.
- [x] Báo sự cố và tùy chọn robot MAINTENANCE/BROKEN.
- [x] Nhật ký sự kiện phân trang và danh sách sự cố.
- [x] Upload ảnh JPEG/PNG cạnh dài >=1280px; retry đăng ký cùng khóa nếu PUT đã xong.
- [x] Xem/xóa ảnh, QC PASS/FAIL; FAIL cần ghi chú.
- [x] Nộp >=2 ảnh có OVERALL và CLOSE_UP, tất cả PASS; sau nộp chỉ đọc.
- [x] QC fail về REWRITE_REQUIRED qua BE, không dùng lượt viết lại miễn phí của khách.
- [x] Khóa gửi lặp; refetch sau cả thành công và lỗi; xử lý 409/422; tôn trọng Retry-After cho API technician.
- [x] Việt/Anh/Nhật; thời gian job hiển thị Asia/Ho_Chi_Minh.
- [x] Sửa riêng toolbar Technical Staff trên mobile: bỏ chiều cao sidebar desktop gây khoảng trống gần một màn hình; không đổi layout desktop hoặc các role khác.

RobotPreview.tsx, QualityCheck.tsx, sim.ts và local store cũ còn dưới dạng tham chiếu; không được App.tsx dùng cho route sản xuất. Không đưa job BE trở lại hàm thay đổi trạng thái local.

## Thứ tự API

Tiền tố chung: `/api/v1`. Job ID khác order ID và mã đơn.

1. GET `/technician/jobs`, GET `/technician/jobs/{id}`.
2. GET `.../{id}/package` -> tải bytes từ signed URL -> SHA-256. Sai hash thì chặn tiếp tục.
3. POST `.../{id}/prepare`: SCHEDULED -> PREPARING.
4. POST `.../{id}/calibration`: đủ frame_mounted, paper_clamped, pen_installed, force_zeroed; force_zero_offset; 3..400 điểm x/y/z, ba điểm đầu không thẳng hàng; frame_transform, height_map, force_curve tùy chọn.
5. POST `.../{id}/simulation`: chọn rõ đạt/không đạt; đạt không được còn errors. Report gắn source=web_manual. Hiệu chuẩn lại làm mất simulation cũ.
6. POST `.../{id}/start`: PREPARING -> WRITING; gate từ BE và hash đang xác minh tại trình duyệt.
7. POST `.../{id}/events`: PROGRESS/PAUSE/RESUME/ESTOP/OVER_FORCE/STROKE_LOST/SENSOR_LOST/FORCE_SUMMARY. Chỉ ghi sự kiện quan sát; không phải nút điều khiển/dừng phần cứng. GET `.../{id}/events` để xem lịch sử.
8. POST `.../{id}/finish`: WRITING -> WRITTEN; BE trừ vật tư. Hoặc POST `.../{id}/incidents`: PREPARING/WRITING/PAUSED -> FAILED, Manager xếp lại.
9. POST `.../{id}/photos/upload-url` -> PUT binary tới storage -> POST `.../{id}/photos` với photo_key, kind.
10. GET `.../{id}/photos`; PATCH/DELETE `.../{id}/photos/{photoId}` trước nộp. Tối đa 10 ảnh. QC FAIL cần ghi chú ít nhất ba ký tự.
11. POST `.../{id}/photos/submit`: PHOTO_UPLOADED, đơn AWAITING_ACCEPTANCE. Hoặc POST `.../{id}/qc-fail {note}`: REWRITE_REQUIRED. Nghiệm thu Customer là flow riêng.

## Lưu ý vận hành

- Refresh trang sẽ mất hash giữ trong bộ nhớ; cần tải và kiểm lại trước chuẩn bị/hiệu chuẩn/mô phỏng/Start. Không lưu dấu xác minh vào localStorage.
- URL hết hạn: tải gói lại để lấy URL mới. Ảnh được refresh/poll để lấy URL ký mới.
- Mọi mutation đọc lại job sau khi xử lý, kể cả lỗi mạng hoặc 409. Không tự ép trạng thái UI thành công.
- Giữ photo_key sau PUT thành công để retry đăng ký; không upload thêm ảnh chỉ vì response đăng ký bị mất.
- PHOTO_UPLOADED chỉ đọc, chờ khách nghiệm thu. Tech không tự chuyển DONE.
- Không giả mức mực, trạng thái máy tức thời hay kết quả sensor.

## Kiểm tra tự động

Trong FE:

```powershell
npm.cmd run test:technician
npm.cmd run i18n:check
npm.cmd run build
npm.cmd run test:technician:browser
```

Browser test dùng Edge thật nhưng chặn toàn bộ API/storage để trả fixture cục bộ. Không tài khoản thật, Supabase, tiền thật hoặc robot. Nếu Edge không ở đường dẫn mặc định, đặt TECH_BROWSER_PATH tới executable Chromium/Edge. Cần quyền chạy trình duyệt headless.

Đã đạt:

- 13 service/rule tests: filter/pagination, hash lệch/URL hết hạn, gate Start, event đúng trạng thái, QC thiếu ảnh/FAIL, upload không bearer, retry cùng khóa, HTTP/payload, lỗi quyền, Retry-After, điểm dò/JSON.
- Browser: xem job không mutation; hash sai bị chặn; tải hợp lệ; chuẩn bị; hiệu chuẩn; mô phỏng; hiệu chuẩn lại xóa kết quả cũ; Start; 409 refetch sang PAUSED; Pause/Resume; Finish; lỗi đăng ký ảnh và retry; QC PASS; Submit; QC fail; incident.
- Browser: render Việt/Nhật, không tràn ngang ở viewport 390px.

Các kết quả này không thay thế UAT với backend/storage triển khai hoặc robot thật.

## UAT backend thật còn cần

- [ ] Customer tạo/gửi đơn; Staff nhận, chốt sketch, báo giá; Customer duyệt và cọc trong môi trường test phù hợp.
- [ ] Manager xếp lịch và giao đúng Technical Staff; kiểm tra jobId trên dashboard.
- [ ] Tải file thật, kiểm hash, từng trang quỹ đạo, CORS và URL TTL.
- [ ] Nhập số đo hiệu chuẩn thực hoặc dữ liệu test được phê duyệt; không coi số mẫu là phép đo thật.
- [ ] Start thiếu gate/sai role/job người khác; re-calibrate bắt mô phỏng lại; xung đột hai client.
- [ ] Progress/events/Finish và đối chiếu kho, production_status.
- [ ] Upload ảnh thật: đúng loại, sai cỡ, thiếu loại, QC FAIL, retry khi mất mạng.
- [ ] Nộp ảnh, phía khách thấy trạng thái chờ nghiệm thu.
- [ ] QC fail/incident về queue Manager, không dùng lượt viết lại miễn phí của khách.
- [ ] Đồng bộ với Flutter khi dùng đồng thời. Flutter chưa đổi code trong đợt này.

Chưa tự ghi dữ liệu thật để UAT; cần tài khoản và bộ dữ liệu kiểm thử phù hợp. Không chạy suite BE có cleanup lên Supabase production.
