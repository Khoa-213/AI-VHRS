# THÔNG SỐ GIAO DIỆN THAM KHẢO MACHINAFUSION → WEBSITE FR3

> **Nhiệm vụ:** Chỉ mượn giao diện, cấu trúc thị giác và chuyển động của video mẫu MachinaFusion. **Tất cả nội dung cuối cùng phải lấy từ dự án FR3 đang có trong workspace**: logo, tiêu đề, đoạn giới thiệu, sản phẩm/dịch vụ, số liệu, nút CTA, đường dẫn và chức năng. Nếu chưa xác định được nội dung FR3 tương ứng, hỏi người dùng; tuyệt đối không bịa thông tin hoặc bê chữ/số liệu của MachinaFusion sang.
>
> **Video và ảnh mẫu KHÔNG phải ảnh website để đưa thẳng làm background.** Phải dựng lại các lớp giao diện bằng component thật.

## 0. Kiểm tra trước khi code

- Trước tiên, mở project đang có. Xác định framework, file trang chủ, component, các tuyến trang, style hiện có và nguồn nội dung FR3.
- Các ảnh mẫu trong `reference/machinafusion/`. Xem `00_tong_hop_manhinh.png` rồi lần lượt 01 đến 06. Mỗi ảnh là ảnh chụp từ VIDEO, không phải asset đồ họa riêng có thể dùng làm hình sản phẩm.
- **Kiểm tra khả năng đọc hình:** mô tả nhanh bố cục ảnh 01 và ảnh 05. Nếu không thể xem nội dung ảnh, nói rõ “không đọc được ảnh” và sử dụng văn bản mô tả ở dưới, đồng thời xin người dùng dán screenshot riêng vào chat. Không tuyên bố đã xem khi chưa xem được.
- Giữ nguyên các phần FR3 không liên quan (backend, API, cơ sở dữ liệu, đăng nhập, tuyến trang). Làm từng section; desktop trước, responsive sau.
- Tạo nhánh Git riêng hoặc checkpoint để có thể khôi phục giao diện cũ.

## 1. Hệ thiết kế xuyên suốt

**Tổng quan:** minimal futuristic / editorial-tech / gần như đơn sắc. Nền tổng thể xám lạnh rất nhạt; phần trang web trắng nằm trong khung lớn có góc bo nhẹ. Nhiều khoảng trắng, chữ sans-serif không chân màu đen, nhãn phụ màu xám; ở vài chỗ chữ chuyển sang xám rất nhạt. Nội dung căn theo lưới rõ ràng. Viền đen/xám mảnh và các pill bo tròn hoàn toàn. Hiệu ứng phải có mục đích thị giác (reveal, parallax nhẹ, layer depth, scroll). Không tự ý thêm neon, gradient đậm, glassmorphism hay card dashboard thông thường.

**Navbar chung:** Góc trên trái có logo nhỏ; phía trên giữa là nhóm các nút điều hướng dạng viên thuốc nhỏ, tab đang chọn là pill đen chữ trắng; góc trên phải có pill CTA màu xám sáng và dấu tròn đậm bên trái. Trên section nền đen, navbar cần đủ tương phản. Không tự bịa tên menu: lấy tên và route thật của FR3.

**Ràng buộc ảnh:** Ảnh chụp chỉ là hình mẫu cách sắp đặt; để giống sát cần asset riêng: hình hero 2 chủ thể tách nền, hình công nghệ/sản phẩm lớn section đen, tối thiểu 5 ảnh gallery chất lượng tốt. Nếu project không có, liệt kê thiếu và chờ người dùng hoặc dùng placeholder có nhãn rõ; đừng dùng tấm screenshot nguyên trang làm giao diện.

## 2. Ảnh 01 — Hero: `01_hero_ban_tay_nguoi_robot.png`

- Khung lớn nền trắng, ít thành phần; navbar ở mép trên.
- Điểm nhìn chính: hình bàn tay người vươn từ mép trái vào gần tâm và bàn tay robot vươn từ mép phải vào gần tâm; bố cục bất đối xứng nhưng tạo một khoảng gặp gỡ ở giữa.
- Một headline chữ sans-serif lớn, đen, nằm chính giữa chiều ngang, bị hai chủ thể hình chồng lên một phần. Dòng thứ hai sử dụng một đoạn xám cực nhạt tạo tương phản với đoạn chữ đen.
- Hiệu ứng hào quang xanh/tím rất nhạt gần vùng giao hai bàn tay (tinh tế, không chói).
- Góc dưới trái: nhãn rất nhỏ + đoạn giới thiệu ngắn. Góc dưới phải: vài pill viền mảnh. Khoảng trống giữa và xung quanh hình rất quan trọng.
- Gợi ý motion bám mẫu: các chủ thể di chuyển từ 2 phía khi reveal, chữ vào sau/đồng thời; không biến toàn màn hình thành ảnh tĩnh.
- **FR3:** Thay headline/đoạn giới thiệu/chip bằng nội dung đã xác thực trong code FR3. Giữ ngôn ngữ nội dung hiện tại. Nếu FR3 không có chủ đề cánh tay robot, cần ảnh có bố cục tương đương nhưng liên quan đến FR3, không bê hình từ MachinaFusion để ngụy trang là sản phẩm FR3.

## 3. Ảnh 02 — Dark feature: `02_robot_nen_den.png`

- Panel đen/than rất đậm chiếm gần hết khung trắng, góc bo rõ, viền/trắng mảnh quanh panel.
- Hình cánh tay robot công nghiệp trắng rất lớn, cắt crop qua đáy và bên trái, khối hình tạo chiều sâu; gần chân panel có đường xanh cực mỏng trong ảnh mẫu.
- Đoạn text phụ đặt thấp ở mép phải, khá nhỏ; không có lưới card, sidebar hay tiêu đề quá lớn.
- Chuyển cảnh sáng → tối rõ rệt; hình có thể chuyển động/parallax trong giới hạn container. Kiểm tra hình không tràn hoặc bị che sai.
- **FR3:** Chọn tính năng hoặc sản phẩm thật của FR3 làm trọng tâm; dùng ảnh riêng thích hợp.

## 4. Ảnh 03 — Statistics: `03_thong_ke.png`

- Trở về nền trắng. Có ba hàng dữ liệu lớn và cách nhau bằng đường kẻ ngang rất mảnh.
- Mép trái mỗi hàng là con số rất to, bên dưới có nhãn mô tả cỡ nhỏ; giữa và phải có thanh capsule kéo dài ngang với gradient trắng/xám pastel rất nhạt và vòng tròn sáng lớn.
- Cỡ chữ lớn nhưng không quá đậm; bố cục sạch, có nhiều khoảng thở.
- Có thể animate vòng tròn / chiều rộng bar trong viewport, nhưng không ngầm biến hình trang trí thành input không hoạt động.
- **FR3:** Không dùng các số `97%`, `12K`, `30+` trong video nếu không có dữ liệu FR3 tương ứng; truy xuất số liệu thật hoặc chuyển sang thông điệp có nguồn trong project, báo người dùng phần còn thiếu.

## 5. Ảnh 04 → 05 — Gallery chuyển động: `04_gallery_xep_chong.png`, `05_gallery_the_3d.png`

- Đây là **hai trạng thái của cùng một gallery** trong video, KHÔNG phải hai gallery tách biệt.
- Tiêu đề lớn nằm gần phần trên, phong cách “nửa chữ đen, nửa chữ xám nhạt”; có nhãn nhỏ ở trên.
- Trạng thái A: giữa trang là nhiều tấm ảnh nằm chồng lên nhau thành các lát nghiêng/tầng xiên, trông như những mặt phẳng đang xoay trong phối cảnh 3D.
- Trạng thái B: khi scroll/animation tiến triển, xấp xỉ 5 thẻ ảnh tối màu đứng thành dãy trải theo chiều ngang, mỗi thẻ có ảnh công nghệ riêng, góc nghiêng và độ cao/tỉ lệ tương đối khác nhau, tạo cảm giác nổi 3D.
- Dưới gallery có hàng logo đối tác rất nhạt trong mẫu; **FR3 không được bịa logo đối tác hoặc quan hệ hợp tác**. Chỉ hiển thị khi project có dữ liệu thật.
- Cần triển khai bằng các thẻ DOM riêng và `transform: translate3d/rotate/scale`, với scroll progress thật (ví dụ GSAP ScrollTrigger nếu stack phù hợp); không thay bằng grid 5 card tĩnh hay fade-in đơn giản.
- Trên mobile cần bố cục thay thế hợp lý như scroll ngang/carousel, không gây tràn viewport. Có reduced-motion fallback.

## 6. Ảnh 06 — Typography/editorial: `06_tieu_de_chu_chay.png`

- Nền trắng rộng, một dòng chữ **cực lớn** ở vùng trên và kéo dài vượt chiều ngang viewport (trong mẫu chữ đen chuyển sang phần xám rất nhạt).
- Tại góc dưới trái có đoạn mô tả tương đối nhỏ, nhiều khoảng trống bên phải; phía dưới có nhóm chip nhỏ; một dòng liên hệ nhỏ phía dưới bên phải.
- Video cho thấy cảm giác dòng chữ chạy/di chuyển ngang theo thao tác scroll, không phải chỉ là một tiêu đề center.
- Dùng nội dung, CTA và thông tin liên hệ thật của FR3; không sao chép chữ/email của website mẫu. Chú ý `overflow-x` để không tạo thanh cuộn ngang ngoài ý muốn.

## 7. Kiểm tra độ giống theo vòng lặp

- Chạy trang chủ FR3 thật ở cùng viewport với ảnh mẫu (nếu không xác định được kích thước nguồn, chọn kích thước desktop cố định 1440×900 để kiểm tra nhất quán).
- So sánh theo thứ tự: (1) cấu trúc khối và tỷ lệ chiếm màn hình, (2) ảnh và crop, (3) vị trí/kích thước chữ, (4) khoảng trắng/bo góc/màu, (5) hướng animation qua các trạng thái.
- Sau mỗi lần sửa, chụp screenshot mới; nhận ít nhất 3–5 điểm lệch lớn nhất và sửa, tránh viết lại cả project mỗi lần.
- Nếu không có công cụ chụp browser tự động, yêu cầu người dùng gửi ảnh screenshot. Không bịa đánh giá “đã giống 95%” nếu không có hình đối chiếu.
- Chỉ nghiệm thu section tiếp theo sau khi người dùng đồng ý section hiện tại.

## 8. Prompt ngắn để bắt đầu

> Đọc `HUONG_DAN_THIET_KE_MAU_CHO_CLAUDE_FR3.md` và project FR3 hiện tại. Các ảnh mẫu nằm trong `reference/machinafusion/`. Trước khi code, hãy xác nhận bạn thật sự xem được `01_hero_ban_tay_nguoi_robot.png` (mô tả bố cục hai bàn tay và vị trí tiêu đề); nếu không xem được thì nói rõ và dựa trên mô tả ở tài liệu, yêu cầu tôi dán ảnh trực tiếp. Đọc nội dung FR3 đang có để ánh xạ sang từng section. Tạm thời chỉ dựng lại NAVBAR + HERO giống bố cục mẫu, nhưng tất cả chữ, logo, CTA, route và dữ liệu đều phải là FR3. Không tạo project mới, không đổi framework, không xóa backend. Sau đó chạy build và chỉ ra điểm chưa giống hoặc tài nguyên thiếu.
