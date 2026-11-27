# 06 — Thuật toán, kỹ thuật thật sự dùng và điểm nổi bật

Chỉ liệt kê thứ đã xác minh có lời gọi trong code. Đường dẫn BE tính từ `BE/app/services/`; agent tính từ `robot_agent/vhrs_agent/`.

**Loại:** A = thuật toán · M = phương pháp toán · E = kỹ thuật công nghệ · P = mẫu thiết kế · L = gọi thư viện · API = mô hình qua dịch vụ ngoài · SDK = lời gọi SDK robot.

**Mức kiểm chứng:** UT = test đơn vị trên dữ liệu tổng hợp · BS = benchmark ảnh tổng hợp · BR = benchmark ảnh chữ thật · SIM = mô phỏng · HW = đã chạy trên robot thật · SP = đang chạy trong sản phẩm.

## 1. Xử lý ảnh và nét chữ

| ID | Kỹ thuật | Loại | Ở đâu | Giải quyết gì; cách làm | Tự viết hay thư viện | Kiểm chứng |
|---|---|---|---|---|---|---|
| A01 | Làm phẳng ánh sáng | E | `stroke_ai/recovery.py:_flatten` | Giấy ố, sáng lệch. Phép đóng hình thái với nhân lớn rồi chia nền | `cv2.morphologyEx`, `cv2.divide` | UT, SP |
| A02 | Ngưỡng Otsu + ngưỡng thứ hai cho mực nhạt | A | `recovery.py:_binarise` | Mực phai. Mảnh nhạt, mảnh như nét bút, không chạm mực đậm thì được giữ | Otsu là `cv2.threshold`; luật mực nhạt tự viết | BR 50 ảnh, mực mờ nhân tạo |
| A03 | Chỉnh nghiêng theo hình chiếu | A | `recovery.py:_deskew` | Trang nghiêng. Quét ±5°, chọn góc có phương sai tổng hàng lớn nhất | Tự viết + `cv2.warpAffine` | UT |
| A04 | Tìm tờ giấy bằng GrabCut + nắn phối cảnh | A / L | `stroke_ai/paper.py` | Nền bàn, giấy rách | `cv2.grabCut`, `cv2.getPerspectiveTransform`; luật quyết định tự viết | BS |
| A05 | Bỏ dòng kẻ bằng phép mở theo hướng | A | `stroke_ai/ruling.py` | Vở kẻ ngang, ô ly; giữ chỗ chữ cắt qua dòng | Tự viết trên OpenCV | BS |
| A06 | Bỏ nếp gấp bằng Hough xác suất | A / L | `stroke_ai/folds.py` | Nếp gấp mọi góc | `cv2.HoughLinesP` + kiểm tự viết | BS |
| A07 | Lọc mực in theo màu Lab | E | `recovery_v2.py:_off_colour` | Logo, vạch lề đỏ | `cv2.cvtColor` | UT |
| A08 | **Làm mảnh Zhang-Suen** dạng bảng tra 256 | A | `recovery.py:zhang_suen` | Mực → khung xương 1 điểm ảnh | **Tự viết** bằng numpy | UT so từng điểm ảnh với bản chuẩn, SP |
| A09 | **Đồ thị khung xương + tỉa nhánh** | A | `recovery.py:_graph`, `_prune_spurs` | Điểm ảnh → nút và cạnh; bỏ nhánh ngắn hơn 1,2 bề rộng nét | **Tự viết** | UT, BR |
| A10 | **Ghép cạnh tại giao điểm theo hướng liên tục** | A | `recovery.py:_pair_edges`, `_assemble` | Nét đi thẳng qua chỗ giao; ghép cặp có góc ≥ 120° | **Tự viết** | UT. Thứ tự và chiều nét chưa từng đo |
| A11 | Trung bình trượt + Douglas-Peucker | M / L | `recovery.py:_smooth`, `_simplify` | Giảm điểm, khử bậc thang | `np.convolve`, `cv2.approxPolyDP` | UT |
| A12 | Thứ tự đọc: dòng → từ → dấu sau chữ | A | `recovery.py:_reading_order` | Robot viết theo trình tự người viết | **Tự viết** | BR |
| A13 | F1 có dung sai qua biến đổi khoảng cách | M | `recovery_v2.py:ink_f1` | Chỉ số "độ giống" trong sản phẩm | `cv2.distanceTransform` | Xem AI-08: không phải độ chính xác |
| A14 | **Ghép dấu tiếng Việt qua NFD** | A | `stroke_ai/text_to_stroke.py:_compose_char` | Font một nét chỉ có ASCII. Tách chữ gốc + mũ / trăng / móc + thanh, neo theo khung bao | **Tự viết**; `unicodedata.normalize` | UT, SP. Hình dấu chưa thử trên giấy |
| A15 | Ngắt dòng tham lam, căn đều, phân trang | A | `text_to_stroke.py:compose_text` | Văn bản → các trang | Tự viết | UT, SP |
| A16 | Rung có seed theo nội dung | E | `engine.py:content_seed` | Cùng nội dung luôn ra cùng nét | SHA-256 + `random.Random` | UT. Biên độ rất nhỏ (±0,12 mm ở cỡ 8 mm) |
| A17 | Font viền → đường tâm | A | `stroke_ai/outline_font.py` | Dùng font TTF cho robot một nét | PIL + A08–A10 | UT |
| A18 | **Láng giềng gần nhất + 2-opt theo cụm từ** | A | `stroke_ai/path_order.py:optimise` | Giảm quãng nhấc bút, giữ nguyên thứ tự trong từ; không bao giờ tệ hơn đầu vào | **Tự viết** | BR: −37,8% trung vị trên 50 trang (giấy ảo) |
| A19 | Mô hình thời gian viết | M | `stroke_ai/trajectory.py:compute_metrics` | Ước lượng thời gian cho giá và lịch | Tự viết; ba hằng số là giả định | UT |
| A20 | Đo chất lượng bản viết: nắn + ECC + Chamfer / HD95 / độ phủ | A / L | `quality_eval.py` | So ảnh thành phẩm với phác thảo, đơn vị mm | `cv2.findTransformECC` + tự viết | UT trên ảnh tổng hợp; ngưỡng chưa hiệu chuẩn |
| A21 | Mốc 4 ô vuông + homography cho phiếu mẫu | A | `stroke_ai/sample_sheet.py` | Nắn phiếu OT-2 về mm, cắt từng ô | OpenCV + tự viết | UT trên phiếu tổng hợp |
| A22 | Tách dấu ở ô mang dấu (union-find) | A | `sample_sheet.py:_carrier_marks` | Lấy dấu rời của người viết | Tự viết | UT |
| A23 | Căn bản chép chữ vào vùng (quy hoạch động đơn điệu) | A | `stroke_ai/htr_align.py:match` | Gắn chữ đọc được vào từng vùng từ | Tự viết | 3,9% vùng sai trên 6 trang, chấm bằng mắt |

Không tìm thấy trong code: ngưỡng thích nghi Sauvola, khớp Bézier / spline, DTW, mạng nơ-ron, PCA, phân cụm.

## 2. Trợ lý AI

| ID | Kỹ thuật | Loại | Ở đâu | Giải quyết gì | Tự viết hay thư viện | Kiểm chứng |
|---|---|---|---|---|---|---|
| B01 | Mô hình ngôn ngữ (Claude, GPT, Gemini) | API | `ai/llm.py` | Hiểu yêu cầu tiếng Việt, chọn hàm | Mô hình bên thứ ba; adapter HTTP tự viết | Test dùng hãng giả; đã chạy Gemini thật |
| B02 | Gọi hàm có cấu trúc | E | `ai/order_tools.py:SPECS` | AI chỉ làm việc qua 14 hàm của hệ thống | Tự viết | UT |
| B03 | Vòng lặp agent có trần | P | `ai/assistant.py:_turn` | Giới hạn 12 thao tác mỗi lượt | Tự viết | UT |
| B04 | Chuyển hãng khi lỗi | P | `ai/assistant.py:_run` | Một hãng lỗi vẫn trả lời được | Tự viết | UT |
| B05 | **Đề xuất: chụp → trả lại → hash → áp dụng** | P | `ai/proposals.py` | AI đề xuất, đơn không đổi cho tới khi áp dụng | Tự viết | UT |
| B06 | **Bộ máy hình học cho sửa nét** | E | `sketch_geometry.py:apply` | Sửa nét an toàn mà AI không đưa toạ độ | Tự viết | UT |
| B07 | Cây revision + hoàn tác / làm lại | P | `sketch_work.py` | Quay lại mọi bước sửa | Tự viết | UT |
| B08 | Đọc chữ viết tay cả trang | API | `ai/htr.py` | Gợi ý chữ cho vùng OT-1 | Gemini, Claude | CER 0,024 trên 50 trang (Gemini) |

## 3. Chuyển động và robot

| ID | Kỹ thuật | Loại | Ở đâu | Giải quyết gì; cách làm | Tự viết hay thư viện | Kiểm chứng |
|---|---|---|---|---|---|---|
| C01 | **Hệ trục giấy từ 3 điểm** | M | `motion/frame.py:build_frame` | Giấy → gốc robot. Gram-Schmidt + tích có hướng | Tự viết | HW (gián tiếp qua 2 nét) |
| C02 | Khớp mặt phẳng bình phương tối thiểu | A | `frame.py:113-122` | Giấy nghiêng, từ 4 điểm dò | `numpy.linalg.lstsq` | SIM |
| C03 | Lấy mẫu lại theo cung, giữ góc | A | `motion/plan.py:resample_stroke` | Điểm đều 0,2 mm, giữ đỉnh gập > 60° | Tự viết | SIM |
| C04 | **Tốc độ theo độ cong Menger + quét tiến / lùi** | A | `plan.py:speed_profile` | v = min(v_max, √(a/κ)), rồi giới hạn gia tốc dọc | Tự viết | SIM. Chế độ MoveL hiện không thực hiện biên dạng này |
| C05 | Giới hạn jerk, lọc S-curve | A | `plan.py:limit_jerk` | Giảm rung | Tự viết | SIM, mặc định tắt |
| C06 | Độ nhấn bút theo Hooke | M | `plan.py:press_mm` | x = F / k | Tự viết | HW (2 nét) |
| C07 | Bộ kiểm tất định | E | `motion/validate.py` | Trong giấy, độ cao, tốc độ, tầm với, hộp làm việc | Tự viết | SIM |
| C08 | Gộp và chia đoạn thẳng | A | agent `linear_motion.py:segments` | Giảm số lệnh, mỗi đoạn ≤ 5 mm | Tự viết | HW |
| C09 | MoveL theo mm/s | SDK | agent `linear_motion.py` | Chuyển động thẳng; nội suy bên trong bộ điều khiển, không rõ phương pháp | FAIRINO | HW |
| C10 | Động học ngược ở REAL | SDK | agent `fairino_robot.py:check_reachable` | Tầm với, đổi nhánh khớp; phương pháp nội bộ không rõ | FAIRINO | HW (suy ra) |
| C11 | Động học ngược ở mô phỏng | L | agent `kinematics.py` | Khớp cho hình 3D | PyBullet + tinh chỉnh tự viết | SIM |
| C12 | Phát hiện điểm kỳ dị | M | agent `kinematics.py:jacobian_ratio` | Tỉ số trị riêng nhỏ nhất / lớn nhất của Jacobian < 0,02 | Tự viết trên PyBullet | SIM |
| C13 | Giám sát bám quỹ đạo và dừng | E | agent `runner.py` | Robot có nghe lệnh không | Tự viết | SIM; ngưỡng chưa đo |
| C14 | Giám sát lực (ngưỡng + cửa sổ thời gian) | A | agent `gripper.py:SafetyMonitor` | Quá lực, mất tiếp xúc | Tự viết | SIM bằng mô hình lò xo; chưa nối phần cứng |

## 4. Hệ thống và dữ liệu

| ID | Kỹ thuật | Loại | Ở đâu | Giải quyết gì | Kiểm chứng |
|---|---|---|---|---|---|
| D01 | **Máy trạng thái hai lớp** (Python + trigger database) | P | `domain/job_rules.py`, `fn_order_state_guard` | Gọi thẳng API cũng không chuyển trạng thái sai được | UT (1.091 test đạt) |
| D02 | **Chống trùng lịch bằng EXCLUDE GiST** | E | `ex_job_robot_overlap`, `ex_job_technician_overlap` | Hai yêu cầu cùng lúc không đặt trùng robot | UT đồng thời |
| D03 | Tìm khe sớm nhất theo lịch làm việc | A | `domain/scheduling_rules.py:find_slot` | Gợi ý lịch, job vắt qua ngày | UT |
| D04 | **Gói sản xuất ký Ed25519 trên JSON chuẩn hoá** | E | `core/production_signing.py` | Robot chỉ nhận đúng bản khách đã duyệt; máy trạm chỉ cần khoá công khai | UT ở BE và agent |
| D05 | Ràng buộc nội dung bằng SHA-256 | E | `stroke_ai/trajectory.py:content_hash` | Phác thảo ↔ báo giá ↔ bản ghi duyệt ↔ job | UT |
| D06 | Webhook idempotent có chữ ký | E | `payments.py:_settle` | Callback trùng, sai thứ tự, sai số tiền | UT đồng thời |
| D07 | Hàng đợi lệnh bền, agent chủ động kéo | P | `robot_link.py:sync` | Không mở cổng vào mạng xưởng; lệnh có hạn | SIM |
| D08 | Khoá bi quan + khoá tư vấn | E | `SELECT … FOR UPDATE`, `pg_try_advisory_xact_lock` | Thao tác đồng thời; một lượt AI mỗi đơn; tác vụ nền không chạy chồng | UT |
| D09 | Danh mục cảnh báo, gộp trùng | P | `robot_ops.py:raise_alert` | Agent không tự hạ mức cảnh báo | UT |

Framework và thư viện (không phải thuật toán): FastAPI, SQLAlchemy, Alembic, Pydantic, OpenCV, numpy, Hershey-Fonts, fpdf2, openpyxl, cryptography, PyJWT, PyBullet, React, Flutter.

## 5. Điểm nổi bật để trình bày

| Điểm nổi bật | Vấn đề giải quyết | Giải pháp thật | Giá trị với doanh nghiệp | Bằng chứng | Cách demo |
|---|---|---|---|---|---|
| 1. Chuỗi niêm phong từ bản khách duyệt tới lệnh robot | Bản robot viết khác bản khách đã trả tiền | Hash phác thảo ghim vào báo giá, bản ghi duyệt, gói ký Ed25519; kiểm lại ở 4 điểm | Tranh chấp có chứng cứ; không ai sửa lén được | D04, D05; `production_snapshot.py:106-138` | Sửa một byte file quỹ đạo, cho thấy máy trạm từ chối |
| 2. AI bị kiểm soát bằng cấu trúc | LLM bịa hoặc sửa sai | LLM chỉ gọi 14 hàm có kiểm tra; nét do engine tất định sinh; thay đổi thành đề xuất có hash | Dùng được AI mà không giao quyền cho AI | B02, B05, B06 | Yêu cầu trợ lý đổi giá hoặc tự gửi đơn: không có hàm để làm |
| 3. Vector hoá chữ viết tay tự cài đặt | Ảnh thư tay → đường bút robot viết được | Zhang-Suen + đồ thị khung xương + ghép cạnh theo hướng + thứ tự "dấu sau chữ" | Chạy trên CPU, không cần GPU hay dịch vụ ngoài | A08–A12 | Tải ảnh thư, xem nét đặt cạnh ảnh gốc |
| 4. Khử nhiễu giấy có báo lại thứ đã bỏ | Thư cũ trên vở kẻ, giấy gấp | GrabCut + phép mở theo hướng + Hough; trả danh sách thứ đã loại | Nhân viên thấy máy đã bỏ gì | A04–A07 | Ảnh vở ô ly |
| 5. Trung thực về độ chắc chắn | Phục dựng dễ thành "bịa" | Nhãn vùng `ORIGINAL` / `RESTORED` / `INFERRED`; dấu "tái tạo bằng AI"; thiếu ký tự thì báo lỗi chứ không đổi font | Khách biết phần nào là gốc | `stroke_ai/regions.py` | Ảnh có vùng mực phai |
| 6. Ghép dấu tiếng Việt cho font một nét | Font robot công cộng chỉ có ASCII | Tách NFD, neo dấu theo khung bao, xếp chồng mũ + thanh | Viết đủ tiếng Việt không cần mua font | A14 | Gõ "Nguyễn Thị Hường" |
| 7. Tối ưu thứ tự nét giữ nguyên thứ tự trong từ | Robot nhấc bút đi xa | Láng giềng gần nhất + 2-opt theo cụm từ | Rút ngắn thời gian máy | A18 | Xem hai bản trước / sau |
| 8. Quy tắc nghiệp vụ nằm ở database | Gọi thẳng API để bỏ bước | Trigger trạng thái, EXCLUDE chống trùng lịch, chỉ mục "chỉ một" | Dữ liệu đúng kể cả khi client sai | D01, D02 | Gọi API chuyển trạng thái sai, nhận 409 |
| 9. An toàn robot theo lớp ở phần mềm | Phần mềm ra lệnh sai | Mỗi lệnh ≤ 5 mm, không gửi lại lệnh chuyển động, kênh dừng riêng, thiếu số đo thì từ chối chạy, mất liên lạc thì viết nốt nét rồi dừng | Giảm rủi ro khi vận hành | `fairino_robot.py:73-127`, `runner.py` | Trên mô phỏng: ngắt mạng giữa nét |
| 10. Thanh toán chịu được callback xấu | Callback trùng, sai tiền, đến muộn | Một điểm chốt, khoá theo thứ tự, tiền mồ côi gắn cờ hoàn | Không xác nhận sai, không mất dấu tiền | D06 | Gửi cùng webhook hai lần |

### Hai cách diễn đạt cho các điểm chính

**1. Chuỗi niêm phong.**
Kỹ thuật: mỗi phiên bản phác thảo có SHA-256 của file quỹ đạo. Hash này được ghim vào báo giá, bản ghi duyệt bất biến của khách, và gói sản xuất ký Ed25519 trên JSON chuẩn hoá. Backend so lại khi tải và khi bắt đầu viết; máy trạm xác minh chữ ký bằng khoá công khai.
Doanh nghiệp: thứ robot viết là đúng bản khách đã xem và đã trả tiền. Nếu file bị đổi ở bất kỳ khâu nào, máy không chạy.

**2. AI có kiểm soát.**
Kỹ thuật: mô hình ngôn ngữ không sinh toạ độ. Nó chọn hàm và tham số; server kiểm tham số bằng chính luật của form, chạy trong savepoint, rồi chụp kết quả thành đề xuất kèm hash trạng thái gốc.
Doanh nghiệp: trợ lý giúp khách soạn đơn nhanh hơn, nhưng không tự đổi giá, không tự gửi đơn, không tự thanh toán, và mọi thay đổi đều truy được.
Lưu ý khi nói: hiện web tự áp dụng đề xuất (AI-01), nên không nói "khách luôn bấm đồng ý" cho tới khi sửa.

**3. Vector hoá chữ viết tay.**
Kỹ thuật: pipeline thị giác máy tính cổ điển tự cài đặt, không mô hình học: làm phẳng sáng, Otsu, Zhang-Suen dạng bảng tra, đồ thị khung xương, ghép cạnh tại giao điểm theo hướng liên tục, sắp thứ tự đọc.
Doanh nghiệp: biến ảnh thư tay thành đường bút cho robot, chạy trên máy chủ thường.
Số được phép nêu: "F1 đường tâm 94,88% trên 220 ảnh tổng hợp từ 22 ảnh quét thật". Không nói "độ chính xác 95%" hay "tái tạo chính xác nét chữ".

**6. OT-2.**
Kỹ thuật: số hoá bộ glyph cá nhân từ phiếu mẫu có mốc định vị, ghép lại bằng cùng bộ dàn trang của OT-3, dấu lấy từ chính người viết.
Doanh nghiệp: hướng phát triển cho dịch vụ "viết bằng nét chữ của bạn"; đã có code, chưa mở cho khách, chưa đo trên người thật.
Không nói: "AI học nét chữ", "sinh chữ viết tay bằng AI".

### Các câu khẳng định chưa được phép dùng

| Câu | Vì sao chưa được | Cách đo để dùng được |
|---|---|---|
| "Độ chính xác X%" | Chỉ có F1 trên ảnh tổng hợp | Tập giữ lại 10–20 ảnh thật có mặt nạ vẽ tay |
| "Sai lệch ≤ 0,5 mm" (NFR-04) | Chưa có bản viết thật để đo | Service G trên ảnh bản viết thật + đối chiếu thước |
| "Giảm thời gian viết 38%" | Con số là quãng nhấc bút trên giấy ảo | So thời gian hai lần chạy trên robot |
| "Điều khiển lực vòng kín" | Lực do lò xo thụ động, cảm biến chưa nối | Nối Hall + ESP32, ghi log lực |
| "Tự động hoàn toàn" | Hiệu chuẩn, đặt giấy, chụp ảnh, hoàn tiền đều do người | Không nên nói |
| "Robot đã viết sản phẩm hoàn chỉnh" | Mới 2 nét | Một lần viết trọn trang có video + log |
