# Report 2 – Project Management Plan (AI-VHRS)

> Chép lại từ PDF `REPORT (3).pdf` (Capstone Report 2, TP.HCM 09/2026). Bảng phân công RACI trong PDF bị vỡ cột (chữ xoay), nên phần 4 dưới đây
> được suy lại từ dữ liệu có trong PDF; kiểm tra lại với bản gốc nếu cần chính xác tuyệt đối. Số điện thoại, ảnh bìa không chép.

## 1. Overview

### 1.1 Scope & Estimation (WBS, man-days)

| # | Hạng mục | Độ phức tạp | Effort |
|---|---|---|---|
| 1 | **Nhóm 1 – Website đặt hàng và quản trị (React + FastAPI)** | | **42** |
| 1.1 | Tài khoản, phân quyền 5 vai trò, hồ sơ (FE-01) | Medium | 4 |
| 1.2 | Website dịch vụ, thư viện mẫu, bảng giá tham khảo (FE-02) | Simple | 2 |
| 1.3 | Tạo đơn 3 loại: upload ảnh, nội dung theo nét đã học, viết theo mẫu + canvas (FE-03) | Complex | 7 |
| 1.4 | Chọn vật tư có ràng buộc giấy → bút → mực, số lượng (FE-04) | Medium | 3 |
| 1.5 | Staff xử lý đơn: tiếp nhận/từ chối/bổ sung, phác thảo, báo giá bảng/file, tin nhắn (FE-05) | Complex | 8 |
| 1.6 | Thanh toán 2 đợt VNPay/Momo: cọc theo %, phần còn lại, webhook, hoàn tiền (FE-06) | Complex | 6 |
| 1.7 | Giao hàng: API phí ship GHN/GHTK, vận đơn, webhook trạng thái, nhận tại xưởng (FE-07) | Complex | 5 |
| 1.8 | Double state (đơn + sản xuất), ràng buộc đồng bộ, ETA và dời ETA, thông báo (FE-08) | Complex | 5 |
| 1.9 | Admin: tài khoản, tích hợp, tham số, audit log (FE-15) | Medium | 2 |
| 2 | **Nhóm 2 – Module tính giá** | | **8** |
| 2.1 | Pricing Engine: công thức giá, hệ số độ phức tạp, chiết khấu, % cọc, snapshot (FE-09) | Complex | 5 |
| 2.2 | Màn hình cấu hình bảng giá, vật tư, bảng tương thích; duyệt điều chỉnh giá (UC-42, UC-44) | Medium | 3 |
| 3 | **Nhóm 3 – Module AI phục dựng và lộ trình robot** | | **28** |
| 3.1 | Tiền xử lý ảnh, skeletonization, vector hóa, thứ tự nét và dấu tiếng Việt (OT-1) | Complex | 10 |
| 3.2 | Text-to-Trajectory: font single-line, ghép dấu, dàn trang, biến thể tự nhiên (OT-3) | Complex | 6 |
| 3.3 | Học nét chữ từ mẫu và sinh nội dung mới (OT-2, R&D) | Complex | 6 |
| 3.4 | Lập lộ trình FR3: hồ sơ vận tốc, biến đổi giấy → robot, kiểm tra khả thi, gói job | Complex | 6 |
| 4 | **Nhóm 4 – Thiết bị IoT điều khiển, sản xuất và báo cáo** | | **29** |
| 4.1 | Quản lý robot, loại robot; lập lịch sản xuất, gợi ý và xếp lại lịch (FE-11) | Complex | 5 |
| 4.2 | Flutter Desktop App: job, tải file, hiệu chuẩn, mô phỏng, chạy, E-Stop, chụp/tải ảnh, trạng thái (FE-12) | Complex | 9 |
| 4.3 | Robot Agent (Python, Fairino SDK): kết nối, chạy lộ trình, telemetry, an toàn | Complex | 5 |
| 4.4 | Thiết bị IoT lực bút: giá kẹp 3D, loadcell + ESP32, firmware, vòng điều khiển lực (FE-13) | Complex | 6 |
| 4.5 | Báo cáo và dashboard sản xuất, doanh thu, robot (FE-14) | Medium | 4 |
| 5 | **Tích hợp, kiểm thử và tài liệu** | | **12** |
| 5.1 | Tích hợp hệ thống, kiểm thử end-to-end trên robot thật | Complex | 8 |
| 5.2 | Tài liệu (Report 1–3, SRS, slide), demo | Medium | 4 |
| | **Tổng** | | **119 man-day** |

### 1.2 Project Objectives
Hệ thống vận hành xưởng viết tay bằng robot chạy end-to-end trên tay Fairino FR3 thật: khách đặt đơn → Staff tiếp nhận, phác thảo, báo giá → khách cọc →
Manager xếp lịch robot → Technical Staff chạy robot qua Flutter App có kiểm soát lực → ảnh sản phẩm → khách nghiệm thu → thanh toán phần còn lại + phí ship → giao hàng.
Phân bổ effort: Requirement & Design ~15%, Coding ~60%, Testing ~15%, PM & Documentation ~10%.

**Quality (các tầng kiểm thử):**

| # | Giai đoạn | Phạm vi | Ghi chú |
|---|---|---|---|
| 1 | Reviewing | 100% PR có review | Bắt buộc trước khi merge |
| 2 | Unit Test | ≥ 70% module xử lý ảnh/vector hóa/quỹ đạo | FR-05, FR-08, FR-09, FR-30 |
| 3 | Integration Test | 100% luồng nhập liệu → Motion Generation → Robot | Test trên robot thật |
| 4 | System Test | ≥ 90% phiên viết end-to-end thành công (NFR-05) | Trước mỗi mốc Review/Hội đồng |
| 5 | Acceptance Test | Đạt ngưỡng NFR-02 (similarity ≥ 80%) và NFR-10 (fidelity canvas) | GVHD & nhóm cùng đánh giá |

Milestone Timeliness ≥ 90%. Năng lực khả dụng ước tính ~135–200 man-day trong 9–10 tuần.

### 1.3 Project Risks

| # | Rủi ro | Impact | Possibility | Kế hoạch ứng phó |
|---|---|---|---|---|
| 1 | AI phục dựng nét từ ảnh (OT-1) không đạt ngưỡng độ giống | Cao | Trung bình | R&D từ tuần 1; Staff được chỉnh sửa phác thảo thủ công trước khi báo giá; OT-3 là phương án demo chắc chắn. |
| 2 | Học nét chữ (OT-2) chưa khả thi trong thời gian đồ án | Trung bình | Cao | Mức Should (R&D, LI-10); literature review sớm; xưởng được từ chối loại đơn này. |
| 3 | SDK Fairino FR3 thiếu tài liệu, chu kỳ lệnh servo không đủ cho vòng lực | Cao | Trung bình | Spike tuần 1–2, đo chu kỳ; vòng lực ở mức lò xo thụ động (L0) nếu chưa đạt. |
| 4 | Thời gian tiếp cận robot tại xưởng hạn chế; robot hỏng | Cao | Trung bình | Lịch cố định với xưởng; mô phỏng trong Flutter App; robot mô phỏng cho demo lập lịch. |
| 5 | IoT lực (loadcell, ESP32, giá kẹp 3D) nhiễu, lệch, cơ khí không chắc | Trung bình | Trung bình | Dựa trên giá kẹp 3D đã có và số đo của anh Sơn tại xưởng; hiệu chuẩn bằng cân; lọc tín hiệu. |
| 6 | Bảng giá và công thức giá không hợp lý với thực tế | Trung bình | Trung bình | Tham khảo giá thị trường, xin ý kiến mentor/xưởng; tham số hóa hoàn toàn để Manager chỉnh; Staff điều chỉnh ±15%. |

## 2. Management Approach
Scrum, sprint 2 tuần, Sprint Review/Demo cuối mỗi sprint cùng GVHD.
- Sprint 1–2: spike SDK FR3 và giá kẹp lực, walking skeleton (đơn Viết theo mẫu → lộ trình → Flutter App → robot viết), song song khung website và state machine.
- Sprint 3–4: Staff xử lý đơn, Pricing Engine, thanh toán, lập lịch robot, AI phục dựng từ ảnh.
- Sprint 5–6: giao hàng, kiểm soát lực, ảnh sản phẩm và nghiệm thu, báo cáo, R&D học nét chữ.
- Sprint 7: tích hợp, kiểm thử, demo.

**2.2 Quality Management**: Defect Prevention (review thiết kế state machine, công thức giá, giao thức Flutter ↔ Backend ↔ Robot Agent trước khi code); code review bắt buộc qua Pull Request GitHub;
Unit Testing (Pricing Engine, state machine mọi chuyển trạng thái hợp lệ/không hợp lệ, module AI và lộ trình); Integration Testing (web ↔ API ↔ AI; Backend ↔ Flutter ↔ Robot Agent ↔ FR3; cổng thanh toán và GHN sandbox); System Testing (đơn end-to-end trên robot thật trước mỗi mốc).

**2.3 Training**: FR3 SDK/an toàn cobot (Khoa, Duy, tuần 1–2); Computer Vision/skeletonization/mô hình sinh chữ (Khoa, Duy, tuần 1–3); Flutter Desktop + Robot Agent (Quang, Nhã, tuần 1–2); ESP32/loadcell/HX711 (Duy, Ân, tuần 2–3); in 3D giá kẹp (Ân, Quang, tuần 3, optional); React + FastAPI + PostgreSQL + VNPay/Momo/GHN (Nhã, Ân, Quang, tuần 1–2).

## 3. Project Deliverables

| # | Deliverable | Hạn | Ghi chú |
|---|---|---|---|
| 1 | Phiếu đăng ký đề tài v1.1 | Tuần 4–5 (Review 1) | Cập nhật theo mô hình xưởng và 5 actor |
| 2 | Report 1 v2.0 | Tuần 4–5 | |
| 3 | Report 2 v2.0 | Tuần 4–5 | |
| 4 | Slide Review 1 + slide dự phòng (cơ chế lực, IoT) | Tuần 4–5 | Mang module kẹp bút đi demo |
| 5 | Report 3 – SRS v2.0 | Tuần 8–9 (Review 2) | |
| 6 | Demo walking skeleton trên robot thật | Tuần 8–9 | OT-3 + Flutter App + robot |
| 7 | Report 3 – Project Tracking | Tuần 8–9 và tuần 14 | |
| 8 | Hệ thống hoàn chỉnh + slide + demo | Tuần 14 (Hội đồng 1.1) | |
| 9 | Tài liệu final & bảo vệ | Tuần 15 (Hội đồng 1.2) | |

## 4. Responsibility Assignments (suy lại từ PDF vỡ cột)
D = Do, R = Review, S = Support, I = Informed. Thứ tự cột: Khoa, Duy, Nhã, Ân, Quang.

| Hạng mục | Khoa | Duy | Nhã | Ân | Quang |
|---|---|---|---|---|---|
| Project Planning & Tracking | D | S | S | S | S |
| Report 1, Report 2 | D | S | S | S | S |
| SRS (Report 3) | R | D | S | S | S |
| Nhóm 1: Website Customer (đặt hàng, vật tư, thanh toán, theo dõi) | I | S | D | R | S |
| Nhóm 1: Website Staff, Manager, Admin | S | S | R | D | S |
| Nhóm 1: Backend order, double state, payment, delivery | D | D | I | S | I |
| Nhóm 2: Pricing Engine | R | D | S | I | I |
| Nhóm 3: AI phục dựng, sinh nét, học nét chữ | D | D | I | I | I |
| Nhóm 3: Lập lộ trình FR3 | D | R | I | I | S |
| Nhóm 4: Quản lý robot, lập lịch, báo cáo | S | D | S | R | I |
| Nhóm 4: Flutter Desktop App | R | I | S | S | D |
| System Integration & Testing | D | D | S | S | S |
| Final Documentation & Demo | D | S | S | S | S |

## 5. Project Communications
Weekly Sprint Sync (cả nhóm + GVHD, hàng tuần); Sprint Review & Demo (cuối mỗi sprint, demo trên robot); buổi làm việc tại xưởng (nhóm robot/IoT + xưởng, anh Sơn, hàng tuần); Status Report theo `Report3_Project_Tracking.xlsx`; vấn đề phát sinh qua email/nhóm chat.

## 6. Configuration Management
- **Tài liệu**: Google Drive chung, đặt tên `<Mã đề tài>_<Tên tài liệu>_v<Version>`; ghi Record of Changes ở đầu mỗi tài liệu.
- **Source code**: GitHub, Gitflow rút gọn: `main` (ổn định, demo), `develop` (tích hợp), `feature/*`; merge vào develop/main bắt buộc qua PR có ≥ 1 review.
- **Công nghệ**: React (Website); Python/FastAPI (Backend, Pricing, AI); Flutter Desktop (Technical Staff); Python + Fairino SDK (Robot Agent); ESP32 + Arduino/PlatformIO (IoT lực). AI/CV: OpenCV, scikit-image, PyTorch. Phần cứng: Fairino FR3, loadcell, ESP32, giá kẹp 3D, camera chụp sản phẩm. DB: PostgreSQL, file (ảnh, gói job, ảnh sản phẩm) trên object storage. Tích hợp: VNPay/Momo sandbox, GHN/GHTK API, SMTP email. Deployment: server nội bộ/cloud cho web; máy trạm tại xưởng chạy Flutter App + Robot Agent.
