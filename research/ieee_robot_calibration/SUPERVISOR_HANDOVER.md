# Bàn giao cho giảng viên hướng dẫn

Ngày: 17/11/2026 · Gói nghiên cứu: `research/ieee_robot_calibration/` · Bản thảo: `paper/AI_VHRS_IEEE_Paper.pdf`
(IEEE hội nghị, hai cột, tiếng Anh, 8 trang). Bản thảo **chưa nộp, chưa được bình duyệt**. Thông tin tác giả và đơn vị đang
để trống (placeholder) để nhóm tự điền.

> **Lưu ý quan trọng:** mọi số liệu độ chính xác trong gói này đều là **kết quả mô phỏng**. Chưa có lệnh chuyển động nào gửi
> tới robot FAIRINO FR3 thật. Dữ liệu thật duy nhất được dùng là hai lần đọc trạng thái controller (chỉ đọc) đã lưu sẵn trong
> `robot_agent/runs/`, dùng để kiểm tra mô hình danh định. Độ chính xác vật lý của robot hiện **chưa biết**.

## 1. Tên đề tài

**Đánh giá bằng mô phỏng phương pháp hiệu chuẩn động học MUKCa với hai và ba socket, kết hợp bù trước quỹ đạo, cho cobot
6 bậc tự do có controller đóng trong hệ thống tái tạo chữ viết tay tiếng Việt.**

Tên tiếng Anh: *Simulation-Based Evaluation of Two- and Three-Socket MUKCa Kinematic Calibration with Trajectory
Pre-Compensation for a Closed-Controller 6-DOF Cobot in Vietnamese Handwriting Reproduction.*

## 2. Mục tiêu

* RQ1: Hiệu chuẩn bằng socket giảm sai số định vị của một cobot 6 bậc tự do (mô phỏng) được bao nhiêu?
* RQ2: Trong điều kiện nào cấu hình 3 socket tốt hơn rõ rệt so với cấu hình 2 socket gốc của MUKCa?
* RQ3: Bù trước quỹ đạo dựa trên mô hình đã hiệu chuẩn cải thiện độ chính xác viết chữ đến đâu khi có nhiễu đo và sai số
  hình học?

## 3. Khoảng trống nghiên cứu (research gap)

* MUKCa (Franzese và cộng sự, *Communications Engineering*, 2026) hiệu chuẩn cobot rẻ, không cần laser tracker, nhưng giả định
  robot **dư bậc tự do** (7 DOF): chuyển động trong không gian null cho nhiều cấu hình khác nhau khi bi nằm cố định trong
  socket. FR3 chỉ có 6 bậc tự do, chưa có phân tích nào cho trường hợp này.
* Controller của FR3 là **controller đóng**: không nạp được mô hình đã hiệu chuẩn, nên phải sửa điểm đích (bù trước).
* Chưa có đánh giá nào nối hiệu chuẩn với **chất lượng chữ viết tiếng Việt** (dấu thanh, dấu mũ, móc nằm sát nhau trong vài mm,
  nên sai lệch dưới 1 mm đã nhìn thấy được).

## 4. Đóng góp và mức độ đã xác minh

| Đóng góp | Mức độ xác minh |
|---|---|
| Phân tích khả nhận dạng của bài toán MUKCa trên robot 6 DOF: rank 21/39, không phụ thuộc số socket hay góc nghiêng | Đã xác minh bằng mô phỏng (240 cấu hình, 10 robot/ô); khớp công thức lý thuyết 4R+6−3−6 |
| Tổng quát hoá hàm mục tiêu MUKCa cho K socket và so sánh 4 bố trí với cùng số mẫu | Đã xác minh bằng mô phỏng (30 robot, kiểm định thống kê) |
| Giải thích khác biệt qua chỉ số khả quan sát O1 và thí nghiệm loại bỏ regularization | Đã xác minh bằng mô phỏng |
| Sơ đồ bù trước cho controller đóng + dò khung giấy 3 điểm, đánh giá trên quỹ đạo chữ tiếng Việt | Đã xác minh bằng mô phỏng; **chưa thử trên robot thật** |
| Khung mô phỏng tái lập được, mô hình danh định được đối chiếu với controller thật | Đối chiếu với 2 lần đọc controller (sai số ≤ 0,011 mm) và PyBullet (≤ 0,00076 mm). Đây là kiểm tra **mô hình danh định**, không phải độ chính xác của robot |

Về tính mới: ý tưởng dùng nhiều socket **không phải mới** (MUKCa đã nhắc đến). Phần mới là bằng chứng định lượng cho robot
6 DOF có controller đóng và ứng dụng viết chữ. Chưa thực hiện tìm kiếm tài liệu có hệ thống (Scopus/IEEE Xplore) — xem mục 11.

## 5. Phương pháp

* **Mô hình danh định**: URDF của hãng (FR3 V6) + offset flange 100 mm; FK/IK viết bằng NumPy.
* **Robot "thật" mô phỏng**: mỗi seed sinh một robot riêng với sai lệch hình học (σ 0,5 mm; 0,1°), sai số truyền động điều hoà
  (≤ 0,003°), độ đàn hồi do trọng lực (độ cứng giả định), sai lệch offset bi/bút (σ 0,3 mm). Hai thành phần sau nằm **ngoài**
  lớp mô hình được hiệu chuẩn. Bộ giải không bao giờ thấy ground truth (có assert và test).
* **Hiệu chuẩn**: 39 tham số; hàm mục tiêu MUKCa tổng quát cho K socket (độ nhất quán trong từng socket + khoảng cách đã biết
  giữa các socket + regularization λ = 1e-4); giải bằng Levenberg–Marquardt (SciPy).
* **Bố trí so sánh** (cùng N = 60 mẫu): S2 (dụng cụ 2 socket của MUKCa), S3L (3 socket thẳng hàng), S3 (3 socket tam giác đều
  150 mm trên mặt viết), S2x2 (dụng cụ 2 socket đặt ở 2 vị trí).
* **Bù trước**: q* = IK theo mô hình đã hiệu chuẩn; gửi cho controller tư thế FK danh định của q*, controller giải ngược ra đúng q*.
* **Khung giấy**: dò 3 góc giấy, dựng khung bằng Gram–Schmidt giống hàm `build_frame` của AI-VHRS.
* **Metric**: MAE/RMSE/P95/max trên mặt giấy; Chamfer/HD95/Hausdorff (cùng định nghĩa Service G); shape MAE sau khi khớp cứng
  2-D; tỉ lệ tiếp xúc bút.
* **Thống kê**: đơn vị phân tích là một robot; bootstrap CI 95%; Wilcoxon có cặp + hiệu chỉnh Holm; tỉ lệ thắng.

Chi tiết: `METHODOLOGY.md`.

## 6. Môi trường

* Python 3.11.9, NumPy, SciPy 1.17.1, Matplotlib 3.10.9, pytest; Windows 11, 12 tiến trình song song.
* `BE/.venv` (có sẵn) chỉ để sinh dữ liệu chữ; `robot_agent/.simenv` (có sẵn, có PyBullet) chỉ để đối chiếu FK.
* LaTeX: tectonic 0.17.0 (nằm trong `tools/`, không đưa lên git).
* Không dùng backend, database, Supabase hay robot thật. Lệnh chạy lại toàn bộ: `REPRODUCIBILITY.md`.

## 7. Thí nghiệm

| Mã | Nội dung | Quy mô | Trạng thái |
|---|---|---|---|
| OBS | Khả nhận dạng (rank, giá trị suy biến) | 4 bố trí × 6 góc nón × 10 robot | Đã chạy xong |
| E1 (P0) | Độ chính xác TCP sau hiệu chuẩn | 30 robot × 500 tư thế kiểm tra | Đã chạy xong |
| E5 (P0) | Độ chính xác quỹ đạo chữ viết, 6 phương pháp A/B/C/D/E/O | 30 robot × 10 mẫu chữ | Đã chạy xong |
| E2 | Nhiễu, sai số ngoài mô hình, độ lớn sai số hình học | 20 robot/thiết lập | Đã chạy xong |
| E2b | Ảnh hưởng của λ | 20 robot/thiết lập | Đã chạy xong |
| E3 | Số mẫu N (12–150) | 20 robot/thiết lập | Đã chạy xong |
| E4 | Khoảng cách socket, góc nón | 20 robot/thiết lập | Đã chạy xong |

Tất cả các dòng kết quả đều ở trạng thái "ok", không loại bỏ trial nào. 14 test kiểm tra khung mô phỏng đều đạt.

## 8. Kết quả chính (mô phỏng)

* **Khả nhận dạng**: rank 21/39 ở mọi bố trí và mọi góc nón. Thêm socket không tăng rank mà làm các hướng yếu được kích thích
  tốt hơn (O1 tại 30°: S2 0,038; S3 0,061).
* **E1** (RMSE sau căn chỉnh, trung bình ± SD): danh định 0,748 ± 0,260 mm; S2 0,109 ± 0,045; S3L 0,109 ± 0,051; S2x2
  0,049 ± 0,011; S3 **0,044 ± 0,005** mm. S3 tốt hơn S2 60% (thắng 28/30 robot, p_Holm = 5,2·10⁻⁸). S3L **không khác** S2
  (p = 0,78). S3 tốt hơn S2x2 10% (p = 0,039).
* **E5** (MAE trên giấy): B (cách làm hiện tại: mô hình danh định + dò giấy) 0,796 mm; C (S2 + bù trước) 0,180 mm; D (S3 + bù
  trước) 0,150 mm; oracle 0,141 mm. Shape MAE: B 0,233 → C 0,037 → D **0,010** mm (D so với C −72%, p = 1,6·10⁻⁷). Trên MAE,
  D không khác S2x2 và không khác oracle (p = 0,62): phần còn lại chủ yếu do nhiễu dò giấy.
* **Độ nhạy**: lợi thế của S3 mất dần khi nhiễu đo tăng 4–8 lần (ở 8 lần, S2x2 0,189 nhỉnh hơn S3 0,199 mm). S3 với 12 mẫu
  (0,068 mm) đã tốt hơn S2 với 150 mẫu (0,116 mm). S3 ở nón 10° đã tốt hơn S2 ở nón 45°. Với λ ≤ 1e-6, S2 cải thiện còn
  0,083–0,088 mm nhưng vẫn kém S3 khoảng 2 lần.
* **Trường hợp thất bại** (đã báo cáo trong bài): E1 — S3 kém S2 ở 2/30 robot (seed 1009, 1027, chênh ≤ 0,005 mm); E5 — seed
  1004 shape của C kém B; seed 1021 MAE của B thấp hơn D và oracle.

Bảng đầy đủ: `EXPERIMENT_RESULTS.md`.

## 9. Giới hạn

* Chỉ là mô phỏng; độ lớn các nguồn sai số do nhóm giả định.
* Chưa mô hình hoá: backlash, trễ, nhiệt, sai số động khi viết nhanh, sai số hình dạng socket/bi, biến dạng giấy, độ đàn hồi
  của bút.
* Không xác định được khung đế (gauge); dựa vào dò giấy để bù.
* Dữ liệu chữ là font sinh tự động (Hershey), không phải chữ viết tay người.
* λ = 1e-4 giữ theo MUKCa dù mô phỏng cho thấy 1e-6 tốt hơn, vì trên robot thật không có ground truth để chỉnh λ.
* Bài dài 8 trang, vượt mục tiêu 4–6 trang.

Chi tiết: `LIMITATIONS.md`.

## 10. Việc cần kiểm chứng trên robot thật

Danh sách đầy đủ 18 thông số (giá trị hiện tại, giả định mô phỏng, quy trình đo, đơn vị, thiết bị, ảnh hưởng tới kết luận)
ở `REAL_WORLD_VALIDATION_REQUIRED.md`. Quan trọng nhất:

1. Độ chính xác tuyệt đối hiện tại của FR3 trên vùng viết (viết lưới chữ thập, scan, đo).
2. Backlash / sai số đảo chiều (MUKCa ghi nhận đây là nguyên nhân thất bại).
3. Độ lặp lại khi đặt bi vào socket và góc nghiêng thực tế đạt được (quyết định lợi thế của S3).
4. Chế tạo tấm 3 socket và đo khoảng cách giữa các socket.
5. Nhiễu dò giấy (đang quyết định giới hạn dưới ~0,14 mm).
6. Viết bộ 10 mẫu chữ bằng B, C, D trên robot thật, scan và chấm bằng chính `metrics.py`.

Mọi bước trên robot thật cần được nhóm phê duyệt, chạy tốc độ thấp và có người trực nút dừng khẩn cấp.

## 11. Điểm cần thầy/cô góp ý

1. **Hội nghị/tạp chí mục tiêu** và giới hạn số trang: có rút xuống 6 trang (chuyển E2b/E3/E4 sang phụ lục) không?
2. Có chấp nhận nộp bài **chỉ mô phỏng** không, hay phải chờ kết quả robot thật (mục 10)?
3. Giữ λ = 1e-4 (theo MUKCa) làm kết quả chính, hay chuyển sang 1e-6 và báo cáo 1e-4 như ablation?
4. Độ lớn các giả định sai số (mục 5) có hợp lý với cobot cỡ FR3 không; có nguồn số liệu nào của hãng/tài liệu để thay thế?
5. Cách đánh giá tính mới (mục 4) có đủ thận trọng không; cần tìm thêm tài liệu nào?
6. Thứ tự tác giả, đơn vị, email và lời cảm ơn (đang để placeholder).
7. Quy trình an toàn và thiết bị đo (scanner, đồng hồ so, bi chuẩn) cho đợt kiểm chứng trên robot thật.
