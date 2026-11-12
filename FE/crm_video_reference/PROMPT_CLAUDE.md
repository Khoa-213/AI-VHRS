# Prompt cho Claude Code

Hãy đọc repository hiện tại và triển khai một giao diện CRM lấy cảm hứng sát từ ba ảnh tham chiếu được đính kèm:

- `01_dashboard_overview.png`
- `02_dashboard_analytics.png`
- `03_deals_pipeline.png`

Bắt đầu bằng việc kiểm tra cấu trúc, framework, cách chạy ứng dụng, hệ thống routing, component dùng chung và quy tắc styling. Sau đó chọn đúng nơi để thêm giao diện vào dự án đang có; không dựng một dự án mới nếu repository hiện tại đã có ứng dụng.

## Hướng thiết kế

Tái tạo một CRM desktop sạch và hiện đại: nền trắng ngà/xám rất nhạt, thanh điều hướng ngang bo tròn, typography gọn, thẻ trắng có viền/bóng rất nhẹ, accent xanh lime, biểu đồ đen/xám phối xanh lime và một thẻ KPI nền đen. Overview gồm lời chào, bộ chọn khoảng thời gian, Export/New deal, hàng KPI có sparkline, biểu đồ doanh thu lớn, thẻ thống kê tối và phần analytics phía dưới. Deals gồm các chỉ số pipeline và bảng kanban chia cột theo giai đoạn, với các deal card có giá trị, công ty và trạng thái.

## Yêu cầu triển khai

- Ưu tiên dùng stack, cấu trúc, routing, CSS strategy, icon/chart package đang có; thêm dependency chỉ khi thật cần thiết.
- Dùng dữ liệu demo nhất quán nếu chưa có API. Không tự thay đổi backend, schema hoặc nghiệp vụ. Với hành động chưa được kết nối backend, hiển thị phản hồi UI trung thực (ví dụ modal/form demo hoặc thông báo).
- Tạo các component có thể tái sử dụng cho thanh điều hướng, KPI card, chart panel và deal card; tránh nhồi toàn bộ vào một component nếu cấu trúc dự án cho phép tách hợp lý.
- Các mục Overview/Deals, bộ lọc thời gian, Export, New deal và thao tác deal cần phản hồi khi bấm. Không để các nút quan trọng chỉ là trang trí.
- Ưu tiên giống ảnh trên desktop; vẫn xử lý tốt tablet/mobile bằng cách cuộn ngang cho kanban hoặc xếp lại thẻ khi cần.
- Không sao chép thương hiệu/logo, watermark TikTok hay phần code editor trong video. Watermark trên ảnh chỉ là lớp phủ của nguồn video.
- Giữ nguyên các luồng cũ và giới hạn chỉnh sửa ở phần cần thiết.

Sau khi hoàn tất, hãy báo file đã thay đổi, cách chạy/mở giao diện, các tương tác đã làm và những phần vẫn là dữ liệu demo. Hãy thực sự sửa code trong repository, không chỉ mô tả cách làm.
