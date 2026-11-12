# Nâng cấp AI phục dựng chữ viết tay và robot viết: audit, thiết kế, lộ trình

Phiên bản 1, 2026-11-12. Viết theo "MASTER PROMPT: END-TO-END AI HANDWRITING RESTORATION & ROBOTIC REPRODUCTION UPGRADE" của chủ dự án.
Tài liệu này là **Phase 0 (audit AS-IS)** và **Phase 1 (gap analysis + thiết kế)**, kèm **lộ trình** và **các quyết định cần chủ dự án chốt**.
Mọi con số trong tài liệu là số đo hoặc số đọc từ code. Những gì chưa đo được ghi rõ "chưa đo", không đoán.

Phạm vi sửa code của AI theo `BE/CLAUDE.md`: chỉ `BE/` và `robot_agent/`. `FE/` và `DesktopApp/` (trước là `Mobile/`) do người khác làm, nên tài liệu chỉ ghi API và hướng dẫn tích hợp cho hai phần đó.

---

## 1. Hiện trạng (AS-IS)

### 1.1 Kiến trúc

```
FE (React 19, Vercel) ─┐
DesktopApp (Flutter) ──┼──> BE FastAPI (Render) ──> Supabase Postgres + Storage
                       │        │  stroke_ai (OpenCV, Hershey, outline font)   ← sinh phác thảo, chạy trong BE
                       │        │  motion (plan, validate)                       ← kiểm lại quỹ đạo phía server
                       │        └─ /agent/sync (agent gọi ra, lệnh bền)
robot_agent (máy trạm) ───────────> FAIRINO SDK ──> FR3 + gripper JODELL EPG40-050 + lò xo + Hall + ESP32
```

### 1.2 Chức năng liên quan đến đợt nâng cấp

| Thành phần | Có gì | Mức độ | Kiểm thử |
|---|---|---|---|
| Phục dựng nét từ ảnh (OT-1) | `stroke_ai/recovery.py` (493 dòng): làm phẳng sáng + Otsu, khử nghiêng ±5°, Zhang-Suen thinning, đồ thị skeleton, nối nét qua giao điểm theo hướng, sắp thứ tự đọc, dấu thanh viết sau chữ, IoU pixel | Chạy thật trong BE, **thị giác máy cổ điển, không có mô hình học**, không có OCR/HTR | Test tự động trên ảnh tổng hợp. **NFR-02 (IoU ≥ 80 % trên bộ ảnh thật) chưa đo**, chưa có bộ ảnh chữ viết tay tiếng Việt |
| Soạn văn bản theo mẫu (OT-3) | `text_to_stroke.py`, `styled_text.py`, `outline_font.py`, `domain/text_layout.py`: font Hershey 1 nét + font outline, cỡ chữ theo đoạn, nghiêng, gạch chân, gạch đôi, gạch ngang, giãn dòng, lề 4 phía, căn dọc, nhiều trang; `GET .../capabilities` mô tả thuộc tính nào làm được | Chạy thật | Có test (`test_text_layout.py`, `test_api_text_styles*.py`) |
| Tách lớp dữ liệu | Ngữ nghĩa: `order_inputs.text_content` + `layout` (JSON). Hình ảnh: PNG/JPG preview. Nét: `trajectory.json` trên Storage. Quỹ đạo robot: agent tự lập (`runner.plan_page`) từ nét + hiệu chuẩn | **Đã tách đủ 4 lớp cho OT-3.** OT-1 chỉ có lớp nét (không có lớp chữ/vùng) | |
| Phiên bản phác thảo | `sketches` (version, `is_final` duy nhất, `content_hash` SHA-256 của JSON quỹ đạo, độ tương đồng, thời gian viết ước tính) | Staff tạo; chỉ sửa được khi đơn `ACCEPTED` | Có test |
| Editor nét cho Staff | FE `pages/staff/SketchEditor.tsx` gửi quỹ đạo đã sửa (`create_manual`) | Có | FE |
| Khách tương tác AI | **Không có.** Khách chỉ tạo đơn, tải ảnh hoặc gõ chữ, vẽ canvas; Staff sinh phác thảo sau khi tiếp nhận | Thiếu | |
| LLM / VLM | **Không có** trong BE, FE, agent (không có thư viện, không có khoá) | Thiếu | |
| Duyệt | Khách duyệt **báo giá**; báo giá gắn `sketch_id`, nên duyệt báo giá = duyệt đúng phiên bản phác thảo. Không có ghi chú lên phác thảo, không so sánh phiên bản | Có một phần | Có test |
| Khoá sau cọc | Cọc xác nhận bằng webhook ký (VNPay, MoMo, payOS, MOCK), idempotent. Sau `ACCEPTED` không sửa phác thảo được. Job lưu `package_hash = sketch.content_hash`; BE kiểm hash khi tải gói và khi bắt đầu viết (MSG14); agent băm lại file tải về | Có, nhưng xem 1.3 | Có test |
| Watermark, provenance | **Không có** | Thiếu | |
| Vật tư | Giấy: mã, tên, gsm, bề mặt, khổ, giá, tồn. Bút: loại, độ rộng nét, dải lực F_target/min/max/hard (BR-20), v_max, phụ phí, tồn. Mực: tên, mã màu hex, theo bút. Tương thích giấy–bút | Có | Có test |
| Preview | `render_image.py`: màu mực hex + độ rộng nét bút + bề mặt giấy | "Visual preview", **chưa hiệu chuẩn** theo vật liệu thật | |
| Motion planning | `services/motion` (BE) + agent: lấy mẫu lại theo cung, giữ góc, độ cong, **profile tốc độ giới hạn gia tốc ngang/dọc**, khung giấy từ 3–9 điểm dò, kiểm hộp làm việc; agent chạy `movel` đoạn ≤ 5 mm | Chạy thật | Có test; server kiểm lại mô phỏng |
| Mô phỏng | `sim.py`, `sim_pybullet.py`, trang 3D; LOAD → PREFLIGHT → kết quả mô phỏng gửi BE | Mô phỏng hình học | Có test |
| Robot thật | FR3 V6.0, controller V3.8.25-QX. **Đã chạy thật:** pen-up 45/45 nét (489 s), viết thật hai nét đầu (2026-10-25), đo TCP 260,63 mm (2026-10-31) | Chưa hiệu chuẩn vật lý đầy đủ | NFR-03/04/05 **chưa đo** |
| Lực / đậm nhạt | `gripper.py`: giao thức ESP32 100 Hz, bảng Hall→mN, từ chối viết khi chưa hiệu chuẩn, không ngoại suy | Code có, **bảng hiệu chuẩn chưa đo** | Test giao thức |
| QC (Service G) | `quality_eval.py`: tìm tờ giấy, làm phẳng, căn chỉnh, đo coverage, extra ink, Chamfer, HD95, Hausdorff (mm) | Có; **ngưỡng chưa kiểm chứng**, chưa hiệu chuẩn mm bằng thước | Có test |
| Chặn giả mạo | BR-23 / LI-12: không nhận chữ ký, giấy tờ pháp lý, văn bản giả mạo. Staff từ chối thủ công | Chính sách, chưa có hỗ trợ tự động | |

Toàn suite BE: 779 test, lần gần nhất 776 passed, 3 skipped trên Supabase thật (2026-11-11).

### 1.3 Bất cập phát hiện khi audit

| # | Bất cập | Hậu quả | Mức |
|---|---|---|---|
| A1 | `content_hash` là SHA-256 **không khoá** của riêng file quỹ đạo, và agent nhận hash qua cùng kênh với file | Hash chỉ chứng minh toàn vẹn, không chứng minh nguồn phát hành. Ai sửa được cả DB lẫn Storage thì hash vẫn khớp | Cao |
| A2 | Gói job không chứa thông số vật tư. Agent và validator đọc bút (v_max, dải lực) **sống** từ catalog lúc chạy | Manager sửa thông số bút sau khi khách cọc sẽ âm thầm đổi cách viết của job đã khoá | Cao |
| A3 | Không có bản ghi "khách duyệt phiên bản X" riêng; chỉ suy ra từ báo giá `APPROVED` | Khó chứng minh khách đã thấy đúng ảnh nào, đúng cấu hình nào | Trung bình |
| A4 | OT-1 không đánh dấu vùng không chắc chắn, không phân biệt nét gốc / nét khôi phục / nét suy đoán | Không đáp ứng yêu cầu Faithful vs Assisted | Cao (cho tính năng mới) |
| A5 | Không có watermark, mã sản phẩm, xác thực | Thành phẩm có thể bị dùng như bản gốc | Cao (cho tính năng mới) |
| A6 | Preview không phân biệt visual / calibrated / production-ready | Khách có thể hiểu preview là y hệt thành phẩm | Trung bình |
| A7 | Độ đậm nhạt: robot không có kênh điều khiển lực theo nét (lực cố định theo bút) | Không thể hiện được nét nhấn | Phụ thuộc phần cứng |
| A8 | NFR-02/03/04/05 chưa có số đo | Không thể tuyên bố độ chính xác | Phụ thuộc dữ liệu thật / robot thật |

---

## 2. Bảng truy vết yêu cầu (rút gọn)

Phân loại: **MUST** (làm ngay, không cần quyết định thêm), **MUST-D** (bắt buộc nhưng chờ quyết định), **SHOULD**, **RESEARCH**, **HW** (phụ thuộc phần cứng / robot thật).

| Yêu cầu (phần của master prompt) | Đã có | Thiếu | Loại |
|---|---|---|---|
| II. AI Assistant cho khách, tool calling, chỉnh theo vùng | Không | Toàn bộ | MUST-D (chọn LLM, khoá API, chi phí) |
| II. Lựa chọn mô hình | Không | Ma trận + benchmark | RESEARCH (mục 4) |
| III-A. Editor như Word, capability-aware | Phần lớn (OT-3, `capabilities`) | Giãn ký tự, khoảng cách đoạn, hướng giấy, khung viết, undo/redo phía BE (bản nháp có phiên bản) | SHOULD |
| III-B. Phục dựng Faithful / Assisted, vùng không chắc chắn | Phục dựng cổ điển | Mô hình vùng (region), độ tin cậy, nhãn nguồn gốc nét, chế độ | MUST (phần dữ liệu), RESEARCH (mô hình) |
| III-C. Bộ đánh giá định lượng | IoU, Chamfer, HD95 (QC) | Bộ dữ liệu tiếng Việt thật, CER/WER, SSIM, endpoint, topology | MUST (công cụ), cần dữ liệu thật từ chủ dự án |
| IV. Workflow Customer→AI→Staff→Customer→Cọc→Khoá | Staff→Customer→Cọc→Job | Bản nháp do khách + AI làm trước khi gửi; ghi chú lên phác thảo; giới hạn vòng sửa | MUST-D (đổi nghiệp vụ lớn) |
| IV.4 / VI. Snapshot bất biến + chữ ký | Hash SHA-256 không khoá | Snapshot chuẩn hoá có vật tư + báo giá + duyệt, **chữ ký số**, agent xác minh bằng khoá công khai, sự cố khi lệch | **MUST, làm ngay** |
| V. Watermark preview / file xuất | Không | Dấu trên ảnh preview, PDF, ảnh khách xem | MUST |
| V. Watermark vật lý trên giấy | Không | Robot viết dấu ở lề + mã sản phẩm | MUST-D (đổi sản phẩm giao khách) |
| V.2 Provenance, QR, chứng nhận | Audit log | Mã sản phẩm, trang xác thực công khai, chứng nhận | SHOULD (sau snapshot) |
| VII. Vật tư chi tiết + trạng thái hiệu chuẩn | Trường cơ bản | Trường mở rộng có nguồn (bắt buộc / nhà cung cấp / đo), profile tổ hợp giấy+bút+mực | SHOULD |
| VII.4 3 cấp preview | 1 cấp | Nhãn cấp preview | MUST (nhãn), HW (cấp calibrated) |
| VIII. Robot engine | Có nền tảng tốt | Tối ưu thứ tự nét + đường pen-up (TSP), benchmark thời gian, giới hạn jerk | SHOULD (phần mềm), HW (đo thật) |
| IX. Đậm nhạt | Giao thức lực | Mô hình độ rộng nét theo lực/tốc độ, hiệu chuẩn | RESEARCH + HW |
| XI. Edge case | Nhiều (MSG14, idempotent webhook, khoá dòng) | Xem mục 7 | Theo từng phase |

---

## 3. Thiết kế đích (TO-BE)

### 3.1 Quy trình

```
Khách ──(1) chọn cách: soạn văn bản | phục dựng ảnh──> STUDIO (bản nháp, chưa là đơn)
   │       AI Assistant: hỏi, phân tích, gọi công cụ xác định, sinh bản nháp, sửa theo vùng, undo/redo
   └─(2) "Gửi xưởng" ──> đơn SUBMITTED kèm bản nháp + lịch sử + vùng không chắc chắn   ← từ đây là quy trình hiện có
Staff ──(3) tiếp nhận, sửa nét / sửa chữ / xử lý vùng, ghi chú ──> phiên bản phác thảo + báo giá
Khách ──(4) duyệt đúng phiên bản (so sánh, ghi chú) | yêu cầu sửa (tối đa N vòng miễn phí) ──> lặp (3)
Hệ thống ──(5) khách duyệt báo giá ⇒ ghi bản duyệt (phiên bản, hash ảnh khách đã xem, cấu hình vật tư)
Cổng thanh toán ──(6) webhook ký xác nhận cọc ⇒ CONFIRMED ⇒ TẠO PRODUCTION SNAPSHOT + CHỮ KÝ
Manager ──(7) xếp lịch: job trỏ tới snapshot (không trỏ thẳng file quỹ đạo nữa)
Kỹ thuật viên / agent ──(8) tải gói, xác minh chữ ký + hash + trạng thái, mô phỏng, viết, QC
```

Quyết định thiết kế: **studio là lớp mới đứng trước đơn hàng**, từ bước (2) trở đi giữ nguyên máy trạng thái đơn hiện có. Lý do: không phá 779 test và các luồng thanh toán, hoàn tiền, ETA, lịch đang chạy.

### 3.2 Kiến trúc AI

```
Khách ⇄ API /studio/{id}/messages ⇄ Orchestrator (LLM, tool calling, có giới hạn lượt gọi)
                                         │ chỉ được gọi các công cụ sau, mọi kết quả là dữ liệu có cấu trúc:
                                         ├─ analyze_image(input_id)        → chất lượng ảnh (FR-33, code có sẵn)
                                         ├─ transcribe(region)             → HTR/VLM: văn bản + độ tin cậy, KHÔNG sinh nét
                                         ├─ recover_strokes(region|page)   → recovery.py (xác định)
                                         ├─ compose_text(doc, layout)      → styled_text.py (xác định)
                                         ├─ edit_region(target, change)    → sửa đúng vùng, các vùng khác giữ nguyên byte
                                         ├─ list_materials(filter)         → đọc catalog thật (không bịa vật tư)
                                         ├─ check_feasibility(draft, mats) → capabilities + tương thích + khổ giấy
                                         └─ render_preview(draft, mats)    → render_image.py + watermark
```

Nguyên tắc: LLM hiểu ý và chọn công cụ; **hình học nét chỉ do công cụ xác định sinh ra**; LLM không bao giờ trả toạ độ robot. Mọi lần gọi mô hình được ghi lại (mô hình, phiên bản, token, thời gian, đầu vào đã băm) để truy vết và tính chi phí.

### 3.3 Mô hình dữ liệu đề xuất (chỉ thêm, không sửa bảng cũ)

| Bảng | Mục đích | Phase |
|---|---|---|
| `production_snapshots` | Snapshot bất biến: payload chuẩn hoá (JSON), `sha256`, `signature`, `key_id`, `sketch_id`, `quotation_id`, `payment_id`, phiên bản schema | U1 |
| cột `production_jobs.snapshot_id` | Job trỏ tới snapshot | U1 |
| `security_incidents` hoặc dùng `incidents` có sẵn | Ghi khi chữ ký / hash lệch | U1 (dùng lại nếu đủ) |
| `sketch_approvals` | Khách duyệt phiên bản nào, hash ảnh đã xem, lúc nào, IP | U2 |
| `sketch_regions` | Vùng trên trang: hộp, văn bản nhận diện, độ tin cậy, nhãn `ORIGINAL` / `RESTORED` / `INFERRED`, người sửa | U4 |
| `studio_drafts`, `studio_revisions` | Bản nháp của khách trước khi thành đơn, mỗi lần sửa là một revision (undo/redo = đổi con trỏ revision) | U5 |
| `ai_sessions`, `ai_messages`, `ai_tool_calls` | Hội thoại, lần gọi công cụ, mô hình, chi phí | U5 |
| `material_profiles` | Profile tổ hợp giấy+bút+mực(+robot): độ rộng nét đo được, độ đậm, lem, trạng thái hiệu chuẩn, nguồn dữ liệu | U6 |
| cột mở rộng của `paper_types`, `pen_types`, `ink_colors` | Trường mới, đều cho phép NULL, kèm cột nguồn dữ liệu | U6 |
| `qc_measurements` (hoặc mở rộng `quality_evaluations` có sẵn) | Số đo QC theo snapshot | U8 |

### 3.4 Thiết kế bảo mật gói sản xuất (làm ngay ở U1)

- **Chuẩn hoá:** JSON khoá sắp xếp, không khoảng trắng, số thập phân dạng chuỗi cố định, UTF-8 (`canonical_json`). Hash ổn định giữa Python BE và agent.
- **Nội dung snapshot:** id + phiên bản sketch, `content_hash` quỹ đạo, các trang (khổ, hướng, kích thước mm), giấy / bút / mực **chép giá trị** (không chỉ id): gsm, bề mặt, khổ, độ rộng nét, dải lực, v_max, mã màu; id + tổng tiền báo giá đã duyệt + thời điểm khách duyệt; id thanh toán cọc đã xác nhận; watermark (khi có); `engine` sinh quỹ đạo; `schema_version`; `package_id` (UUID); thời điểm phát hành.
- **Chữ ký: Ed25519** (chữ ký số bất đối xứng), không dùng HMAC. Lý do: agent ở máy trạm chỉ cần **khoá công khai** để xác minh; nếu dùng HMAC thì agent phải giữ bí mật có thể dùng để **tự ký gói giả**. Khoá bí mật chỉ ở BE (biến môi trường `PRODUCTION_SIGNING_KEY`), có `key_id` để xoay khoá: khoá cũ còn trong danh sách xác minh `PRODUCTION_VERIFY_KEYS` cho tới khi hết job dùng nó.
- **Thư viện:** `cryptography` (thêm vào `requirements.txt`; hiện chưa cài).
- **Kiểm tra trước khi viết (BE):** chữ ký hợp lệ với `key_id`; hash payload khớp; `content_hash` file quỹ đạo khớp payload; đơn vẫn `CONFIRMED`, cọc vẫn hợp lệ; vật tư trong catalog hiện tại **khác** snapshot thì không âm thầm dùng giá trị mới: job dùng giá trị trong snapshot và báo cảnh báo cho kỹ thuật viên.
- **Kiểm tra lại ở agent:** agent xác minh chữ ký bằng khoá công khai trước LOAD; sai thì từ chối, gửi sự kiện `HASH_MISMATCH` (có sẵn), không có cờ bỏ qua.
- **Chống replay / trùng / cũ:** `package_id` duy nhất; job chỉ chạy snapshot đúng `snapshot_id` của nó; snapshot thuộc đơn đã huỷ hoặc job đã `DONE` bị từ chối; đơn vẫn chỉ có một job đang chạy (ràng buộc có sẵn).
- **Đơn cũ:** job tạo trước U1 không có snapshot. Giữ luồng cũ cho chúng (hash SHA-256 như hiện nay), có nhãn `legacy`, để không chặn các job đang dở.

### 3.5 Watermark

| Nơi | Cách | Phụ thuộc quyết định |
|---|---|---|
| Ảnh preview, JPG khách xem, PDF báo giá | Dòng chữ chéo mờ + dải chân trang "AI-VHRS · Tái tạo bằng AI · Không phải bản gốc · mã" vẽ khi render, không lưu vào lớp nét | Không (làm ở U2) |
| Phác thảo đã chốt | Watermark là một phần của snapshot (văn bản + vị trí + nét), nên nằm trong chữ ký | Không |
| Thành phẩm giấy | Robot viết dòng nhỏ ở lề dưới (ngoài vùng nội dung, nét Hershey 1 nét, khoảng 2,5 mm): "Tái tạo bằng AI-VHRS · Mã XXXX-XXXX". Thêm thẻ chứng nhận in riêng có QR tới trang xác thực công khai | **Có** (đổi sản phẩm giao khách, xem câu hỏi Q3) |

Robot vẽ QR bằng bút là khả thi về hình học nhưng dễ hỏng khi mực lem, và tốn thời gian; nên QR in trên thẻ chứng nhận, không viết bằng robot.

### 3.6 Robot writing engine

Giữ kiến trúc hiện có (đã đúng hướng: quỹ đạo xác định, server kiểm lại, agent mô phỏng trước). Việc nên làm, theo thứ tự lợi ích / rủi ro:

1. **Thứ tự nét và đường pen-up:** giữ thứ tự trong một chữ (thứ tự viết có ý nghĩa với dấu tiếng Việt), tối ưu thứ tự **giữa các cụm** bằng nearest-neighbour + 2-opt, cho phép đảo chiều nét chỉ khi nét không có chiều bắt buộc. Đo trước/sau: tổng quãng pen-up (mm), thời gian ước tính. Toàn phần mềm, đo được ngay bằng mô phỏng.
2. **Giới hạn jerk** (profile S-curve) trong `speed_profile`: giảm rung ở chỗ đổi tốc độ. Phải đo trên robot thật mới biết hiệu quả (HW).
3. **Nối đoạn `movel`:** lệnh hiện tại ≤ 5 mm, controller dừng giữa các đoạn. Cần đọc tài liệu SDK FAIRINO về blending trước khi đổi; **không tự bịa API** (HW + đọc tài liệu).
4. ROS 2 / MoveIt 2: **không đề xuất** lúc này. Bài toán là viết trên mặt phẳng trong hộp làm việc cố định, IK do controller FR3 giải; thêm ROS tăng độ phức tạp vận hành mà không giải quyết đúng điểm nghẽn hiện tại (dừng giữa đoạn, hiệu chuẩn).

### 3.7 Đậm nhạt (nghiên cứu)

- Phân biệt: **độ rộng nét** (hình học, phụ thuộc đầu bút + lực + góc), **độ đậm quang học** (đo từ ảnh), **màu mực**, **độ dày lớp mực**, **lực nhấn**. Với bút bi / gel / fineliner, lực đổi độ rộng nét rất ít; muốn đậm nhạt rõ cần bút có ngòi biến thiên (bút lông, bút máy ngòi mềm, brush pen).
- Phần cứng hiện có: lò xo + Hall cho **ước lượng** lực qua bảng hiệu chuẩn; tay FR3 đổi lực bằng cách đổi độ nén lò xo (dịch trục Z). Đây là điều khiển vòng hở theo vị trí, sai số phụ thuộc độ phẳng giấy và độ cứng lò xo.
- Phương án theo thứ tự: (a) phần mềm: mỗi nét có trường `width_hint` (từ ảnh gốc ở OT-1), bản đồ width → độ nén Z qua bảng hiệu chuẩn; (b) phần cứng hiện có: đo bảng Hall→N và bảng (lực, tốc độ) → độ rộng nét trên từng tổ hợp vật liệu (thí nghiệm có người vận hành); (c) nâng cấp: cảm biến lực tải trọng nhỏ ở đầu bút hoặc trục Z có lò xo tuyến tính đo được. Chi phí phần cứng chưa báo giá được, cần chủ dự án hỏi nhà cung cấp.
- Mọi thí nghiệm robot thật phải có người vận hành xác nhận và mã `AUTHORIZE-…`.

---

## 4. Lựa chọn mô hình AI

**Lưu ý trung thực:** AI viết tài liệu này **chưa chạy benchmark** nào trên chữ viết tay tiếng Việt. Bảng dưới là ứng viên và lý do chọn, **không phải kết quả đo**. Phase U3 sẽ dựng bộ dữ liệu và đo thật trước khi chốt.

| Vai trò | Ứng viên chính | Dự phòng / tối ưu chi phí | Ghi chú |
|---|---|---|---|
| Hội thoại + tool calling | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Claude Haiku 5.5 (`claude-haiku-5-5`) cho các lượt đơn giản; GPT / Gemini tương đương nếu chủ dự án muốn | Cần khoá API (Q1). Gọi qua HTTP từ BE, không gửi ảnh gốc khi không cần |
| Hiểu ảnh tài liệu (VLM) | Cùng mô hình hội thoại (có vision): mô tả bố cục, gợi ý vùng mờ | Không gọi VLM, chỉ dùng chất lượng ảnh FR-33 | VLM **không** sinh nét, chỉ gợi ý |
| HTR tiếng Việt | Đề cử thử: VietOCR (mã nguồn mở, có mô hình tiếng Việt), TrOCR tinh chỉnh, và VLM đọc chữ | Không HTR: Staff gõ lại nội dung | Phải benchmark CER/WER và **độ chính xác dấu** trên bộ ảnh thật. HTR chỉ gán nhãn chữ cho vùng; nét vẫn lấy từ ảnh gốc |
| Làm rõ ảnh | Pipeline cổ điển hiện có (làm phẳng sáng, khử nghiêng, khử nhiễu) | Mô hình học khử nhiễu tài liệu (nghiên cứu) | Ưu tiên không "làm đẹp" nét gốc |
| Trích nét | `recovery.py` hiện có | Mô hình học khôi phục thứ tự nét (nghiên cứu) | Giữ cổ điển vì xác định, giải thích được |
| Chất lượng | IoU, Chamfer, HD95 (có), thêm SSIM, endpoint error, topology (số nét, số giao điểm), CER | | Xem 4.1 |

### 4.1 Chỉ số theo giai đoạn

| Giai đoạn | Chỉ số | Vì sao |
|---|---|---|
| Nhận diện chữ | CER, WER, tỉ lệ đúng dấu thanh | Đúng nội dung, **không** nói gì về nét |
| Phục dựng nét (ảnh gốc ↔ nét) | IoU (NFR-02), Chamfer, HD95, topology | Nét có trùng mực gốc không |
| Bố cục | Sai lệch vị trí dòng / chữ (mm) | Giữ bố cục gốc |
| Thành phẩm (phác thảo ↔ ảnh giấy) | Coverage, extra ink, Chamfer, HD95, endpoint (mm, NFR-04 ≤ 0,5 mm) | Robot viết đúng phác thảo |
| Cảm nhận | Đánh giá người (thang 1–5, người thân nhận ra nét chữ) | Không có chỉ số máy nào thay được |

---

## 5. Lộ trình triển khai

Mỗi phase: code + test + chạy toàn suite trên Supabase + cập nhật `PROJECT_STATUS.md`, `FE_API_GUIDE.md`. Thứ tự ưu tiên phần **không cần quyết định và không cần robot thật** trước, khác thứ tự đề xuất của CodeX ở chỗ: khoá snapshot đứng đầu (nó bảo vệ mọi phase sau và không phụ thuộc LLM).

| Phase | Nội dung | Phụ thuộc | Tiêu chí nghiệm thu |
|---|---|---|---|
| **U1** ✅ code + test (2026-11-12, commit `9c29ee1`) | Production snapshot + chữ ký Ed25519; job trỏ snapshot; kiểm tra khi tải gói / bắt đầu viết; agent xác minh; sự cố khi lệch; job cũ chạy luồng legacy | Không | Test: sửa 1 byte quỹ đạo / đổi thông số bút / chữ ký khoá lạ / replay snapshot đơn khác → đều bị từ chối và ghi sự cố; job cũ vẫn chạy |
| **U2** ✅ code + test (2026-11-12, commit `b200e4b`; so sánh phiên bản chưa làm) | Watermark preview + file xuất; bản ghi duyệt phiên bản (`sketch_approvals`); so sánh phiên bản; lý do báo giá lại (Q4 thay cho giới hạn vòng sửa) | Q4 (số vòng) cho phần giới hạn | Ảnh khách xem luôn có dấu; duyệt báo giá ghi đúng phiên bản + hash ảnh |
| **U3** ✅ đợt 1 (2026-11-12, chưa commit; báo cáo `docs/benchmarks/U3_recovery_viet_hw_2026-11-12.md`) | Bộ đánh giá: công cụ đo (topology, endpoint, vùng / từ, dấu, độ nhạy mực mờ; SSIM bỏ vì cần căn ảnh, CER chờ nhận dạng chữ) + cấu trúc bộ dữ liệu + báo cáo; chạy trên 50 ảnh **thật** | Q5 (dữ liệu) | Báo cáo số đo thật, không số giả |
| **U4** ✅ code + test (2026-11-12, commit `766b89a`; HTR chưa có) | Vùng phục dựng: `sketch_regions`, nhãn ORIGINAL / RESTORED / INFERRED, chế độ Faithful / Assisted, Staff sửa theo vùng, sửa chữ không đụng vùng khác | Không (HTR thêm sau) | Sửa vùng 3 không đổi byte nét của vùng khác |
| **U5** | Studio + AI Assistant: bản nháp trước khi gửi xưởng, revision + undo/redo, hội thoại, tool calling, ghi chi phí | **Q1** (LLM, khoá), **Q2** (nghiệp vụ studio) | Kịch bản hội thoại mẫu chạy với công cụ thật; LLM không bịa vật tư (test bằng catalog) |
| **U6** ✅ code (2026-11-12, migration 0019, chưa commit) | Vật tư mở rộng + profile tổ hợp + nhãn cấp preview | Không (đo thật là HW) | Manager nhập được, trường đo được ghi nguồn |
| **U7** | Robot engine: tối ưu thứ tự nét + pen-up, jerk limit, benchmark mô phỏng | Không (đo thật là HW) | Quãng pen-up / thời gian giảm, đo bằng mô phỏng trên bộ phác thảo mẫu |
| **U8** | Watermark vật lý + chứng nhận + trang xác thực QR | **Q3** | Snapshot có watermark; agent từ chối gói thiếu watermark bắt buộc |
| **U9** | Đậm nhạt + hiệu chuẩn vật liệu + QC trên robot thật | **HW**, người vận hành | Số đo NFR-04/05 thật |

---

## 6. Câu hỏi cần chủ dự án quyết định

**Đã chốt ngày 2026-11-12:**
- Q1: dùng **nhiều nhà cung cấp** (Claude, ChatGPT, Gemini), tự chuyển khi một bên lỗi hoặc hết quota để khách không bị bỏ lửng. Cách làm: thứ tự ưu tiên cố định, mỗi phiên hội thoại giữ một nhà cung cấp trừ khi nó lỗi, mọi hình học nét và dữ liệu vật tư do công cụ xác định tạo ra (chất lượng bản nháp không phụ thuộc model nào trả lời), cùng một bộ kịch bản kiểm thử chạy trên mọi nhà cung cấp. Mỗi nhà cung cấp một tài khoản (dùng nhiều tài khoản để lách giới hạn có thể vi phạm điều khoản). Khoá API chưa có.
- Q2: phương án A (studio là lớp mới trước đơn).
- Q3: phương án A (dòng ở lề dưới + thẻ chứng nhận có QR; bắt buộc OT-1, tuỳ chọn OT-3).
- Q4: **không giới hạn vòng miễn phí**; mỗi lần khách yêu cầu sửa, Staff lập báo giá mới kèm **lý do giá thay đổi** (giá có thể giữ nguyên). U2 thêm trường lý do thay cho bộ đếm vòng.
- Q5 (một phần, 2026-11-12): chủ dự án đưa bộ `5CD-AI/Viet-Handwriting-gemini-VQA` (Hugging Face, ảnh UIT-HWDB + Cinnamon, có văn bản chuẩn, không có quỹ đạo bút, giấy phép chưa ghi). Dùng 50 ảnh để đo nội bộ, ảnh không vào repo. Vẫn thiếu: ảnh hư hại thật (giấy cũ, mực phai) và dữ liệu có quỹ đạo bút để đo thứ tự / chiều nét.


**Q1. Nhà cung cấp LLM cho AI Assistant**
- Vấn đề: chưa có LLM nào trong hệ thống; cần khoá API và chấp nhận chi phí theo lượt gọi.
- Ảnh hưởng: chọn sai thì đổi lại tốn công (mọi công cụ viết theo một giao diện chung nên đổi được, nhưng prompt và kiểm thử phải làm lại).
- A. Anthropic Claude (Sonnet 5.5 chính, Haiku 5.5 cho lượt rẻ). Ưu: tool calling và đọc ảnh tốt, một nhà cung cấp cho cả chat + vision. Nhược: tốn phí theo token, ảnh khách đi ra bên ngoài.
- B. OpenAI hoặc Google Gemini. Tương tự A, khác nhà cung cấp.
- C. Chưa dùng LLM: studio chạy bằng form + công cụ xác định, thêm LLM sau. Ưu: không tốn phí, không gửi dữ liệu ra ngoài. Nhược: không có hội thoại tự nhiên.
- Khuyến nghị: A, nhưng làm giao diện `LlmProvider` để đổi được; bật cờ `AI_ASSISTANT_MODE=off|mock|live` (giống cổng thanh toán) để dev/test không tốn tiền. Chi phí thật phụ thuộc số lượt chat; AI sẽ đo token thực tế ở chế độ live trước khi ước tính, không đoán.
- Cần chốt: nhà cung cấp, và ai tạo khoá API (đặt vào biến môi trường `LLM_API_KEY` trên Render, không vào repo).

**Q2. Studio trước khi gửi xưởng có đổi nghiệp vụ không?**
- Vấn đề: hiện Staff sinh phác thảo sau khi tiếp nhận. Yêu cầu mới: khách + AI làm bản nháp trước.
- A. Studio là lớp mới **trước** đơn; gửi studio = tạo đơn `SUBMITTED` kèm bản nháp. Staff vẫn làm phác thảo chính thức. Ưu: không đổi máy trạng thái đơn, không phá luồng tiền. Nhược: hai nơi có "phác thảo" (nháp của khách, phiên bản của Staff).
- B. Đổi máy trạng thái đơn, thêm trạng thái `DRAFTING_WITH_AI`. Nhược: đụng mọi luồng và test hiện có.
- Khuyến nghị: A.
- Cần chốt: A hay B.

**Q3. Watermark vật lý trên thành phẩm**
- Vấn đề: robot viết thêm dấu lên giấy giao khách là đổi sản phẩm.
- A. Dòng nhỏ ở lề dưới mỗi tờ + thẻ chứng nhận in riêng có QR. Ưu: khó tách khỏi tờ hơn thẻ rời, không đè nội dung. Nhược: có thể bị cắt lề.
- B. Chỉ thẻ chứng nhận + QR, không viết lên tờ. Ưu: tờ sạch. Nhược: tách rời được dễ dàng.
- C. Dấu nằm trong vùng nội dung (chéo, mờ). Robot viết bằng bút thì không "mờ" được, sẽ đè lên chữ; không khuyến nghị.
- Khuyến nghị: A, bắt buộc với OT-1 (phục dựng chữ người thật), tuỳ chọn với OT-3.
- Cần chốt: A / B, nội dung dòng chữ, có áp cho OT-3 không.

**Q4. Giới hạn vòng sửa**
- Vấn đề: vòng khách ↔ Staff không có giới hạn.
- Khuyến nghị: 3 vòng miễn phí; vòng thứ 4 trở đi Staff được phép báo giá lại (thay đổi ảnh hưởng giá / vật tư / thời gian luôn phải báo giá lại, bất kể vòng).
- Cần chốt: số vòng.

**Q5. Dữ liệu đánh giá phục dựng**
- Vấn đề: không có ảnh chữ viết tay tiếng Việt thật để đo NFR-02; AI không được tự tạo kết quả.
- Khuyến nghị: chủ dự án gom 30–50 ảnh thật (có sự đồng ý của người viết), mỗi ảnh có nội dung gõ lại đúng; một phần là ảnh cũ / mờ. Lưu ngoài repo (dữ liệu cá nhân).
- Cần chốt: có cung cấp được không, và nơi lưu.

---

## 7. Edge case và cách xử lý (rút gọn)

| Tình huống | Xử lý | Phase |
|---|---|---|
| Khách duyệt phiên bản cũ (tab cũ) | Duyệt gửi kèm `sketch_id`; khác phác thảo của báo giá đang mở → `409 SKETCH_VERSION_STALE`; bản ghi duyệt lưu hash | U2 ✅ (`sketch_id` tuỳ chọn để app cũ không gãy) |
| Webhook cọc gửi nhiều lần | Đã idempotent; snapshot tạo trong cùng giao dịch, ràng buộc duy nhất theo đơn + sketch | U1 |
| Manager sửa thông số bút sau khi khoá | Job dùng giá trị trong snapshot; cảnh báo kỹ thuật viên có khác biệt | U1 |
| Gói job bị sửa / tải nhầm phiên bản | Chữ ký + hash + `snapshot_id` của job; lệch → từ chối + sự cố | U1 |
| Replay gói của đơn khác | Payload chứa `order_id`, `job` chỉ nhận snapshot của chính nó | U1 |
| Đơn huỷ / hoàn tiền sau khi có snapshot | Snapshot bị thu hồi (`revoked_at`), agent từ chối | U1 |
| Khách đòi sửa sau cọc | Theo BR hiện có: huỷ sau cọc (4d-1) hoặc Staff tạo phiên bản mới + báo giá mới + snapshot mới; snapshot cũ thu hồi | U2 |
| Hai Staff sửa cùng phác thảo | Khoá dòng đơn (có sẵn) + chỉ sửa vùng trên phiên bản mới nhất (`409 SKETCH_VERSION_CONFLICT`) | U4 ✅ |
| AI nhận sai chữ / vùng mất chữ | Vùng có độ tin cậy thấp → nhãn RESTORED; FAITHFUL chặn INFERRED cả khi sửa lẫn khi chốt. Giới hạn: mực mất hẳn không sinh nét nên không có vùng, Staff phải tự đối chiếu ảnh | U4 ✅ |
| Font không có dấu tiếng Việt | `capabilities` + kiểm glyph trước khi sinh (có một phần) | U6 |
| Vật tư hết / không tương thích | Kiểm tồn + tương thích khi khách chọn và khi khoá | U1/U6 |
| Robot mất kết nối / E-Stop / lỗi giữa chừng | Có sẵn (lost-link, PAUSED, sự cố → FAILED → xếp lại) | Có |
| QC không đạt | Không tự viết lại; Staff quyết định, viết lại dùng snapshot mới hoặc cùng snapshot với job mới | U8 |
| Yêu cầu giả mạo (chữ ký, giấy tờ) | BR-23; studio thêm cảnh báo + AI từ chối trong hội thoại + Staff duyệt | U5 |
| Khoá ký bị lộ | Xoay khoá: khoá mới ký, khoá cũ chỉ xác minh, thu hồi snapshot ký bằng khoá lộ | U1 |
