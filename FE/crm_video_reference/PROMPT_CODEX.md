# Prompt cho Codex

Hãy triển khai giao diện CRM dựa trên các ảnh tham chiếu đính kèm:

- `01_dashboard_overview.png`
- `02_dashboard_analytics.png`
- `03_deals_pipeline.png`

## Cách làm

1. Trước khi sửa, xem cấu trúc repository, framework, quy ước hiện có, các trang/layout/component và thư viện đang dùng. Tìm entry point phù hợp để tích hợp giao diện vào dự án hiện tại.
2. Dựng trang CRM desktop theo ảnh: nền trắng ngà/xám rất nhạt; thanh điều hướng ngang bo góc; chữ tối giản; thẻ nền trắng, đường viền/bóng nhẹ; điểm nhấn xanh lime; biểu đồ đen/xám phối xanh lime; một thẻ KPI nền đen. Bố cục Overview có lời chào, bộ lọc thời gian, nút Export/New deal, hàng KPI, biểu đồ hiệu suất lớn và bảng/phần thống kê. Trang Deals có KPI tổng quan và các cột pipeline dạng kanban.
3. Dùng dữ liệu mẫu hợp lý nếu dự án chưa có API. Không tự tạo backend/API hay thay đổi nghiệp vụ hiện có. Giữ đúng công nghệ và quy ước repository; tái sử dụng component, icon và chart library đã có nếu phù hợp.
4. Làm các thao tác nhìn thấy được có phản hồi phù hợp: chuyển Overview/Deals, lọc thời gian, Export, New deal và thao tác thẻ deal nếu phạm vi dự án cho phép. Nếu một thao tác chưa có backend, dùng trạng thái giao diện mẫu rõ ràng thay vì giả vờ đã lưu dữ liệu.
5. Bố cục cần co giãn ở tablet/mobile, nhưng ưu tiên độ giống ảnh trên màn hình desktop. Không sao chép logo/brand trong ảnh, watermark TikTok, hay chữ code ở ngoài vùng giao diện. Watermark bên trái là lớp phủ của video, không thuộc UI mẫu.
6. Giữ thay đổi tập trung vào giao diện CRM. Sau khi làm, tóm tắt file đã sửa, cách mở trang và phần nào đang dùng dữ liệu mẫu. Đừng chỉ trả về hướng dẫn hoặc mockup tĩnh nếu repository có thể chạy giao diện thật.

## Tiêu chí hoàn thành

- Trang render được trong ứng dụng hiện tại, không làm hỏng các trang/luồng cũ.
- Thứ bậc bố cục, khoảng trắng, màu sắc, thẻ KPI và cách chia biểu đồ bám sát ảnh tham chiếu.
- Các nút chính có phản hồi nhìn thấy được; dữ liệu mẫu thống nhất giữa KPI, biểu đồ và pipeline.
