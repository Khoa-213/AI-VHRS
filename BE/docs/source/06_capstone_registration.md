# Phiếu đăng ký đề tài Capstone FA26SE097 (AI-VHRS)

> Chép lại từ PDF `FA26SE097_AI-VHRS_Phieudangky.pdf` (ký ngày 13/10/2026, thời gian thực hiện 09/2026 – 12/2026, nhóm GFA26SE13, chuyên ngành SE).
> Đây là tài liệu **đăng ký/nghiên cứu** (tiếng Anh). Phạm vi của nó hẹp hơn Report 1–3 ở một số chỗ (MVP) và có thêm phần nghiên cứu RQ1–RQ3 mà Report 1–3 không có. Số điện thoại không chép.

## 1. Người hướng dẫn
Supervisor 1: Lâm Hữu Khánh Phương · Supervisor 2: Trần Trọng Huỳnh.
(Report 1 chỉ liệt kê một giảng viên.)

## 2. Sinh viên
| Họ tên | MSSV | Vai trò |
|---|---|---|
| Hoàng Nguyễn Trọng Nhã | SE181839 | FE |
| Nguyễn Đình Duy | SE181803 | BE |
| Hoàng Anh Khoa | SS181074 | Leader/BE |
| Hoàng Bảo Ân | SE181603 | FE |
| Lê Đắc Trần Quang | SE181548 | FE |

## 3. Nội dung đăng ký

**Tên**: *Development of an AI-Assisted Vietnamese Handwriting Reproduction System Using a Robotic Arm* · VI: *Phát triển hệ thống sao chép chữ viết tay tiếng Việt có sự hỗ trợ của AI sử dụng cánh tay robot* · viết tắt **AI-VHRS**.

### a. Bối cảnh
Khách muốn chép lại thư tay cũ, hoặc viết nội dung theo nét chữ chọn sẵn trên giấy thật, phải thuê người viết (chậm, đắt, khó lặp lại). Font viết tay/AI chỉ ra ảnh; pen plotter (AxiDraw) cần vector thủ công, không phục hồi nét từ ảnh, xử lý kém dấu tiếng Việt. Xưởng viết tay có robot công nghiệp chưa có hệ thống nhận đơn, phục hồi/soạn nét và cho robot viết với lực bút kiểm soát. Dự án xây hệ thống đó và đo mức độ trung thực khi robot tái hiện chữ viết tay tiếng Việt.

### b. Giải pháp đề xuất
- **Order management web**: 3 loại đơn (Copy–Restore, Template writing, Creative writing) từ yêu cầu → phác thảo + duyệt báo giá → thanh toán 2 đợt → giao hàng.
- **Stroke recovery and composition service**: phục hồi đường nét, thứ tự, dấu từ ảnh; soạn nét từ văn bản bằng font single-line.
- **Trajectory planning and Robot Agent**: nét → chuyển động FR3 khả thi, mượt; chạy qua Fairino SDK với mô phỏng và E-Stop.
- **IoT pen-force module**: giá kẹp bút lò xo + cảm biến Hall + ESP32 đo lực chạm; Robot Agent chỉnh độ cao bút và nhấc bút khi quá lực.
- **Production and pricing support**: gợi ý lịch job-robot cho Manager; định giá theo vật tư, số ký tự, độ phức tạp, số lượng.

**MVP**: Copy–Restore và Template writing end-to-end trên một FR3 thật. **Stretch**: Creative writing theo phong cách đã học (R&D, chỉ đơn thử nghiệm).
**Out of scope**: động học và lớp an toàn robot (dùng Fairino SDK), sửa chữa robot, giấy > A4 hoặc khách tự cấp, chữ ký và giấy tờ pháp lý, lập lịch tự động hoàn toàn; robot khác trong demo lập lịch là mô phỏng.

### c. Yêu cầu chức năng (theo actor)
| Actor | Chức năng chính | Ví dụ nghiệm thu |
|---|---|---|
| Customer (Web) | Tạo đơn 1 trong 3 loại với giấy/bút/mực, xem giá ước tính; duyệt hoặc yêu cầu sửa phác thảo & báo giá; trả cọc (mặc định 50%) và phần còn lại qua VNPay/MoMo; theo dõi trạng thái đơn/sản xuất và ETA; nhận ảnh kết quả hoặc yêu cầu **một lần viết lại miễn phí**; chọn giao hàng (GHN/GHTK) hoặc nhận tại xưởng | Đơn thiếu thông tin bị từ chối kèm thông báo; đơn đủ được lưu với giá ước tính |
| Staff (Web) | Tiếp nhận/từ chối đơn; chuẩn bị và sửa phác thảo AI; lập báo giá (điều chỉnh ±15% kèm lý do); xác nhận thanh toán và hoàn tiền; tạo vận đơn và cập nhật ETA | Không gửi được báo giá trước khi lưu phác thảo |
| Technical Staff (Flutter Desktop) | Tải job được giao; hiệu chuẩn robot/giấy/bút; mô phỏng; chạy, giám sát, E-Stop; tải ảnh sản phẩm và sự cố | Job không chạy được cho tới khi hiệu chuẩn và mô phỏng đạt |
| Manager (Web) | Quản lý robot, vật tư, ma trận tương thích, mẫu chữ; gán/xếp lại job; đặt giá và cọc tối thiểu; duyệt điều chỉnh lớn; dashboard | Job của robot hỏng hiện ra để xếp lại kèm robot gợi ý |
| Admin (Web) | Quản lý tài khoản/quyền 5 vai trò; cấu hình tích hợp thanh toán, vận chuyển, email; xem audit log | Người không phải Manager bị chặn khỏi trang lập lịch |

AI, pricing, Robot Agent, IoT là module hệ thống, không phải actor. Simulation và dashboard là **Should**; các chức năng còn lại là **Must**.

### d. Yêu cầu phi chức năng
| Tiêu chí | Mục tiêu | Đo bằng |
|---|---|---|
| Performance | Ghi log thời gian phản hồi của pricing, sketch, restoration, packaging; đặt ngưỡng sau pilot | Server timing logs |
| Safety | Mọi lần thử E-Stop và quá lực: robot dừng, bút nhấc; ghi lại thời gian dừng | Robot Agent logs, thử lặp |
| Writing quality | Đo stroke IoU và độ lệch (mm); ngưỡng đặt theo pilot tuần 6 | Bộ test, scan overlay |
| Force quality | F_target mỗi bút trong 0,3–2,0 N (dải lực viết của người [7]); dải đặt theo hiệu chuẩn | Force logs, cân tham chiếu |
| Security, privacy | RBAC 5 vai trò, JWT, HTTPS; không lưu dữ liệu thẻ; webhook ký; xóa ảnh sau 90 ngày trừ khi đồng ý | Permission tests; deletion log |
| Reliability, usability | Mọi job demo kết thúc với trạng thái được log; webhook trùng không đổi gì; người mới đặt đơn không cần hướng dẫn | Demo log; webhook test; user test |

### e. Công nghệ
Lý thuyết: skeletonisation (Zhang–Suen), phục hồi thứ tự nét, soạn font single-line với dấu, biến đổi giấy → robot và velocity profiling cho tay 6 DoF, điều chỉnh lực bằng lò xo + cảm biến Hall, RBAC.
Thực hành: React, FastAPI, PostgreSQL; Python/OpenCV; Flutter Desktop (Windows); Python Robot Agent + Fairino SDK (TCP/IP); ESP32 qua USB serial; sandbox VNPay/MoMo, GHN/GHTK.
**Fallbacks**: adapter robot mô phỏng, độ cao bút cố định, adapter thanh toán và vận chuyển **mock**.

### f. Sản phẩm bàn giao
Source code có tag release (web, backend, stroke service, Robot Agent, Flutter, firmware ESP32); demo triển khai trên test server + một FR3 theo danh sách nghiệm thu (một đơn Copy–Restore, một đơn Template); module IoT lực + bản ghi hiệu chuẩn; tài liệu (Reports 1–3 SRS, hướng dẫn người dùng/triển khai, test plan, test report); gói nghiên cứu (bộ test có chú thích, script thí nghiệm, log, benchmark RQ1–RQ3, bản thảo bài báo).

### g. Kế hoạch
| Gói | Nội dung | Đầu ra | Tuần | Phụ trách |
|---|---|---|---|---|
| TP1 Requirements & design | Ma trận actor–quyền, SRS, kiến trúc, DB, API draft, test plan | SRS, ERD, API spec, test plan | 1–3 | Khoa, all |
| TP2 Web system | Tài khoản, 3 loại đơn, pricing, sketch & báo giá, thanh toán & giao hàng, lập lịch, dashboard | Web app + unit/integration tests | 3–12 | Nhã, Ân, Duy |
| TP3 Stroke service | Tiền xử lý, skeletonisation, thứ tự nét & dấu, Template writing, bộ test | Service API, test set có chú thích, kết quả RQ1 | 2–10 | Khoa |
| TP4 Robot & IoT | Trajectory planning, Robot Agent, Flutter app, force module, firmware | Robot Agent, Flutter app, module đã hiệu chuẩn | 3–13 | Quang, Khoa |
| TP5 Integration & evaluation | Test end-to-end trên FR3, đo NFR, chạy RQ2–RQ3 | Test report, benchmark | 11–15 | All |
| TP6 Documentation | Reports, guides, bài báo, demo cuối | Tài liệu cuối, bản thảo bài báo | 13–16 | Khoa, Duy |

Mốc: SRS duyệt (tuần 3); pilot RQ1 trên bộ test (tuần 6); đơn đầy đủ đầu tiên do FR3 viết (tuần 10); xong test và benchmark (tuần 15).

## 3.3 Thông tin nghiên cứu
**Vấn đề**: phục hồi cách chữ được viết (đường nét, thứ tự, dấu) từ ảnh tĩnh còn mở; chữ Việt có thể mang hai dấu chồng nhau. Nghiên cứu hiện có chủ yếu cho chữ Latin/Hán; robot viết chủ yếu phát lại đường cho sẵn ở độ cao bút cố định.

- **RQ1**: pipeline phục hồi đề xuất (skeletonisation + suy luận thứ tự nét và dấu) có stroke IoU, độ chính xác thứ tự nét và dấu cao hơn baseline skeleton-vectorisation không?
- **RQ2**: kiểm tra khả thi và làm mượt vận tốc giảm bao nhiêu độ lệch trên giấy và jerk so với gửi điểm thô ở tốc độ không đổi, và đổi lại thời gian viết bao nhiêu?
- **RQ3**: bù độ cao bút từ module lực có giữ lực gần F_target hơn (RMS thấp hơn, nhiều thời gian trong dải hiệu chuẩn hơn, ít nét đứt hơn) so với độ cao bút cố định không?
- Giả thuyết H1–H3: mỗi phương pháp đề xuất thắng baseline trên chỉ số chính. Creative writing mang tính khám phá.

**Mục tiêu**: O1 bộ test tiếng Việt có ground-truth nét và so với baseline (RQ1); O2 đo ảnh hưởng xử lý quỹ đạo trên FR3 (RQ2); O3 đo ảnh hưởng bù lực (RQ3); O4 công bố protocol, script, log để tái lập.

**Dữ liệu**: ảnh render từ HANDS-VNOnDB [3] (quỹ đạo bút cho ground-truth thứ tự nét, dùng theo giấy phép) + mẫu viết trên tablet của tình nguyện viên đồng ý; chỉ ảnh rõ; tách validation/test theo người viết (writer-disjoint).

| RQ | Baseline | Chỉ số | Thí nghiệm |
|---|---|---|---|
| RQ1 | Zhang–Suen skeleton + polyline, thứ tự trái → phải | Stroke IoU, độ chính xác thứ tự nét và dấu (%) | Offline trên test split; ablation bỏ suy luận dấu |
| RQ2 | Điểm thô, tốc độ không đổi | Độ lệch (mm), RMS jerk, thời gian viết (s) | Cùng mẫu trên FR3, scan overlay |
| RQ3 | Độ cao bút hiệu chuẩn cố định | % thời gian trong dải lực, RMS lực (N), nét đứt/trang | Cùng mẫu và bút trên FR3 |

**Protocol**: cùng mẫu, giấy, bút, cài đặt cho mỗi phương pháp; 5 lần lặp mỗi điều kiện robot; mean ± SD với kiểm định Wilcoxon signed-rank; pilot RQ1 offline trước tuần 6; lưu phiên bản code, config, seed, phần cứng, log thô trong repo.

**Đóng góp**: (1) pipeline phục hồi nét thích nghi với dấu tiếng Việt, đánh giá với baseline chung (thinning và Fairino SDK là công cụ có sẵn, đóng góp là điều chỉnh + đánh giá); (2) protocol benchmark và bộ test cho viết tay tiếng Việt bằng robot; (3) đo tác động của làm mượt quỹ đạo và bù lực trên tay 6 DoF. Mối đe dọa tính hợp lệ: ảnh rõ, ít người viết, một robot; không tuyên bố cải thiện trước khi đo.

**Tài liệu tham khảo**: [1] Zhang & Suen, thinning, CACM 27(3) 1984. [2] Doermann & Rosenfeld, recovery of temporal information from static handwriting images, IJCV 15, 1995. [3] Nguyen et al., HANDS-VNOnDB, Pattern Recognition 78, 2018. [4] Graves, generating sequences with RNNs, arXiv:1308.0850, 2013. [5] Kotani, Tellex, Tompkin, decoupled style descriptors, ECCV 2020. [6] Kotani & Tellex, Teaching robots to draw, ICRA 2019. [7] Schomaker & Plamondon, pen force and pen-point kinematics, Biol. Cybern. 63, 1990.

## 4. Rủi ro và ràng buộc
(1) FR3 không có sẵn → dùng adapter mô phỏng; (2) phục hồi dưới ngưỡng → Staff sửa phác thảo hoặc từ chối ảnh; (3) module lực không ổn định → độ cao bút cố định cho demo, RQ3 báo là hạn chế; (4) không có sandbox thanh toán/vận chuyển → adapter mock. Bảng change log và traceability nằm ở phụ lục của bản gốc (không có trong PDF này).
