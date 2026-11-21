# OT-2: viết theo nét chữ đã học, kế hoạch (2026-11-20, chủ dự án DUYỆT Q1–Q4 theo khuyến nghị cùng ngày)

Chủ dự án chốt I-c (2026-11-20): sau Phase I lập kế hoạch OT-2. Quyết định cũ còn hiệu lực: D3 (OT-2 cũng sửa nét như OT-1 / OT-3),
mục "OT-2" của V2 (nghiên cứu mô hình sinh phác thảo OT-2, không chỉ sửa bản Staff tải lên), D5 (polyline là định dạng nét chuẩn).
Tài liệu này **chỉ là kế hoạch**; chưa có dòng code OT-2 nào.

## 1. Yêu cầu gốc

| Mã | Nội dung |
|---|---|
| FR-07 (UC-09) | Khách tải ≥ 1 trang mẫu chữ của cùng một người (khuyến nghị đủ chữ cái) hoặc chọn bộ nét đã lưu; nhập nội dung mới; xác nhận quyền dùng nét chữ |
| FR-36 (UC-09, UC-25) | Tách ký tự từ mẫu, xây bộ glyph của người viết (HandwritingStyle), bổ sung ký tự thiếu bằng mô hình sinh; sau đó dùng pipeline FR-35 (như OT-3). Hướng nghiên cứu: few-shot handwriting generation |
| LI-10 | R&D: chưa đạt chất lượng thì xưởng từ chối loại đơn hoặc chỉ nhận thử nghiệm |
| BR-23, NFR-12 | Không viết chữ ký, giấy tờ pháp lý, văn bản có dấu hiệu giả mạo; ảnh và bộ nét xoá sau 90 ngày trừ khi khách đồng ý lưu |

## 2. Hiện trạng code

- Có: loại đơn `OT2_LEARNED_STYLE`, đầu vào `HANDWRITING_SAMPLE` + `TEXT_CONTENT`, kiểm tra khi gửi đơn (mẫu hoặc bộ nét đã lưu, nội dung, xác nhận quyền).
- Có bảng `handwriting_styles` (`status` PENDING_REVIEW / APPROVED / REJECTED / DELETED, `glyph_set_uri`, `coverage_pct`, `right_to_use_confirmed`, `keep_consent`, `approved_by`) và luồng xoá 90 ngày giữ lại bộ nét có `keep_consent`. **Chưa có gì tạo ra bộ nét**: `glyph_set_uri` chưa bao giờ được ghi.
- Sinh phác thảo OT-2 bị chặn ở `sketches.run_engine`, `SketchWork.generate`, công cụ trợ lý (`AI_TYPE_UNSUPPORTED`). `system_settings.order_types_enabled` mặc định chỉ OT-1, OT-3.
- Dùng lại được: phục dựng nét từ ảnh (`recovery.py`, U3), vùng chữ (`regions.py`), dàn trang và dấu tiếng Việt ghép theo nét (`text_to_stroke.py`, `styled_text.py`), Geometry Engine và luồng V2 (working sketch → v1 → duyệt → snapshot → kiểm tra chuyển động).

## 3. Hai hướng và khuyến nghị

**Hướng A, thu glyph (cổ điển, trong sản phẩm, không thêm thư viện).** Khách viết một **phiếu mẫu cố định** (A4 in sẵn ô, chữ cần viết in mờ bên trên, phủ đủ chữ cái thường / hoa, số, dấu câu). Vì đã biết chữ trong từng ô nên không cần đọc chữ, không gửi ảnh ra ngoài. Mỗi ô → phục dựng nét bằng bộ U3 → glyph polyline của người viết. Dấu tiếng Việt: ghép từ glyph dấu người đó viết (phiếu có ô riêng cho các dấu) theo cách `text_to_stroke` đang ghép dấu Hershey. Nhiều mẫu cho một chữ → chọn ngẫu nhiên khi viết để chữ không lặp y hệt. Phần tử được dàn trang bằng layout OT-3 có sẵn.
- Ưu: chạy được trên Render, dễ giải thích, nét là nét thật của người viết, Staff duyệt từng glyph được.
- Nhược: chỉ có chữ đã viết trên phiếu; nối chữ (chữ viết liền) sẽ kém tự nhiên vì ghép từ glyph rời.

**Hướng B, mô hình sinh nét few-shot (nghiên cứu, ngoài sản phẩm).** Mô hình học từ vài mẫu chữ để sinh nét cho chữ bất kỳ, kể cả chữ không có trên phiếu và cách nối chữ. Cần PyTorch, trọng số mô hình và dữ liệu chữ viết tay **dạng nét** (online) tiếng Việt; chạy trong môi trường benchmark riêng như VietOCR ở E1, không vào `requirements` sản phẩm. Ứng viên để khảo sát: các mô hình sinh chữ viết tay theo phong cách từ vài mẫu đã công bố (họ RNN / transformer sinh chuỗi điểm), dữ liệu online tiếng Việt công khai (ví dụ bộ HANDS-VNOnDB; giấy phép cần kiểm trước khi tải).
- Ưu: phủ mọi chữ, có thể tự nhiên hơn.
- Nhược: rủi ro cao (LI-10), phải tải dữ liệu / mô hình (cần xin phép), không chắc chạy được trên Render, khó giải thích khi sai.

**Khuyến nghị:** làm A cho sản phẩm; B là nghiên cứu song song, chỉ vào sản phẩm khi vượt cổng chất lượng đặt trước (O1). OT-2 **vẫn tắt** trong `order_types_enabled` tới khi chủ dự án xem kết quả và tự bật.

## 4. Các phase

| Phase | Nội dung | Đầu ra | Database |
|---|---|---|---|
| **O1 Đo trước** | (a) Thử hướng A bằng script trên dữ liệu công khai: dựng bộ glyph từ một phần chữ của một người, viết lại phần câu còn lại, đo. (b) Khảo sát hướng B: tìm mô hình / dữ liệu, kiểm giấy phép, chạy thử trong môi trường riêng nếu được phép tải | `docs/benchmarks/O1_*.md` với số đo thật, ảnh so sánh | Không |
| **O2 Phiếu mẫu và bộ nét** | Sinh phiếu mẫu PDF; khách tải ảnh phiếu đã viết; tìm ô (dấu căn góc), phục dựng nét từng ô, lưu bộ glyph vào file store, tính `coverage_pct`; Staff xem từng glyph, bỏ glyph hỏng, duyệt / từ chối bộ nét (`approved_by`) | API tạo / xem / duyệt bộ nét, test | Có thể thêm cột (vd. số glyph theo chữ, phiên bản phiếu); chỉ thêm, hỏi trước khi áp |
| **O3 Viết bằng bộ nét** | Đơn OT-2 với bộ nét đã duyệt: dàn nội dung bằng layout OT-3, nguồn glyph là bộ nét của người viết; thiếu chữ thì báo rõ (không lặng lẽ thay bằng font khác); vào đúng luồng V2: working sketch, sửa nét D3, trợ lý, báo giá, duyệt, snapshot, kiểm tra chuyển động; bỏ `AI_TYPE_UNSUPPORTED` khi có bộ nét đã duyệt | Test end-to-end như Test 4 của Phase I | Không dự kiến |
| **O4 Nghiệm thu** | Toàn suite Supabase, cập nhật `FE_API_GUIDE.md`, `PROJECT_STATUS.md`; báo cáo chất lượng cho chủ dự án quyết định có bật OT-2 không | Báo cáo | - |

Hướng B, nếu vượt cổng ở O1, thành phase riêng sau O3 (chỉ thay nguồn glyph cho chữ thiếu), cần kế hoạch và duyệt riêng.

## 5. Đo thế nào (đặt trước khi đo, không chỉnh sau)

- **Đọc được:** ảnh render từ nét sinh ra → Gemini đọc (đường I2) → CER so với nội dung đã nhập. Chỉ trên dữ liệu công khai, không ảnh khách.
- **Giống người viết:** khoảng cách hình dạng (DTW trên polyline chuẩn hoá) giữa glyph sinh ra và glyph thật **giữ lại không dùng để dựng bộ** của cùng người viết, so với glyph cùng chữ của người khác. Giống người viết nghĩa là gần người đó hơn người khác.
- **Robot viết được:** kiểm tra chuyển động (`motion validation`) như OT-1 / OT-3, số nét / chữ, độ dài đường nhấc bút.
- **Mắt người:** chủ dự án chấm mù một bộ ảnh (thật / sinh ra trộn lẫn). Cổng đề xuất cho B: CER không tệ hơn A, và chủ dự án không phân biệt được thật / sinh ra tốt hơn đoán ngẫu nhiên rõ rệt. Đây là đề xuất, chủ dự án chốt.

## 6. An toàn

- Viết theo nét chữ một người thật là rủi ro mạo danh. Giữ BR-23: khách xác nhận quyền dùng nét chữ (đã có), Staff duyệt từng bộ nét và từng đơn, chặn nội dung giống chữ ký / giấy tờ (Staff kiểm, trợ lý không viết chữ ký).
- Phiếu mẫu cố định nên không cần gửi ảnh mẫu chữ cho Gemini; ảnh và bộ nét theo NFR-12 (xoá 90 ngày trừ khi `keep_consent`).
- Không dùng ảnh mẫu chữ của khách để huấn luyện hay đo (như D4).

## 7. Câu hỏi cho chủ dự án

| | Câu hỏi | Khuyến nghị |
|---|---|---|
| Q1 | Mẫu chữ: phiếu mẫu cố định hay trang chữ tự do như FR-07 viết? | Phiếu cố định (biết trước chữ, không cần AI đọc, không gửi ảnh ra ngoài); trang tự do để sau |
| Q2 | Chữ không có trong bộ nét | Dấu ghép từ glyph dấu của người viết; thiếu chữ cái thì báo khách / Staff, không thay bằng font khác |
| Q3 | Hướng B: cho phép tải dữ liệu chữ online tiếng Việt và mô hình công khai vào môi trường benchmark riêng (không vào sản phẩm, kiểm giấy phép trước, báo tên / nguồn / dung lượng trước khi tải) | Có, nhưng chỉ sau khi O1(a) xong |
| Q4 | Thứ tự | O1 → O2 → O3 → O4, mỗi phase báo lại; OT-2 vẫn tắt tới khi chủ dự án bật |

## 8. Tiến độ

- **O1(a) xong (2026-11-20), commit `02d45a5`:** `docs/benchmarks/O1a_glyph_harvest_2026-11-20.md`. Trên 50 trang công khai chỉ
  6,4 % từ tách được thành chữ cái (59 % từ viết liền), nên không thu được bộ glyph từ trang tự do; phiếu mẫu (Q1) là bắt
  buộc. Glyph nhận diện đúng người viết gấp ~2,2 lần ngẫu nhiên (24 / 211). Đọc được và robot viết được chưa đo (không đủ
  chữ để viết lại), chuyển sang O2 trên phiếu mẫu thật.
- **O1(b) khảo sát xong (2026-11-20), chưa tải gì, commit `02d45a5`:** `docs/benchmarks/O1b_model_survey_2026-11-20.md`. Hai mô
  hình sinh nét bút có mã MIT (SDT, DiffInk), không có sẵn tiếng Việt; dữ liệu tiếng Việt dạng nét HANDS-VNOnDB chỉ cho
  nghiên cứu, không thương mại, nên mô hình huấn luyện trên đó không vào sản phẩm thu tiền khi chưa được tác giả cho phép.
  Khuyến nghị: làm O2 trước, thử SDT (B1) khi có glyph thật từ phiếu mẫu.

## 9. O2 chi tiết: phiếu mẫu và bộ nét (2026-11-20, chủ dự án DUYỆT O2-a … O2-d theo khuyến nghị)

Chủ dự án chọn làm O2 trước B1 / B2 (2026-11-20). Không thêm thư viện: PDF bằng `fpdf2`, nắn ảnh bằng OpenCV, dò nét bằng phần
lõi của bộ phục dựng U3 (tách thành hàm dùng chung, kết quả OT-1 giữ nguyên từng byte, có test).

**Phiếu mẫu (`SHEET_V1`, 3 trang A4).**
- Lưới ô khoảng 18 × 18 mm. Chữ cần viết in nhỏ phía trên mỗi ô, nằm ngoài vùng viết.
- Đường kẻ dòng (baseline) và đường cao chữ (x-height) chỉ đánh dấu bằng vạch ngắn trên hai cạnh ô, không kẻ trong ô, để
  mực in không bị lẫn với nét chữ.
- Bốn dấu góc đen để nắn ảnh chụp nghiêng. Mã trang in chữ to (`SHEET_V1 1/3`).

| Nội dung | Số ô |
|---|---|
| Chữ thường a–z và ơ ư đ, mỗi chữ 3 lần | 87 |
| Chữ hoa A–Z và Ơ Ư Đ, mỗi chữ 2 lần | 58 |
| Số 0–9, mỗi số 2 lần | 20 |
| Dấu câu `. , ? ! : ; - ( ) " '` | 11 |
| Dấu tiếng Việt viết trên chữ a: á à ả ã ạ ă â ê ô, mỗi chữ 2 lần (tách dấu khỏi thân chữ đã biết) | 18 |

**Đọc phiếu.**
- Ảnh từng trang qua bốn bước: tìm 4 dấu góc, nắn về đúng khổ, cắt từng ô (bỏ viền), dò nét trong ô.
- Nét lưu theo hệ toạ độ của ô: biết baseline và x-height theo vạch in, nên glyph chuẩn hoá theo cỡ chữ in, không phải đoán.
- Ô trống, ô có nhiều mảnh lạ hoặc nét tràn ra ngoài ô thì đánh dấu để Staff xem lại; hệ thống không tự sửa.
- Bộ nét lưu trong file store (`glyph_set_uri`) dạng JSON: mỗi ký tự có danh sách mẫu, mỗi mẫu là polyline (mm theo x-height
  chuẩn) kèm ô gốc.
- `coverage_pct` là phần trăm ký tự của phiếu có ít nhất một mẫu dùng được.

**Luồng.**
1. Khách tạo bộ nét: đặt tên, xác nhận quyền dùng nét chữ (BR-23), chọn có lưu lâu dài không (`keep_consent`).
2. Tải PDF phiếu, viết tay, chụp, tải từng trang lên. Hệ thống đọc phiếu và báo độ phủ cùng các ô có vấn đề. Khách viết lại
   trang nếu cần, rồi gửi duyệt.
3. Staff xem từng glyph cạnh ảnh ô gốc, loại mẫu hỏng, rồi duyệt hoặc từ chối kèm lý do.
4. Chỉ bộ nét đã duyệt mới hiện ở `/catalog/my-styles` (đã có) và mới dùng được cho đơn OT-2 ở O3.
- Ảnh phiếu và bộ nét tuân theo NFR-12 (xoá sau 90 ngày trừ khi `keep_consent`). Kiểm lại job xoá hiện có cho cả ảnh phiếu.

**Database (migration 0028, chỉ thêm).**
- `style_status` thêm giá trị `DRAFT`, cho bộ nét đang làm chưa gửi duyệt.
- `handwriting_styles` thêm cột:
  - `sheet_version`
  - `review_note`
  - `updated_at`
  - `submitted_at`
- Bảng mới `handwriting_style_pages`: `style_id`, `page_no`, file ảnh, `read_result` jsonb, thời điểm tải.
- Không sửa dòng dữ liệu thật nào. Thử trên DB cục bộ trước, rồi áp lên Supabase và tạo lại script DB tổng.

**Test.**
- Phiếu tổng hợp: PDF phiếu → render thành ảnh → vẽ chữ Hershey vào ô → xoay, làm mờ, chụp nghiêng → đọc lại. Kiểm tra đúng
  ký tự vào đúng ô, ô trống và ô tràn được đánh dấu.
- Quyền: khách chỉ thấy bộ nét của mình; Staff duyệt; bộ nét chưa duyệt không dùng được.
- Toàn suite trên Supabase.

**Đo trên phiếu thật.** Cần **một phiếu thật do người đồng ý viết** (chủ dự án hoặc thành viên nhóm). Đo:
- phần trăm ô đọc đúng;
- độ phủ;
- nhận diện người viết, chỉ đo được nếu có từ 2 người viết trở lên.
Đo "đọc được" và "robot viết được" khi O3 ghép được chữ. Ảnh phiếu thật không commit.

**Câu hỏi cho O2.**

| | Câu hỏi | Khuyến nghị |
|---|---|---|
| O2-a | Migration 0028 như trên | Duyệt |
| O2-b | Ai viết phiếu thật để đo, và mấy người | Chủ dự án + 1 thành viên (2 người để đo được nhận diện người viết); ảnh chỉ để đo, không commit |
| O2-c | API bộ nét có mở khi OT-2 còn tắt không | Mở (chỉ lưu nét của chính người đó, có xác nhận quyền); đơn OT-2 vẫn bị chặn tới khi chủ dự án bật |
| O2-d | Nội dung phiếu như bảng trên (3 trang) | Duyệt; chữ viết liền để sau (cần mô hình, O1(b)) |

**Tiến độ O2 (2026-11-20, commit `02d45a5`):** code xong. Migration 0028 đã áp lên Supabase, có 8 test mới
(`tests/test_ot2_style_sheet.py`), FE mục 7y.

Khác kế hoạch:
- Người duyệt là **Manager**, dùng luồng FR-42 `/manager/styles` có sẵn, không phải Staff.
- Phiếu có 194 ô (chữ có dấu: 9 loại × 2), không phải 18.

Việc còn lại của O2: đo trên phiếu thật do chủ dự án và 1 thành viên viết (ảnh không commit).

## 10. O3 chi tiết: viết nội dung bằng bộ nét (2026-11-21, chủ dự án DUYỆT O3-a … O3-f theo khuyến nghị cùng ngày)

Không đổi DB (không migration).

**Hiện trạng dùng lại được.**
- Đơn OT-2 đã chọn được bộ nét: `order_inputs.handwriting_style_id` trên dòng `TEXT_CONTENT`. Khi lưu, hệ thống kiểm bộ nét phải
  thuộc khách và đang `APPROVED` (`orders._validate_template_style`).
- Dàn trang OT-3 (`text_to_stroke.compose_text`, `styled_text.compose_styled`) nhận một "nguồn glyph" bất kỳ có
  `char(ch) -> CharGlyph` và `space_units`. Hershey (`HersheySource`) và font outline (`OutlineSource`) đều dùng giao diện này.
- Bộ glyph O2 (`ot2-glyphs/1`): nhiều mẫu cho mỗi chữ, nét theo đơn vị x-height (baseline 0), dấu thanh / dấu mũ của người
  viết kèm vị trí so với chữ mang dấu (`dx`, `dy`).
- Hiện có 3 chỗ chặn OT-2 (`AI_TYPE_UNSUPPORTED`): `sketches.run_engine`, `SketchWork.generate`, và công cụ
  `generate_sketch` của trợ lý.

**Làm gì.**
1. `stroke_ai/style_source.py` (mới), `StyleSource(glyph_set, seed)`, cùng giao diện với Hershey:
   - Đổi đơn vị x-height sang đơn vị dàn trang. Tỉ lệ chữ hoa / chữ thường lấy từ chính chữ người viết (trung vị chiều cao chữ hoa),
     nên chữ hoa giữ đúng độ cao người đó viết.
   - Bề rộng chữ lấy từ khung nét cộng một khoảng cách chữ cố định. Không nối chữ, vì phiếu SHEET_V1 không có chữ viết liền.
   - Chữ có dấu:
     - `ơ`, `ư`, `đ` lấy thẳng từ phiếu.
     - Các chữ còn lại ghép theo Q2: chữ gốc của người viết, cộng dấu mũ / trăng / thanh của chính họ, đặt theo vị trí trung vị đo
       được trên các ô "chữ mang dấu".
     - Thiếu chữ gốc hoặc thiếu dấu thì báo lỗi `UNSUPPORTED_CHARS` kèm danh sách chữ thiếu, không thay bằng font khác.
   - Chọn mẫu: mỗi lần chữ xuất hiện thì lấy một mẫu khác theo `seed` của nội dung, nên cùng một nội dung luôn ra cùng một phác thảo.
     Mẫu Manager đã loại thì không dùng.
2. `engine.generate_ot2(...)`: giống `generate_ot3` nhưng dùng `StyleSource`.
   - Tên engine là `learned-style-compose`. Engine ghi kèm `style_id` và sha256 của file bộ glyph, để biết phác thảo dựng từ bộ nào.
   - Độ phức tạp tính theo OT-2.
   - Layout của V2 Phase D vẫn dùng được: cỡ chữ theo đoạn, căn lề, khoảng cách dòng.
3. Bỏ 3 chỗ chặn, nhưng chỉ khi đơn có bộ nét đã duyệt. Đơn OT-2 chỉ có ảnh mẫu tự do (FR-07 cũ) vẫn trả `AI_TYPE_UNSUPPORTED`
   như hiện nay, để Staff vẽ tay hoặc từ chối.
4. Luồng V2 giữ nguyên: working sketch, sửa nét D3, trợ lý, báo giá, gửi, Staff nhận, v1, duyệt, snapshot, kiểm tra chuyển động.
5. Bộ nét không còn dùng được (bị xoá, hết hạn, file mất) thì báo `STYLE_UNAVAILABLE` (409), không âm thầm đổi nguồn.
   - Snapshot đã duyệt vẫn giữ nét, vì nét đã nằm trong tài liệu `vhrs-sketch/2`.
   - Kiểm lại job xoá 90 ngày: không được xoá file bộ glyph của bộ nét mà một đơn đang làm vẫn còn dùng.
6. OT-2 vẫn tắt trong `order_types_enabled`. Test mở nó trong phiên test như hiện nay (conftest), không ghi `system_settings` thật.

**Test.**
- Dùng bộ glyph tổng hợp (phiếu Hershey tổng hợp của O2). Kiểm tra:
  - mọi chữ tiếng Việt ghép được dấu;
  - chữ thiếu thì báo đúng danh sách;
  - cùng nội dung ra cùng nét, các lần cùng một chữ dùng mẫu khác nhau;
  - đơn không có bộ nét vẫn bị chặn.
- End-to-end giống Test 4 của Phase I: khách tạo bộ nét, Manager duyệt, đơn OT-2, working sketch, sửa nét, gửi, Staff v1, khách
  duyệt, snapshot, kiểm tra chuyển động đạt.
- Toàn suite trên Supabase.

**Đo (theo mục 5, đặt trước khi đo).** Chỉ đo được khi có phiếu thật do chủ dự án và 1 thành viên viết (O2-b):
- **Đọc ô:** phần trăm ô đọc đúng và độ phủ của từng phiếu.
- **Robot viết được:** kiểm tra chuyển động đạt, số nét / chữ, độ dài đường nhấc bút, so với OT-3 Hershey cùng nội dung.
- **Đọc được:** CER của bản render (xem O3-e).
- **Giống người viết:** khoảng cách DTW giữa glyph giữ lại và glyph của người kia (cần đủ 2 người).
- **Mắt người:** chủ dự án chấm mù 10 câu (5 viết thật, 5 dựng từ bộ nét).

**Câu hỏi cho O3.**

| | Câu hỏi | Khuyến nghị |
|---|---|---|
| O3-a | Sinh tự động chỉ cho đơn có bộ nét đã duyệt; đơn chỉ có ảnh mẫu tự do vẫn để Staff vẽ tay / từ chối | Duyệt |
| O3-b | Chữ không ghép được (thiếu chữ gốc / dấu, ký tự ngoài phiếu như `@ # %`) | Báo `UNSUPPORTED_CHARS` kèm danh sách, khách sửa nội dung hoặc viết lại phiếu; không thay bằng font (giữ Q2) |
| O3-c | Chữ rời, khoảng cách chữ cố định, chưa nối chữ | Duyệt; nối chữ chờ hướng B |
| O3-d | Mỗi lần chữ xuất hiện chọn một mẫu khác nhau, cố định theo nội dung | Duyệt |
| O3-e | Đo "đọc được": cho Gemini đọc ảnh render từ bộ nét của chủ dự án / thành viên (khoá free tier, Google có thể dùng ảnh) hay chỉ chấm bằng mắt | Chỉ bản render (không phải ảnh phiếu), với sự đồng ý của người viết; nếu không đồng ý thì chỉ chấm bằng mắt |
| O3-f | Thứ tự | Code + test tổng hợp ngay; số đo thật khi có ảnh phiếu; OT-2 vẫn tắt tới O4 |

**Tiến độ O3 (2026-11-21, commit `02d45a5`):** code xong, không đổi DB, 7 test mới (`tests/test_ot2_compose.py`), FE mục 7y.
Cục bộ cả suite qua. Supabase THẬT 2026-11-21: 953 passed, 3 skipped, 0 failed (2 giờ 31 phút); dữ liệu thật không đổi. Số đo trên phiếu thật (độ dễ đọc, tỉ lệ chữ hoa, khoảng cách chữ) còn chờ ảnh phiếu của chủ dự án và 1 thành viên.

Khác kế hoạch / cần biết:
- Job xoá 90 ngày vốn chỉ xoá ảnh trang phiếu, không xoá file bộ glyph, nên không phải sửa job. Khách tự xoá bộ nét thì đơn
  đang làm báo `STYLE_UNAVAILABLE`.
- Dấu nặng đặt theo baseline (với chữ có đuôi như `ỵ`, chấm không xuống dưới đuôi chữ).
- Ba giá trị là giả định, chưa đo trên chữ thật:
  - khoảng cách chữ 0,15 x-height mỗi bên;
  - khoảng trắng giữa từ 0,8 x-height;
  - tỉ lệ chữ hoa / chữ thường 1,45 khi bộ nét không có chữ hoa.
- Admin vẫn không bật được OT-2 trong `order_types_enabled` (khoá trong code); mở ở O4 khi chủ dự án quyết định.

Việc còn lại: đo trên phiếu thật (mục 9 và các số đo ở trên), rồi O4.
