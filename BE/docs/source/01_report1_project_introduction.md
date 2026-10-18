# Report 1 – Project Introduction (AI-VHRS)

> Chép lại từ PDF `REPORT (2).pdf` (Capstone Report 1, TP.HCM 09/2026, tạo 22/09/2026). Sơ đồ "5.2 Luồng nghiệp vụ tổng quát" là ảnh (ghi "VẼ"), không có ở đây.
> Lưu ý: Report 1 dùng mã **FE-01..FE-15** cho "Feature" (không phải Front-End); khác với **FR-xx** của Report 3.

## 1. Overview

**1.1 Thông tin dự án**
- Tên: Development of an AI-Assisted Vietnamese Handwriting Reproduction System Using a Robotic Arm (AI-VHRS)
- Mã đề tài: **FA26SE097** · Nhóm: **GFA26SE13** · Loại: Web Application + AI Service + Robotics Integration

**1.2 Nhóm**

| Họ tên | Vai trò |
|---|---|
| Lâm Hữu Khánh Phương | Lecturer/Supervisor |
| Hoàng Anh Khoa | Leader / BE |
| Nguyễn Đình Duy | BE |
| Hoàng Nguyễn Trọng Nhã | FE |
| Hoàng Bảo Ân | FE |
| Lê Đắc Trần Quang | FE (Flutter Desktop theo Report 2) |

(Email và số điện thoại có trong PDF gốc, không chép vào repo.)

## 2. Product Background

Chữ viết tay trên giấy thật có giá trị tình cảm và thẩm mỹ mà bản in không thay thế được. Ba nhu cầu chưa có dịch vụ nào đáp ứng trọn vẹn:

| STT | Nhu cầu | Mô tả |
|---|---|---|
| N1 | Lưu trữ, phục hồi, sao chép tài liệu/thư tay cũ | Thư tay của ông bà, cha mẹ, tài liệu viết tay đã cũ, phai mực, rách mép cần chép lại thành bản mới trên giấy thật, giữ nguyên nét chữ gốc ("copy lại cái cũ"). |
| N2 | Tạo nội dung mới theo nét chữ đã học | Viết nội dung mới (lời chúc, bức thư) bằng nét chữ của một người cụ thể (ví dụ người thân đã mất) học từ các mẫu còn lưu. **Hướng R&D: làm được đến đâu đưa vào sản phẩm đến đó.** |
| N3 | Chữ trang trí cho người viết chữ không đẹp | Thiệp, poster, câu đối, tranh chữ viết bằng bút thật với kiểu chữ typography theo mẫu có sẵn. |

Hiện giải quyết thủ công (thuê người viết): tốn thời gian, đắt, khó nhân bản đồng nhất, không giữ nét chữ của một người cụ thể. Công cụ số (font viết tay, AI sinh chữ) chỉ ra ảnh/PDF.
Pen-plotter như AxiDraw viết được trên giấy nhưng người dùng phải tự vector hóa, không phục dựng nét từ ảnh, xử lý kém dấu tiếng Việt (ă, â, ê, ô, ơ, ư và 5 dấu thanh).
AI-VHRS: dịch vụ trọn gói — khách đặt hàng trên website, xưởng dùng AI phục dựng/sinh nét chữ, cánh tay robot công nghiệp viết bằng bút thật lên giấy thật, gửi ảnh sản phẩm để khách nghiệm thu, rồi giao hàng.

## 3. Existing Systems
- **AxiDraw** (Evil Mad Scientist; phân phối ở VN qua SGC Workshop): pen-plotter nhận SVG/DXF; muốn viết chữ tay tiếng Việt phải tự tạo font hoặc vector hóa thủ công; không tự phục dựng quỹ đạo từ ảnh.
- **Realistic Handwriting (HandtextAI)**: AI text-to-handwriting, >80 kiểu, xuất ảnh/PDF; không viết ra giấy thật.
- **Scriptalizer** (Quantum Enterprises): web tạo font single-line cá nhân hóa dùng với plotter; quy trình thủ công, không tích hợp quản lý yêu cầu/robot end-to-end.

## 4. Business Opportunity

**Mô hình**: AI-VHRS là hệ thống vận hành của một **xưởng dịch vụ "Xưởng Nét Việt"** sở hữu nhiều cánh tay robot; khách chỉ đặt hàng trên website, xưởng lo xử lý, sản xuất, giao hàng. Nhóm khách: cá nhân (chép thư tay, thiệp cưới, tranh chữ, câu đối); doanh nghiệp (thiệp tri ân số lượng lớn, thư cảm ơn, poster, bảng tên sự kiện); bảo tàng/gia đình/dòng họ (phục hồi, nhân bản tài liệu).

**Doanh thu**: phí dịch vụ theo đơn (vật tư + công viết theo số ký tự và độ phức tạp + phí setup); **khách đặt cọc trước, phần còn lại và phí giao hàng thanh toán khi nghiệm thu**. Mở rộng công suất bằng cách thêm robot; hệ thống quản lý danh sách robot và lập lịch cho nhiều robot.

**Vì sao Fairino FR3** (thông số theo hãng, nhóm xác minh khi thử nghiệm): 6 DOF (điều khiển góc nghiêng bút); độ lặp lại ±0,02 mm; tầm với ≈ 622 mm (phủ khổ A4 + khung kẹp giấy); tải trọng 3 kg (giá kẹp bút + loadcell + bút); cobot có phát hiện va chạm (kỹ thuật viên làm việc cạnh robot); SDK Python/C++ qua TCP/IP. So với plotter: kiểm soát lực tì và góc bút, viết trên bề mặt không hoàn toàn phẳng, nhân rộng thành nhiều trạm.

## 5. Software Product Vision

Hệ thống vận hành xưởng viết tay bằng robot gồm: website đặt hàng và quản trị, module tính giá, module AI phục dựng nét chữ tiếng Việt và sinh lộ trình cho FR3, ứng dụng Flutter điều khiển robot tại xưởng kèm thiết bị IoT kiểm soát lực bút.
Luồng: **đặt hàng → duyệt phác thảo và báo giá → đặt cọc → robot viết → nghiệm thu qua ảnh sản phẩm thật → giao hàng.**

### 5.1 Actors

| Actor | Kênh | Vai trò chính |
|---|---|---|
| Customer | Web | Khách cá nhân/doanh nghiệp: tạo đơn (3 loại), tải ảnh/nhập nội dung, chọn giấy → bút → mực, số lượng, xem giá ước tính, gửi đơn; duyệt phác thảo và báo giá; đặt cọc theo % tối thiểu; theo dõi 2 trạng thái; nghiệm thu qua ảnh thật; chọn giao hàng hoặc nhận tại xưởng, thanh toán phần còn lại + phí ship; xác nhận đã nhận; hủy đơn theo chính sách. |
| Staff | Web | Tiếp nhận/từ chối đơn (tài liệu quá cũ, hư hỏng, thiếu thông tin), yêu cầu bổ sung; phác thảo (chạy AI và chỉnh sửa) và đề xuất cách làm; lập báo giá bảng/file; trao đổi với khách; xác nhận thanh toán; tạo vận đơn/giao hàng; cập nhật trạng thái đơn và ETA. |
| Technical Staff | Flutter Desktop App (có thể có vai trò web) | Xem job được giao, tải file job về máy trạm, chuẩn bị robot (lắp khung, kẹp giấy, lắp bút, hiệu chuẩn), mô phỏng, chạy viết, giám sát lực và E-Stop, báo sự cố, chụp ảnh sản phẩm thật, cập nhật trạng thái sản xuất. |
| Manager | Web | Quản lý robot và loại robot, lập lịch sản xuất, quản lý vật tư và bảng tương thích giấy–bút, mẫu chữ, bảng giá và % cọc tối thiểu, duyệt điều chỉnh giá vượt ngưỡng, phân công Staff, dashboard sản xuất và báo cáo. |
| Admin | Web | Cấp trên Manager. Tài khoản và vai trò, cấu hình tích hợp (cổng thanh toán, hãng vận chuyển, email), tham số hệ thống, audit log, dashboard toàn hệ thống. |

## 6. Scope & Limitations

### 6.1 Major Features (4 nhóm công việc)

| Nhóm | Features |
|---|---|
| 1. Website đặt hàng và quản trị | FE-01..FE-08, FE-15 |
| 2. Module tính giá | FE-09 |
| 3. Module AI phục dựng và lộ trình robot | FE-10 |
| 4. Thiết bị IoT, sản xuất, báo cáo | FE-11..FE-14 |

| ID | Feature |
|---|---|
| FE-01 | Tài khoản và phân quyền 5 vai trò (Customer, Staff, Technical Staff, Manager, Admin). |
| FE-02 | Website dịch vụ: giới thiệu 3 loại dịch vụ, thư viện mẫu chữ, bảng giá tham khảo, sản phẩm mẫu. |
| FE-03 | Đặt hàng 3 loại: Sao chép – Phục hồi (upload ảnh), Sáng tạo theo nét chữ đã học, Viết theo mẫu/Trang trí. |
| FE-04 | Chọn vật tư có ràng buộc tương thích (giấy → bút → mực), số lượng, giá ước tính tức thời; 2 cách: khách tự chọn trong danh mục hoặc để xưởng đề xuất. |
| FE-05 | Staff xử lý đơn: tiếp nhận/từ chối/yêu cầu bổ sung, phác thảo và đề xuất cách làm, lập báo giá bảng/file, trao đổi với khách. |
| FE-06 | Thanh toán 2 đợt qua VNPay/Momo: cọc theo % tối thiểu, phần còn lại + phí ship trước khi giao; hoàn tiền theo chính sách. |
| FE-07 | Giao hàng: phí ship tách riêng, lấy qua API hãng vận chuyển (GHN/GHTK), tạo vận đơn, theo dõi trạng thái; hoặc nhận tại xưởng. |
| FE-08 | Theo dõi đơn với 2 trạng thái độc lập (đơn hàng, sản xuất) và ETA tối đa có thể dời kèm thông báo. |
| FE-09 | Pricing Engine: giá theo loại giấy, khổ, bút, mực, số ký tự, độ phức tạp, số lượng; phí setup; chiết khấu; % cọc. |
| FE-10 | Module AI và lộ trình robot: phục dựng nét từ ảnh, sinh nét từ mẫu/font, học nét chữ (R&D), chuyển thành lộ trình cho FR3. |
| FE-11 | Quản lý robot và lập lịch sản xuất: danh sách, loại, trạng thái, gán job cho robot và kỹ thuật viên, xếp lại lịch khi robot hỏng. |
| FE-12 | Ứng dụng Flutter Desktop cho Technical Staff: nhận job, tải file, chuẩn bị/hiệu chuẩn, mô phỏng, chạy robot, giám sát, E-Stop, chụp/tải ảnh, cập nhật trạng thái sản xuất. |
| FE-13 | Thiết bị IoT kiểm soát lực bút: giá kẹp 3D, loadcell, ESP32, vòng điều khiển lực phối hợp robot. |
| FE-14 | Báo cáo và dashboard: sản xuất, doanh thu, hiệu suất robot, đơn trễ hạn. |
| FE-15 | Quản trị hệ thống (Admin): tài khoản, vai trò, tích hợp bên thứ ba, tham số, audit log. |

### 6.2 Limitations & Exclusions

| ID | Limitation |
|---|---|
| LI-01 | Không bao gồm bảo trì, sửa chữa phần cứng robot; hệ thống chỉ ghi nhận trạng thái robot (sẵn sàng/bảo trì/hỏng) và sự cố. |
| LI-02 | Không tự phát triển tầng động học và an toàn cấp thấp của robot (IK, tránh va chạm); dùng SDK và firmware Fairino. |
| LI-03 | Demo với 1 robot FR3 thật; robot khác trong danh sách có thể là robot mô phỏng để minh họa lập lịch nhiều robot. |
| LI-04 | Sao chép – Phục hồi chỉ nhận ảnh rõ, nền tương phản, không chồng nét nặng; ảnh hư hỏng nặng bị từ chối. |
| LI-05 | Không cam kết tái tạo 100% mọi nét chữ; kết quả là bản gần giống nhất, khách nghiệm thu qua phác thảo và ảnh sản phẩm. |
| LI-06 | Mỗi đơn 1 loại giấy, 1 loại bút, 1 màu mực; khổ tối đa A4 ở giai đoạn 1. |
| LI-07 | Chỉ dùng giấy trong danh mục xưởng; không nhận giấy khách tự gửi. |
| LI-08 | Thanh toán online qua cổng bên thứ ba, **tối đa 2 đợt (cọc và phần còn lại)**; không lưu thông tin thẻ; không trả góp. |
| LI-09 | Giao hàng nội địa qua hãng vận chuyển bên thứ ba; thời gian giao là ước tính, có thể dời. |
| LI-10 | Sáng tạo theo nét chữ đã học là R&D: nếu chưa đạt chất lượng, xưởng có thể từ chối loại đơn này hoặc chỉ nhận ở mức thử nghiệm. |
| LI-11 | Lập lịch: hệ thống gợi ý, Manager quyết định cuối; không tối ưu tự động toàn phần. |
| LI-12 | Không nhận viết chữ ký, giấy tờ pháp lý, văn bản giả mạo. |
