# AI-VHRS V2: Đơn hàng hợp nhất, phác thảo chuẩn (canonical sketch) và chỉnh sửa bằng AI

Trạng thái: **Phase A xong; chủ dự án chốt D1–D6 (mục 9.0); Phase B (lõi) xong 2026-11-17, mục 11; Phase C (trợ lý trên đơn) xong 2026-11-18, mục 12; Phase H (Staff sửa bằng cùng engine) xong 2026-11-19, mục 13; Phase D (cấp 1 trên đơn) xong 2026-11-19, mục 14; Phase E phần 1 (đo HTR) xong 2026-11-19, mục 15, phần 2 (tích hợp) chờ chủ dự án quyết. Phase F, I chưa làm.**
Một việc độc lập đã làm và test ngay (mục 2.3): bản xem trước studio và phác thảo của Staff giờ ra **cùng một nét**.

Tài liệu này nối tiếp `docs/UPGRADE_AI_ROBOT_PLAN.md` (U1–U9). Quy ước trạng thái: **ĐÃ CÓ** = code + test chạy; **THIẾT KẾ** = mới
trên giấy; **CHƯA XÁC MINH** = nhận định kỹ thuật, chưa đo trên dữ liệu của dự án.

---

## 1. AI hiện tại thực sự làm được gì (đọc code, 2026-11-17)

| Năng lực | Trạng thái | Ở đâu | Giới hạn thật |
|---|---|---|---|
| Sinh nét OT-3 từ chữ gõ (font một nét Hershey có dấu tiếng Việt, hoặc font viền → đường tâm) | ĐÃ CÓ | `stroke_ai/text_to_stroke.py`, `styled_text.py`, `outline_font.py` | Nét là của **font**, không phải chữ người; biến thiên tự nhiên = co giãn ngẫu nhiên có seed |
| Phục dựng nét OT-1 từ ảnh (nhị phân hoá, Zhang-Suen, đồ thị khung xương, nối nét qua giao điểm, thứ tự đọc, dấu viết sau chữ) | ĐÃ CÓ | `stroke_ai/recovery.py` | Thị giác cổ điển, **không có mô hình học**. Thứ tự / chiều nét là **suy đoán** (heuristic), không phải thứ tự gốc của người viết |
| Vùng từ (word region) cho OT-1: nhãn ORIGINAL / RESTORED / INFERRED, độ tin cậy, Staff + khách sửa vùng | ĐÃ CÓ | `stroke_ai/regions.py`, `sketch_regions`, U4 + U5 | Vùng = cụm mực, không gắn với chữ đã nhận dạng (chưa có HTR) |
| Đo chất lượng phục dựng trên 50 ảnh **thật** (UIT-HWDB / Cinnamon) | ĐÃ CÓ (U3) | `docs/benchmarks/U3_recovery_viet_hw_2026-11-12.md` | IoU trung vị 65,3 % (trần thấp do cách đo nét đều), topology 0,90, endpoint 1,32; **chưa có CER/WER** (chưa có nhận dạng) |
| Nhận dạng chữ viết tay (HTR/OCR) | **KHÔNG CÓ** | — | Trợ lý không đọc được chữ trong ảnh; vùng mờ không biết là chữ gì |
| Trợ lý AI (LLM nhiều nhà cung cấp: Anthropic / OpenAI / Gemini, tự chuyển khi lỗi) | ĐÃ CÓ (U5) | `services/ai/llm.py`, `assistant.py`, `tools.py` | 12 công cụ cấp **tài liệu**: đọc nháp, vật tư, mẫu chữ, sửa chữ / mẫu / cỡ / căn lề, vật tư, tuỳ chọn, kiểm tra, hoàn tác / làm lại, gắn cờ. **Không** sửa vùng, **không** sửa nét, **không** xem ảnh |
| Bản nháp có revision, undo / redo, xem trước, kiểm tra như xưởng | ĐÃ CÓ (U5) | `services/studio.py`, `studio_drafts`, `studio_revisions` | Revision lưu **nội dung** (chữ, vật tư, chỉnh sửa vùng), **không lưu hình học**; mỗi lần xem là sinh lại |
| Tối ưu thứ tự viết (giữ nguyên từ, đảo chiều nét tự do), giới hạn jerk | ĐÃ CÓ (U7) | `stroke_ai/path_order.py`, `motion/plan.py` | Đo trong `docs/benchmarks/U7_path_order_2026-11-12.md` |
| So sánh phiên bản (nét giữ / bỏ / thêm, ảnh chồng màu) | ĐÃ CÓ (U2) | `services/sketch_compare.py` | So theo toạ độ đúng tuyệt đối |
| Gói sản xuất ký Ed25519, kiểm tra trước khi robot chạy, dòng xác thực + QR | ĐÃ CÓ (U1, U8) | `production_snapshot.py`, `core/production_signing.py`, `physical_mark.py`, `robot_agent/` | Robot thật chưa chạy (cần người vận hành) |
| Kế hoạch chuyển động, biến đổi toạ độ giấy → robot, kiểm tra giới hạn | ĐÃ CÓ | `services/motion/{plan,frame,validate}.py` | Chưa đo sai số thành phẩm trên giấy thật |

Kết luận: phần "AI" có thật là **tầng 3 (robot) khá đầy đủ** và **tầng 1 (trợ lý) ở cấp tài liệu**. **Tầng 2 (handwriting intelligence)
mới có phần hình học cổ điển**, chưa có nhận dạng chữ, chưa có biểu diễn nét có cấu trúc (từ → ký tự → nét có id ổn định).

## 2. Vì sao studio và đơn hàng đang tách

### 2.1 Do thiết kế đã duyệt
Q2 = phương án A (`UPGRADE_AI_ROBOT_PLAN.md`): studio là **lớp mới trước đơn**, để không đụng máy trạng thái đơn và luồng tiền.
`FE_API_GUIDE.md` mục 7q cho FE "dùng studio làm màn tạo đơn mới, hoặc để cả hai", nên FE làm hai màn.

### 2.2 Hậu quả trong dữ liệu
- Hai nơi giữ cùng một thứ: `studio_drafts` + `studio_revisions.content` và `orders` (DRAFT) + `order_inputs`.
- `submit()` (`services/studio.py`) **chép** chữ / ảnh / vật tư sang đơn mới rồi gửi. Hình học không đi theo: Staff bấm
  "sinh phác thảo" và engine **chạy lại từ đầu** (`services/sketches.py::generate`).
- Phác thảo chỉ là file `vhrs-trajectory/1`: trang → nét (polyline mm, `kind`). Không có id ổn định cho dòng / từ / ký tự / nét;
  vùng OT-1 trỏ vào nét bằng **chỉ số** `stroke_start..stroke_end`, sinh lại là đổi.

### 2.3 Hai chỗ lệch thật giữa xem trước và phác thảo chính thức (đã sửa 2026-11-17)
1. **Seed:** studio vẽ OT-3 với `seed = draft.id`, xưởng với `seed = order.id`. Cùng nội dung ra biến thiên khác nhau.
2. **Bố cục:** đơn lưu layout ở dạng chuẩn (luôn có `vertical_align`, mặc định MIDDLE), còn studio vẽ bản nháp chưa có layout
   **từ mép trên**. Chữ lệch vị trí trên trang dù cùng seed.

Sửa: `engine.content_seed()` lấy seed từ chính nội dung (chữ NFC, hình vẽ, font, cỡ, căn lề, khổ giấy, layout); seed truyền tay
của Staff vẫn được (biến thể có chủ ý, `engine.seed_source = "explicit"`). Studio vẽ với đúng chữ NFC và layout chuẩn mà
`OrderService.set_text` sẽ lưu (gọi chung `_check_layout`). Test `tests/test_sketch_integrity.py`: 3 kiểu nội dung, nét Staff
**bằng đúng** nét xem trước (toạ độ tới 0,01 mm, cùng thứ tự). OT-1 không có ngẫu nhiên nên không bị (seed không dùng).
Hệ quả cần biết: đơn OT-3 cũ, Staff bấm sinh lại sẽ ra biến thiên khác lần trước (seed đổi cách tính); phác thảo đã lưu không đổi.

Đây mới là "sinh lại ra cùng kết quả". Mục tiêu V2 vẫn là **không sinh lại**: chuyển chính hình học đã duyệt (mục 5).

## 3. Có thể tái sử dụng gì

| Thành phần | Giữ nguyên | Mở rộng |
|---|---|---|
| `orders` + máy trạng thái, báo giá, thanh toán, snapshot ký, robot agent, QC, watermark | ✅ | — |
| `sketches` (phiên bản chính thức, `content_hash`, `is_final`), duyệt phác thảo U2 | ✅ | thêm nguồn "từ bản nháp của khách" |
| `sketch_regions` (U4) | ✅ | gắn với id phần tử của tài liệu |
| Engine OT-1 / OT-3, `path_order`, `motion/*` | ✅ | xuất thêm cấu trúc (dòng / từ / ký tự / nét có id) |
| Revision + undo / redo của studio | logic ✅ | chuyển sang gắn với đơn |
| LLM adapter nhiều nhà cung cấp, ghi chi phí, consent, trần lượt | ✅ | thêm công cụ cấp vùng / nét |
| `sketch_compare` | ✅ | dùng cho Before / After mỗi lần AI sửa |
| Editor Staff (`create_manual`, sửa vùng `regions/{id}/edit`) | ✅ | chuyển sang cùng Geometry Engine với AI |

## 4. Kiến trúc đề xuất: 3 tầng trong monolith hiện tại (THIẾT KẾ)

```
FE (Create Order = sketch editor + chat)          Staff editor
        │                                              │
        ▼                                              ▼
┌──────────────── Order / Application services (orders, quotations, payments, snapshot) ────────────────┐
│  Sketch Versioning  (working revisions của đơn DRAFT → phiên bản chính thức `sketches`)               │
│  Tầng 1  AI Assistant Orchestrator   services/ai/   (LLM chọn công cụ; không bao giờ ra toạ độ)      │
│  Tầng 2  Handwriting Intelligence    services/stroke_ai/ + htr/  (nhận dạng, phục dựng, cấu trúc nét) │
│          Geometry Engine             services/geometry/  (lệnh sửa có cấu trúc → hình học mới, kiểm tra)│
│  Tầng 3  Robotic Writing Engine      services/motion/ + production_snapshot + robot_agent/           │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Nguyên tắc: LLM hiểu yêu cầu và **chọn lệnh + tham số trong khoảng cho phép**; Geometry Engine (code xác định) thực hiện và kiểm
tra; mỗi lệnh thành một revision; robot chỉ nhận hình học từ snapshot đã ký. Việc nặng (phục dựng ảnh, HTR) chạy thành job có
trạng thái, giới hạn thời gian, huỷ được.

## 5. Unified Order + Canonical Sketch (THIẾT KẾ, cần chốt D1–D3)

### 5.1 Luồng
`POST /orders` (DRAFT) → nhập chữ / ảnh, vật tư → **bản phác thảo làm việc r1** (engine) → khách + AI sửa (r2, r3, …) →
`submit` gửi **revision hiện tại** → Staff tiếp nhận: phiên bản chính thức v1 = **đúng hình học đó** (không sinh lại) → Staff sửa
(v2…) → báo giá → khách duyệt → cọc → snapshot ký → robot.

### 5.2 Dữ liệu (đề xuất, chỉ thêm, không xoá bảng cũ)
- **`sketch_revisions`** (mới): `id, order_id, parent_id, seq, author (CUSTOMER|AI|STAFF|ENGINE), tool_name, model/provider,
  note, document jsonb (lớp ngữ nghĩa + bố cục), geometry_uri + geometry_hash, materials jsonb, validation jsonb, created_at`.
  Đơn có `current_revision_id`. Undo / redo = di con trỏ như studio hiện tại.
- **Định dạng hình học `vhrs-sketch/2`** (file trong storage, như trajectory hiện nay):
  `document → pages → blocks → lines → words → glyphs → strokes`, mỗi phần tử có **id ổn định** (sinh một lần, giữ qua các lần sửa),
  `stroke = {id, points (polyline mm), kind, provenance: ENGINE|RECOVERED|INFERRED|STAFF|AI_EDIT, source_ref {image_id, bbox}?,
  confidence?}`. `vhrs-trajectory/1` vẫn **sinh ra từ đây** cho robot / snapshot (không đổi tầng 3).
- Quan hệ phụ thuộc: ngữ nghĩa (chữ) → bố cục → hình học → quỹ đạo. Sửa chữ / font / cỡ / bố cục = sinh lại **phần bị ảnh hưởng** và
  báo rõ; sửa vùng / nét chỉ đổi hình học (chữ của vùng có thể đổi theo khi khách nói rõ).
- `studio_drafts` / `studio_revisions`: giữ dữ liệu; API `/studio` thành **lớp tương thích** gọi vào đơn DRAFT đến khi FE chuyển xong
  (rồi mới đánh dấu deprecated). Không xoá dữ liệu cũ.
- `sketches`: thêm `source_revision_id` (phiên bản chính thức sinh từ revision nào của khách) để kiểm chứng "Staff nhận đúng".

## 6. Chỉnh sửa 3 cấp (THIẾT KẾ)

| Cấp | Đối tượng chọn | Lệnh (Geometry Engine) | Kiểm tra bắt buộc |
|---|---|---|---|
| 1 Tài liệu | cả đơn / đoạn | chữ, font, cỡ (cả theo đoạn), căn lề, giãn dòng, lề, vật tư, số bản (đã có) | như form hiện tại + sinh lại hình học + revision |
| 2 Vùng | đoạn / dòng / từ / ký tự / dấu / vùng ảnh | bỏ, viết chữ (đã có cho OT-1), dời, co giãn, nghiêng, **thay chữ giữ nét gốc** (cần HTR + ghép ký tự) | chỉ phần tử được chọn đổi; nét nối với phần tử bên cạnh → báo phạm vi, xin xác nhận |
| 3 Nét | một hay nhiều nét (id) | dời / xoay / co giãn, nắn độ cong (fit Bézier cục bộ rồi lấy mẫu lại), kéo dài / cắt, nối / tách, làm mượt giữ góc, căn dấu | trong lề giấy, độ dời tối đa, không tự cắt nhau ngoài ý muốn, độ dài đoạn tối thiểu, giới hạn bút; ngoài vùng chọn **không đổi** (so hash) |

LLM nhận **id đã chọn trên FE** + mô tả; trả về lệnh có tham số bị chặn (ví dụ `curvature_scale ∈ [0,5; 1,5]`, `dx,dy ∈ ±5 mm`).
Yêu cầu mơ hồ ("đẹp hơn") → hỏi lại hoặc đưa 2–3 phương án xem trước, không tự sửa.

## 7. Mô hình và thuật toán (CHƯA XÁC MINH trừ khi ghi khác)

| Việc | Lựa chọn | Nhận định |
|---|---|---|
| Trợ lý (tầng 1) | Giữ adapter Anthropic / OpenAI / Gemini hiện có | Gemini đã chạy thật bằng dữ liệu giả (U5). Chất lượng chọn công cụ cần **cùng một bộ kịch bản** cho mọi nhà cung cấp, chưa chạy |
| HTR tiếng Việt | (a) VietOCR (mã nguồn mở, nhận dạng theo dòng, cần PyTorch), (b) PaddleOCR (dò dòng) + mô hình nhận dạng tiếng Việt, (c) VLM qua API (Gemini / Claude / GPT đọc ảnh) | Chưa benchmark trên ảnh của dự án. (a)(b) chạy cục bộ, không lộ ảnh, nhưng thêm phụ thuộc nặng (PyTorch, RAM trên Render). (c) dễ tích hợp, có thể tốt với chữ khó, nhưng **gửi ảnh khách ra ngoài** (hiện chính sách: không gửi ảnh) và tốn phí mỗi ảnh. Phải đo CER / WER trên 50 ảnh U3 trước khi chọn |
| Phục dựng ảnh cũ | Giữ pipeline cổ điển; thêm khử nền / tăng tương phản cục bộ | Mô hình học (khử nhiễu tài liệu) chỉ xét khi có ảnh hư hại thật để đo (Q5 còn thiếu) |
| Vector hoá / nét | Giữ Zhang-Suen + đồ thị; thêm fit Bézier (Schneider) **cục bộ khi sửa**, lưu polyline | Robot và mọi công cụ hiện dùng polyline; Bézier chỉ là lớp biên tập |
| Đo chất lượng | IoU (đã có), topology, endpoint, Chamfer / Hausdorff giữa khung xương ảnh và nét, CER / WER khi có HTR, độ lệch bố cục, đánh giá người | Không dùng một chỉ số làm kết luận (U3 đã cho thấy IoU có trần thấp) |
| Robot | Giữ `motion/*`, U7, snapshot, agent | Chưa đo sai số thành phẩm trên giấy thật |

## 8. Lộ trình và tiêu chí nghiệm thu

Ưu tiên **lát cắt dọc** trước khi mở rộng: OT-3, khách tạo đơn DRAFT → engine sinh r1 → AI dời một dấu / nắn một nét → gửi →
Staff nhận v1 đúng nét đó (hash bằng nhau) → báo giá → duyệt → snapshot → mô phỏng chuyển động (không chạy robot thật).

| Phase | Nội dung | Nghiệm thu (test thật, không giả lập kết quả) |
|---|---|---|
| A | Audit + kiến trúc (tài liệu này) + sửa lệch xem trước / chính thức | ✅ `test_sketch_integrity.py` |
| B | `sketch_revisions`, `vhrs-sketch/2` với id ổn định cho OT-3 (dòng / từ / ký tự / nét), đơn DRAFT có bản làm việc, submit chuyển hình học thành v1 | Test 6 (không đơn trùng, không mất dữ liệu), Test 7 (hash v1 = hash revision khách gửi) |
| C | Trợ lý gắn vào đơn DRAFT (dùng lại `assistant.py`), `/studio` thành lớp tương thích | Test 10 (timeout, nhà cung cấp lỗi, request trùng, sửa đồng thời, revision cũ, công cụ ngoài quyền) |
| D | Cấp 1 hoàn chỉnh trên đơn (cỡ theo đoạn, giãn dòng, lề, màu mực) | Test 1 |
| G (lên trước E, F) | Geometry Engine + công cụ cấp nét cho AI và Staff dùng chung | Test 3 (control point, liên tục, undo / redo, ngoài vùng chọn không đổi) |
| F | Cấp vùng cho OT-3 và OT-1 (id ổn định, phạm vi ảnh hưởng) | Test 2 |
| E | HTR: benchmark rồi tích hợp; vùng không chắc → cảnh báo / hỏi khách / chuyển Staff | Test 4, Test 5 (không bịa chữ), CER / WER thật |
| H | Staff editor dùng chung engine, snapshot từ revision đã duyệt | Test 8 |
| I | Toàn suite Supabase, benchmark, tài liệu | Test 9 |

## 9. Câu hỏi cần chủ dự án chốt

### 9.0 Đã chốt (chủ dự án, 2026-11-17)
| | Quyết định |
|---|---|
| D1 | **A**: đơn DRAFT là gốc; revision gắn với đơn (`sketch_revisions`); `/studio` thành lớp tương thích đến khi FE chuyển xong. Không xoá dữ liệu cũ |
| D2 | **A**: Staff tiếp nhận thì phiên bản chính thức v1 = đúng hình học khách gửi, không sinh lại |
| D3 | **Cả ba loại đơn OT-1, OT-2, OT-3** được sửa nét (rộng hơn khuyến nghị). OT-3 vẫn chặn biên độ lệnh để chữ không trượt khỏi mẫu quá xa |
| OT-2 | **Nghiên cứu mô hình sinh phác thảo OT-2** (học nét chữ người viết, R&D LI-10), không chỉ sửa bản Staff tải lên. Cần dữ liệu mẫu chữ của người viết; sẽ có câu hỏi riêng khi tới phase đó |
| D4 | Đo cả hai: VietOCR cục bộ (môi trường benchmark riêng, không vào `requirements`) và Gemini (khoá hiện có, ~50–100 lượt) trên 50 ảnh công khai U3; chọn theo CER / WER |
| D5 | Polyline là dữ liệu chuẩn; Bézier chỉ fit tạm khi sửa |
| D6 | **Duyệt** Phase B + lát cắt dọc OT-3 (migration áp thẳng Supabase theo quy trình đã uỷ quyền) |

**D1. Nguồn nghiệp vụ của bản nháp**
- Vấn đề: bản nháp nằm ở `orders` (DRAFT) hay vẫn ở `studio_drafts`.
- Ảnh hưởng: chọn sai thì phải chuyển dữ liệu lần nữa, hoặc giữ mãi hai nguồn.
- A. Đơn DRAFT là gốc; revision gắn với đơn (`sketch_revisions`); `/studio` thành lớp tương thích rồi bỏ dần. Ưu: một nguồn, đúng yêu cầu V2. Nhược: việc lớn hơn, FE phải chuyển.
- B. Giữ `studio_drafts`, nhưng tạo đơn DRAFT ngay khi mở studio và gắn 1-1. Ưu: ít đổi. Nhược: vẫn hai bảng cho một việc.
- Khuyến nghị: **A**.
- Cần xác nhận: A hay B.

**D2. Bản khách gửi có là phiên bản chính thức đầu tiên không**
- Vấn đề: hiện Staff luôn sinh phác thảo sau khi tiếp nhận.
- Ảnh hưởng: nếu Staff vẫn sinh lại, mọi chỉnh sửa vùng / nét của khách sẽ mất.
- A. Khi tiếp nhận, v1 = đúng hình học khách gửi (Staff vẫn kiểm tra, sửa, báo giá như cũ). Ưu: không mất công sức của khách. Nhược: Staff nhận cả hình học do khách / AI chỉnh, cần cảnh báo rõ nét nào bị sửa.
- B. Staff vẫn sinh lại, chỉ áp lại chỉnh sửa (như U5 hiện tại với vùng). Nhược: chỉnh sửa nét không áp lại được tin cậy.
- Khuyến nghị: **A**.
- Cần xác nhận: A hay B.

**D3. Khách sửa nét ở loại đơn nào**
- Vấn đề: OT-3 là chữ sinh từ font; sửa nét làm chữ khác mẫu chữ.
- Ảnh hưởng: sản phẩm có thể không còn đúng "mẫu chữ" khách chọn; Staff khó kiểm tra.
- A. Cả OT-1 và OT-3, OT-3 giới hạn lệnh (dời dấu, nghiêng, khoảng cách, độ cong nhẹ). B. Chỉ OT-1.
- Khuyến nghị: **A** (lát cắt dọc đầu tiên làm trên OT-3 vì không cần ảnh).
- Cần xác nhận: A hay B.

**D4. Nhận dạng chữ (HTR) chạy ở đâu**
- Vấn đề: chọn mô hình cục bộ hay gửi ảnh cho dịch vụ AI.
- Ảnh hưởng: quyền riêng tư (ảnh chữ người thật), chi phí, RAM máy chủ.
- A. Mô hình mở chạy cục bộ (VietOCR / PaddleOCR). Ưu: ảnh không rời hệ thống, không phí theo ảnh. Nhược: thêm PyTorch (nặng, có thể vượt RAM gói Render hiện tại), độ chính xác trên chữ cũ chưa biết.
- B. VLM qua API, chỉ khi khách đồng ý gửi ảnh. Ưu: tích hợp nhanh. Nhược: phí mỗi ảnh, ảnh ra ngoài, kết quả có thể "đoán" chữ (phải kiểm soát chống bịa).
- Khuyến nghị: **đo cả hai trước** trên 50 ảnh bộ công khai đã dùng ở U3 (không phải ảnh khách), rồi quyết theo CER / WER. Cần: cho phép cài PyTorch + VietOCR **trong môi trường benchmark riêng** (không vào `requirements` sản phẩm), và dùng khoá Gemini hiện có cho khoảng 50–100 lượt đọc ảnh công khai (chi phí ước tính rất nhỏ, sẽ ghi số thật).
- Cần xác nhận: đồng ý chạy benchmark A + B như trên.

**D5. Lưu Bézier hay polyline**
- Khuyến nghị: polyline là dữ liệu chuẩn (robot, so sánh, snapshot đều dùng); Bézier chỉ fit tạm thời khi sửa rồi lấy mẫu lại. Phương án ngược lại (lưu Bézier) phải viết lại tầng 3.
- Cần xác nhận: đồng ý polyline chuẩn.

**D6. Phạm vi đợt làm tiếp theo**
- Khuyến nghị: Phase B + lát cắt dọc OT-3 (mục 8) trước; migration thêm bảng `sketch_revisions` và cột liên kết, áp thẳng Supabase theo quy trình đã uỷ quyền.
- Cần xác nhận: "duyệt" phạm vi này.

## 10. Việc đã làm trong Phase A

| | |
|---|---|
| Làm gì | Audit; sửa lệch seed + bố cục giữa xem trước studio và phác thảo Staff |
| File | `app/services/stroke_ai/engine.py` (`content_seed`, `seed_source`), `app/services/studio.py` (vẽ với chữ NFC + layout chuẩn), `app/services/sketches.py` (seed mặc định theo nội dung), `app/api/staff_schemas.py` (mô tả `seed`), `tests/test_sketch_integrity.py` (mới) |
| API | Không đổi đường dẫn. `trajectory.engine` OT-3 có thêm `seed_source` (`content` / `explicit`); mặc định `seed` của `POST .../sketches/generate` đổi từ id đơn sang seed theo nội dung |
| Database | Không đổi |
| Model | Không thêm |
| Test | Xem `PROJECT_STATUS.md` mục 6 |
| Giới hạn | Vẫn là sinh lại cùng kết quả, chưa chuyển hình học; Staff đổi khổ giấy khi sinh (`paper_size`) thì vẫn khác bản xem trước (đúng ý) |

## 11. Phase B: đã làm (2026-11-17, migration 0023, chưa commit)

| | |
|---|---|
| Làm gì | Bản phác thảo làm việc của đơn DRAFT (D1), Geometry Engine với 11 lệnh có giới hạn theo loại đơn (D3, D5), v1 của Staff = đúng hình học khách gửi (D2), lát cắt OT-3 tới mô phỏng chuyển động (D6) |
| Database | Migration 0023 (chỉ thêm): bảng `sketch_revisions`, cột `orders.current_sketch_revision_id`, `sketches.source_revision_id`. Đã thử lên / xuống trên DB cục bộ; **đã áp Supabase**: 69 đơn thật, 34 phác thảo thật, 15 tài khoản thật, checksum không đổi trước / sau. Script DB tổng tạo lại ở 0023 |
| File mới | `app/services/sketch_geometry.py` (định dạng `vhrs-sketch/2` + Geometry Engine), `app/services/sketch_work.py` (bản làm việc: sinh, sửa, hoàn tác, xem trước, kiểm tra nội dung đổi), `app/api/v1/order_sketch.py`, `migrations/versions/0023_sketch_revisions.py`, `tests/test_v2_working_sketch.py` |
| File sửa | `sketches.py` (`run_engine` dùng chung cho khách và Staff; `adopt_customer_revision`), `workshop.py` (tiếp nhận đơn → v1 từ bản khách; lỗi không chặn việc tiếp nhận, ghi audit `SKETCH_ADOPT_FAILED`), `orders.py` (gửi đơn kiểm `SKETCH_OUTDATED`), `models/order.py`, `models/sketch.py`, `main.py` |
| API | `GET /orders/{id}/sketch`, `POST .../sketch/generate`, `POST .../sketch/edit`, `POST .../sketch/undo`, `/redo`, `GET .../sketch/revisions`, `GET .../sketch/preview` (`FE_API_GUIDE.md` mục 7r) |
| Lệnh hình học | `translate`, `rotate`, `scale`, `slant`, `curvature` (co giãn độ lệch khỏi dây cung, hai đầu giữ nguyên), `smooth`, `extend`, `trim`, `join`, `split`, `delete`. Chọn theo id nét hoặc id từ. Sau mỗi lệnh: trong mép giấy (cách mép ≥ 1 mm), nét ≥ 0,2 mm, trần số điểm, và **nét ngoài vùng chọn được so từng byte** (khác → huỷ lệnh, `500 EDIT_SCOPE_VIOLATION`, coi là lỗi code) |
| Test | `test_v2_working_sketch.py` (11): lát cắt OT-3 (nắn 1 nét + dời 1 từ, revision cũ bị từ chối, hoàn tác / làm lại, gửi → chỉ đọc, Staff tiếp nhận → v1 cùng `geometry_hash`, kế hoạch chuyển động + kiểm tra của v1 đạt với cấu hình đo mẫu); nội dung đổi → `SKETCH_OUTDATED`; giới hạn OT-3, quyền chủ đơn; OT-1 giữ 6 vùng vào v1 (`source` CUSTOMER); đơn không có bản làm việc tiếp nhận như cũ; đơn vị hình học (giữ độ dài khi xoay, độ cong 0 = thẳng theo dây cung, nối / tách / cắt, đầu vào không bị sửa, 5 trường hợp từ chối). Kết quả chạy: `PROJECT_STATUS.md` mục 9 |
| Chưa làm | **Trợ lý AI trên đơn** (Phase C: hiện trợ lý vẫn ở studio, chưa có công cụ `edit_strokes`); studio → lớp tương thích; Staff sửa bằng cùng Geometry Engine (Phase H; Staff vẫn dùng editor cũ trên phác thảo chính thức); id ổn định cho dòng / ký tự (mới có từ / nét); thay chữ trong vùng giữ nét gốc (cần HTR, Phase E / F); HTR benchmark (D4); nghiên cứu mô hình OT-2 |
| Giới hạn đã biết | "Độ cong" là phép co giãn quanh dây cung, chưa fit Bézier (D5 cho phép, sẽ thêm khi cần giữ góc); dời / xoay không kiểm va chạm với nét khác; OT-1 sinh lại phải chạy phục dựng ảnh (vài giây) |


### 11.1 Tạm dừng (2026-11-17 tối, theo yêu cầu chủ dự án) – làm tiếp từ đây

**2026-11-18: bước 1–3 xong** (cục bộ và Supabase đều 898 passed, 3 skipped, 0 failed). Còn: commit khi được yêu cầu, rồi Phase C.
1. Chạy toàn suite cục bộ (`export $(cat .env.test | xargs)`), sửa nếu có lỗi.
2. Chạy toàn suite trên Supabase (migration 0023 **đã có** trên Supabase; chờ nếu phiên khác đang giữ khoá pytest).
3. Ghi kết quả vào `PROJECT_STATUS.md` mục 9 (dòng V2 Phase B) và mục 6; commit khi chủ dự án yêu cầu (không gồm `docs/report_samples/`).
4. Sau đó Phase C (trợ lý AI trên đơn) theo thứ tự đề xuất C → H → D → E → F → I.

## 12. Phase C: trợ lý AI trên đơn (2026-11-18, migration 0024, commit `8d466c1`)

**Kết quả:** toàn suite cục bộ và Supabase THẬT đều 907 passed, 3 skipped, 0 failed (Supabase 5 giờ 18 phút, xong 2026-11-19); dữ liệu thật không đổi.

| | |
|---|---|
| Làm gì | Trợ lý (cùng `assistant.py`, cùng nhà cung cấp, trần lượt, đồng ý gửi dữ liệu) làm việc trên đơn DRAFT / NEED_INFO với bộ công cụ mới `app/services/ai/order_tools.py`: `get_order`, `list_materials`, `list_templates`, `update_text`, `choose_materials`, `set_options`, `check_order`, `generate_sketch`, `get_sketch`, `edit_strokes`, `undo_sketch`, `redo_sketch`, `flag_for_staff`. Sửa nét chỉ qua `edit_strokes` → `SketchWorkService.edit` → Geometry Engine (revision `author = AI`, `tool_name`, `provider`, `model`) |
| Database | Migration 0024 (chỉ thêm): `ai_sessions.order_id` (một phiên mỗi đơn, CHECK đúng một trong `draft_id` / `order_id`, `draft_id` thành nullable), `ai_sessions.flags`, `ai_messages.client_ref` (UNIQUE theo phiên), `ai_tool_calls.sketch_revision_id`. Thử lên / xuống cục bộ; **đã áp Supabase** 2026-11-18: 69 đơn thật, 15 tài khoản thật, 0 phiên AI, checksum không đổi trước / sau. Script DB tổng tạo lại ở 0024 |
| An toàn (Test 10) | Một lượt mỗi đơn (`pg_try_advisory_xact_lock` → `409 AI_TURN_IN_PROGRESS`); `base_revision_id` cũ → `409 STALE_REVISION` trước khi gọi AI; `client_ref` trùng → trả câu đã lưu, không gọi AI lần hai; nhà cung cấp quá thời gian / lỗi → chuyển bên khác, hết bên → `FAILED`, phác thảo không đổi; công cụ không có trong danh sách (vd `submit_order`) → `UNKNOWN_TOOL`; sửa ngoài vùng khách chọn → `OUTSIDE_SELECTION`; tham số ngoài giới hạn → `EDIT_OUT_OF_RANGE`; công cụ lỗi được rollback về savepoint (không để thay đổi dở) |
| Hiểu "chữ này" | OT-3: `from_generated` gắn `text` cho từng từ (sắp các nhóm nét theo thứ tự viết của engine, chỉ gắn khi số nhóm = số từ của nội dung, lệch thì không gắn). OT-1: chưa có chữ (cần HTR, Phase E) |
| Staff | `GET /workshop/orders/{id}/assistant`: cờ (vd `FORGERY_RISK`) + hội thoại + công cụ đã gọi |
| Sửa thêm | `studio_ai` (trần 10 tin / phút dùng chung) giờ đếm **sau** bước kiểm vai trò ở cả `POST /studio/{id}/messages` và route mới: trước đây vai trò bị từ chối vẫn tiêu lượt, nên `test_permission_matrix` thấy `429` thay vì `403` (có thể là nguyên nhân lỗi "chưa rõ" của test này trên Supabase ngày 2026-11-16) |
| Test | `tests/test_v2_order_assistant.py` (9): lát cắt (trợ lý dời đúng từ khách chọn, chỉ nét đó đổi, revision AI có provider / model, khách hoàn tác); từ chối ngoài vùng chọn / ngoài giới hạn / công cụ lạ / lệnh lạ không tạo revision; revision cũ bị từ chối trước khi gọi AI; tin nhắn trùng gọi AI một lần; lượt song song bị từ chối (route thường và stream); quá thời gian → chuyển nhà cung cấp, hết → FAILED; đồng ý, chủ đơn, đơn đã gửi; trợ lý sửa chữ → phác thảo cũ, gửi bị chặn, cờ FORGERY_RISK tới Staff; stream báo từng công cụ |
| Chưa làm | `/studio` thành lớp tương thích gọi vào đơn (D1: giữ studio đến khi FE chuyển; chưa đổi để không phá FE đang dùng); hoàn tác nội dung / vật tư (form đơn chưa có lịch sử); trợ lý chưa đo chất lượng chọn công cụ trên cùng bộ kịch bản cho mọi nhà cung cấp (chưa gọi LLM thật cho Phase C); OT-1 chưa biết chữ của vùng (HTR) |

## 13. Phase H: Staff sửa bằng cùng Geometry Engine (2026-11-19, migration 0025, commit `9f38e29`)

Chủ dự án duyệt 2026-11-19 theo khuyến nghị: **H-a** Staff dùng cùng giới hạn lệnh theo loại đơn với khách / AI; **H-b** chưa làm trợ lý AI cho Staff; **H-c** phiên bản cũ không backfill, tài liệu dựng lại khi đọc.

| | |
|---|---|
| Làm gì | Mọi phiên bản chính thức lưu thêm tài liệu `vhrs-sketch/2` (`document.json` cạnh `trajectory.json`). v1 nhận từ khách = **đúng tài liệu của revision khách** (cùng id, cùng chữ của từ); Staff sửa nét → phiên bản mới giữ id những nét không đổi; sinh lại / tải quỹ đạo tay / sửa vùng U4 → id mới. Mỗi nét có `edited_by` (CUSTOMER / AI / STAFF) để editor Staff thấy nét khách / trợ lý đã sửa (D2). Snapshot chỉ khoá đúng phiên bản + mã băm khách đã duyệt |
| Database | Migration 0025 (chỉ thêm): `sketches.document_uri`, `sketches.geometry_hash`. Phiên bản cũ để NULL (không sửa dòng / file cũ) |
| File | `sketches.py` (`_persist` ghi tài liệu và kiểm `geometry_hash(document) = pages_geometry_hash(quỹ đạo)`, sai → `500 GEOMETRY_MISMATCH` không lưu; `document_of`, `edit_strokes`, `_regions_from_doc` dùng chung với `adopt_customer_revision`), `sketch_geometry.py` (`mark_edit`, `edit_summary`), `sketch_work.py` (sửa của khách / AI ghi `edited_by`; `order_word_texts` dùng chung), `production_snapshot.py` (kiểm bản duyệt), `staff_schemas.py`, `workshop.py`, `migrations/versions/0025_sketch_documents.py` |
| API | `POST /workshop/orders/{id}/sketches/{version}/edit` (mới); `GET /workshop/orders/{id}/sketches/{version}` thêm `document`, `edit_summary` (FE mục 7t) |
| Test 8 | Khi phát hành snapshot: bản ghi duyệt (U2, bảng chỉ thêm) phải trỏ đúng phác thảo chốt và cùng `content_hash`, lệch → `409 SKETCH_NOT_APPROVED`, không tạo gói, không tạo job. Sau khi khách duyệt, Staff không sửa được nữa (`ORDER_NOT_ACCEPTED`). File quỹ đạo khi tải gói vẫn được so với hash đã ký (U1, có sẵn) |
| Test | `tests/test_v2_staff_editor.py` (7): v1 giữ tài liệu khách (id, dấu CUSTOMER, chữ của từ, hash khớp quỹ đạo); Staff dời một từ → v2 chỉ nét đó đổi, id giữ, dấu STAFF, v1 không đổi, sửa trên v1 → `SKETCH_VERSION_CONFLICT`, ngoài giới hạn / nét lạ / lệnh lạ / thiếu ghi chú / khách gọi → từ chối không tạo phiên bản; phiên bản trước 0025 có tài liệu dựng lại, sửa được, không bị backfill, file quỹ đạo bị đổi → `GEOMETRY_TAMPERED`; file tài liệu bị đổi → `GEOMETRY_TAMPERED`; OT-1 vùng U4 theo sau (vùng sửa → `STAFF`); lát cắt tới snapshot khoá đúng v2 Staff sửa; xếp lịch từ chối phác thảo chốt khác bản duyệt |
| Kết quả test | Cục bộ (Postgres 18) 914 passed, 3 skipped. Supabase THẬT 914 passed, 3 skipped, 0 failed, 1 error teardown (kết nối khoá suite bị đóng sau khoảng 5 giờ, đã sửa `conftest.py`); dữ liệu thật không đổi |
| Chưa làm | Trợ lý AI cho Staff (H-b); hoàn tác trong editor Staff (Staff mở lại phiên bản cũ rồi sửa tiếp, hoặc chốt phiên bản cũ); đọc lại file quỹ đạo ngay lúc phát hành snapshot (hiện so ở mỗi lần tải gói, U1) |

## 14. Phase D: chỉnh cả văn bản trên đơn (2026-11-19, migration 0026, chưa commit)

Chủ dự án duyệt 2026-11-19 theo khuyến nghị: **D-a** định dạng theo đoạn văn = giãn dòng, căn ngang, khoảng trước đoạn (không font riêng); **D-b** vẽ lại khi có nét đã sửa → báo trước, cần `discard_edits` (chưa tự áp lại lệnh sửa); **D-c** lưu form theo lần vẽ, hoàn tác / làm lại kéo theo form (migration 0026); **D-d** một màu mực mỗi đơn; **D-e** trợ lý có `set_layout`, không đổi vật tư / giá.

| | |
|---|---|
| Đã có từ trước (không làm lại) | Cỡ / nghiêng / gạch theo đoạn chữ (`spans`), giãn dòng chung, lề, căn dọc, căn ngang, màu mực trên ảnh xem trước |
| Làm gì | `layout.paragraphs` (`text_layout.py` kiểm, `styled_text.py` vẽ: giãn dòng / căn / khoảng trước theo đoạn, khoảng trước bỏ ở đầu trang); `text_layout.remap` (difflib: định dạng theo phần chữ không đổi, định dạng đoạn theo đoạn giữ / sửa tại chỗ) dùng cho `keep_layout` của form và `update_text` của trợ lý (trước đây xoá hết); `SKETCH_HAS_EDITS` khi vẽ lại đè nét đã sửa; `sketch_revisions.inputs_snapshot` + hoàn tác / làm lại qua lần vẽ khác khôi phục form (chữ, bố cục, canvas, giấy / bút / mực; tính lại giá ước tính; audit `ORDER_INPUTS_RESTORED`), sửa chưa vẽ → `UNDRAWN_INPUT_CHANGES`; công cụ trợ lý `set_layout` |
| Database | Migration 0026 (chỉ thêm): `sketch_revisions.inputs_snapshot JSONB`. Thử lên / xuống / lên cục bộ; **đã áp Supabase**: 69 đơn thật, 34 phác thảo thật, 0 revision làm việc của đơn thật, 1 bản duyệt, 1 snapshot, 15 tài khoản thật, checksum không đổi trước / sau. Script DB tổng tạo lại ở 0026 |
| API | `PUT /orders/{id}/inputs/text` thêm `layout.paragraphs`, `keep_layout`, phản hồi `layout_remap`; `POST .../sketch/generate` body `{discard_edits}`; `POST .../sketch/undo|redo` body `{discard_input_changes}`, phản hồi `inputs_restored` (FE mục 7u) |
| Test 1 | `tests/test_v2_document_level.py` (8): luật đoạn văn (đọc / ghi, 9 trường hợp từ chối); mỗi thiết lập đoạn chỉ dời đúng đoạn đó, đo bằng toạ độ nét (giãn dòng = đúng một bước dòng, khoảng trước = đúng 6 mm, căn phải chạm lề phải); remap giữ định dạng; trên đơn: cỡ một đoạn chữ, giãn dòng đoạn, khoảng trước, căn đoạn, lề, mỗi lần là revision mới đo trên khung từ; từ chối cỡ < 4 mm, đoạn không tồn tại, lề quá lớn không tạo revision; đổi mực không đổi nét nhưng đổi ảnh xem trước; `keep_layout`; `SKETCH_HAS_EDITS`; hoàn tác / làm lại khôi phục chữ, bố cục, giấy; `UNDRAWN_INPUT_CHANGES`; revision trước 0026 chỉ đổi phác thảo; gửi đơn → Staff nhận v1 đúng hash; trợ lý `set_layout` (3 thành công, 2 từ chối), `update_text` giữ định dạng, `generate_sketch` bị chặn khi có nét đã sửa. Không gọi LLM thật |
| Kết quả Supabase | Toàn suite 2026-11-19 14:02 → 16:55: 913 passed, 3 skipped, 9 failed; 9 test trợ lý hỏng vì `ImportError` do code E2b được sửa giữa lượt chạy, không do Phase D. Chạy lại cùng E2b + F |
| Chưa làm | Tự áp lại lệnh sửa nét sau khi vẽ lại (D-b phương án B; làm ở Phase F); nhiều màu mực; font riêng theo đoạn; định dạng cho OT-1 / OT-2; khôi phục ảnh OT-1 khi hoàn tác; trợ lý chưa đo chất lượng chọn `set_layout` với LLM thật |

## 15. Phase E phần 1: đo nhận dạng chữ viết tay (2026-11-19, không đổi code BE / DB, chưa commit)

Chủ dự án duyệt 2026-11-19 theo khuyến nghị: **E-a** cài PyTorch CPU + VietOCR + trọng số `vgg_transformer` trong môi trường đo riêng `benchmarks/.venv-htr` (không vào `requirements`); **E-b** Gemini tối đa 100 lượt trên 50 ảnh công khai; **E-c** tách dòng bằng code tự viết (không PaddleOCR); **E-d** phần 2 (tích hợp) trình riêng sau khi có số đo.

| | |
|---|---|
| Kết quả | Báo cáo `docs/benchmarks/E_htr_benchmark_2026-11-19.md`, script `scripts/benchmark_htr.py`. CER trung vị: **Gemini 0,024**, **VietOCR 0,245**; WER 0,097 / 0,635. Gemini 2,7 s / trang, VietOCR 7,0 s / trang trên CPU, RAM 699 MB |
| Cần lưu ý | 2/50 trang Gemini bị chặn `RECITATION` (trả rỗng; nội dung công khai có trong dữ liệu huấn luyện), nên số của Gemini có thể đẹp hơn với thư thật. Không thấy Gemini tự điền phần bị che; trang trắng / nhiễu trả `[?]`. VietOCR luôn trả ra chữ (trang nhiễu: 370 ký tự vô nghĩa), cần ngưỡng tin cậy |
| Tải về (đã duyệt) | PyTorch CPU 127 MB, OpenCV + các gói phụ thuộc, trọng số VietOCR 152 MB. **Ngoài dự kiến:** VietOCR tự tải mô hình nền ImageNet `vgg19_bn` 548 MB vào `~/.cache/torch` (không cần, đã tắt trong script) |
| Gemini | 59 lượt gọi (57 trang + 2 lần gọi lại), 66.887 token vào, 8.387 token ra |
| Phần 2 cần chủ dự án quyết | Dùng Gemini (gửi ảnh khách ra ngoài, cần đồng ý từng đơn) hay chạy cục bộ (VietOCR chưa đủ tốt, nặng); chỗ dùng: gắn chữ cho vùng OT-1, vùng không chắc → cảnh báo / hỏi khách / chuyển Staff (Test 4, Test 5) |

### 15b. Phase E2a: gắn chữ cho từng vùng U4 (2026-11-19, chỉ đo, không đổi code BE / DB, chưa commit)

Chủ dự án duyệt kế hoạch phần 2 theo khuyến nghị, đổi **E2-d: cho phép chuyển sang Claude khi Gemini lỗi** (chưa có `ANTHROPIC_API_KEY`, nên chưa đo và chưa chạy được). Báo cáo `docs/benchmarks/E2a_htr_regions_2026-11-19.md`.

| | |
|---|---|
| Cách A (bỏ) | Gemini đọc từng khung đánh số trên ảnh: đúng thứ tự chữ nhưng gán nhầm khung (U4 hay cắt một từ thành hai vùng). Thử 3 trang, 10 lượt gọi, dừng |
| Cách B (đề xuất) | Đọc cả trang (bản chép E1, không gọi thêm) + `scripts/htr_align.py` gắn từ vào vùng trên máy (quy hoạch động theo độ rộng chữ, đầu dòng); khớp kém hoặc `[?]` → UNREAD. 0,2 s / trang |
| Kết quả | 6 trang bốc ngẫu nhiên, AI soát bằng mắt: **24/612 = 3,9 % vùng sai** (ngưỡng ≤ 5 %), dồn ở 2 trang có bố cục lạ. 85 % vùng READ. Không bịa chữ (trang trắng / nhiễu bị từ chối). **Trang bị che giữa: 21/52 và 34/67 vùng trượt chữ** trên 2 trang văn xuôi |
| Đề xuất E2b | Chữ theo vùng chỉ là gợi ý cho khách / Staff, kèm READ / UNREAD, không tự đổi nét; UNREAD hoặc khớp kém → cảnh báo / chuyển Staff. Thư hư nặng cần sửa phần gộp mảnh chữ bị cắt và đo lại trước khi bật |

### 15c. Phase E2b: gợi ý chữ cho từng vùng OT-1 (2026-11-19, migration 0027, chưa commit)

| | |
|---|---|
| Quyết định | Gemini gói miễn phí đọc ảnh (chủ dự án chấp nhận gửi ảnh khách; lời xin đồng ý nói Google có thể lưu và dùng ảnh), Claude khi Gemini lỗi / từ chối; khách đồng ý mỗi lần; tắt mặc định (`htr_enabled`), 100 trang / ngày toàn hệ thống |
| Làm gì | Đọc cả trang (prompt E1) → lưu bản chép theo ảnh (`htr_readings`, khoá theo ảnh + xoay + cắt) → gắn từ vào vùng bằng `htr_align` (cách B của E2a) tính khi xem, nên theo được sửa / hoàn tác; `SKETCH_OUTDATED` khi ảnh đổi sau lần vẽ |
| Không làm | Không đổi nét, giá, chữ của vùng; trợ lý không tự gửi ảnh; không xử lý đặc biệt trang bị che (E2a: vẫn trượt chữ nhiều) |
| Database | Migration 0027 (chỉ thêm bảng `htr_readings`), lên / xuống / lên cục bộ, đã áp Supabase, dữ liệu thật không đổi |
| Test | `tests/test_v2_htr_hints.py` (5), bên đọc giả và `httpx.MockTransport`, không gọi LLM thật |
| Supabase | Toàn suite trên Supabase THẬT 2026-11-19: 929 passed, 3 skipped, 0 failed (cùng lượt với Phase F) |
| Chưa kiểm chứng | Gọi Gemini / Claude thật qua code sản phẩm; Claude trên chữ viết tay |

## 16. Phase F: dòng và đoạn, giữ id và lệnh sửa khi vẽ lại (2026-11-19, không migration, chưa commit)

Chủ dự án duyệt 2026-11-19 theo khuyến nghị: **F-a** chỉ dòng và đoạn, không id ký tự; **F-b** giữ id khi vẽ lại cho cả OT-3 và OT-1; **F-c** chỉ áp lại dời / xoay / đổi cỡ / nghiêng trên cả từ; **F-d** thay chữ vùng OT-1 bằng chữ gõ để sau.

| | |
|---|---|
| F1 | `lines` / `paragraphs` mỗi trang. Dòng tìm bằng `htr_align.units_of` (đã đo trên chữ viết tay thật ở E2a) cho mọi loại đơn; đoạn OT-3 lấy từ xuống dòng của văn bản (`TEXT`), OT-1 đoán theo khoảng cách dòng > 1,6 bước dòng hoặc thụt > 2,5 chiều cao chữ (`LAYOUT`). Chọn sửa theo `line_ids` / `paragraph_ids` (khách, trợ lý, Staff) |
| F2 | `carry_ids`: OT-3 so chữ bằng difflib theo thứ tự đọc; OT-1 so khung cùng trang, IoU ≥ 0,5, cặp tốt nhất trước. Từ khớp giữ id, nét giữ id khi cùng số nét; dòng / đoạn giữ id theo đa số; còn lại id mới, không tái dùng |
| F3 | Đi ngược cây revision từ bản hiện tại tới lần vẽ trước, áp lại theo thứ tự cũ các lệnh dời / xoay / đổi cỡ / nghiêng chọn theo từ / dòng / đoạn, qua cùng Geometry Engine và kiểm tra; lệnh khác bỏ với lý do (`OP_NOT_REAPPLIED`, `NOT_WHOLE_WORDS`, `GONE`, mã lỗi). Báo trong `redraw`; một lần hoàn tác về bản trước khi vẽ lại |
| F4 | `report.affected = {strokes, words, lines}` cho mọi lệnh sửa |
| Test | `tests/test_v2_lines_and_redraw.py` (2): OT-3 qua API + trợ lý (vùng chọn theo dòng); OT-1 vẽ lại cùng ảnh, Staff sửa theo dòng |
| Supabase | Toàn suite trên Supabase THẬT 2026-11-19: 929 passed, 3 skipped, 0 failed |
| Giới hạn | Đoạn OT-1 là đoán; từ có số nét đổi (đổi kiểu chữ) giữ id từ nhưng nét nhận id mới; sửa từng nét không được áp lại |

## 17. Phase I: nghiệm thu V2 (2026-11-20, không migration, commit `fcefc44`)

Chủ dự án duyệt 2026-11-20 theo khuyến nghị: **I-a** đọc thật Gemini + Claude trên ảnh công khai; **I-b** tăng tốc test để sau; **I-c** sau Phase I lập kế hoạch OT-2.

| | |
|---|---|
| Test mới | `tests/test_v2_acceptance.py` (9): Test 10 lưu revision lỗi (file / database sau khi đã ghi file) và công cụ trợ lý lưu lỗi; Test 6 gửi đơn hai lần kể cả song song; Test 5 bản đọc bịa; Test 4 ảnh mực phai từ gợi ý tới snapshot và kiểm tra chuyển động |
| Sửa | Khoá dòng đơn khi khách sửa / gửi đơn DRAFT (hai lần gửi song song từng cùng qua); công cụ trợ lý lưu lỗi → `SAVE_FAILED` thay vì hỏng cả lượt; `htr_align` từ chối trang có số chữ > 1,5 × số vùng mực (`TOO_MANY_WORDS`); xếp lịch: deadlock khi hai lịch trùng chèn cùng lúc → thử lại một lần trong savepoint, ra `409 SLOT_CONFLICT` |
| I2 | `docs/benchmarks/I2_htr_product_2026-11-20.md`: Gemini thật qua code sản phẩm, 5 trang công khai, CER 0,018, 505 / 539 vùng có gợi ý. Claude chưa đo: không có `ANTHROPIC_API_KEY` |
| Báo cáo | `docs/benchmarks/V2_acceptance_2026-11-20.md` (10 test → test tự động, phần chưa kiểm chứng) |
| Supabase | Lượt liền: 933 passed, 3 skipped, 5 failed, cả 5 do Supabase đóng kết nối giữa chừng, chạy lại riêng đều qua; không lỗi logic; chưa có lượt 0 failed; dữ liệu thật không đổi |
| Giới hạn | Bản đọc bịa có số chữ / độ dài gần đúng vẫn được gắn (bộ gắn chỉ có hình học); nhánh thử lại khi deadlock chưa thấy chạy trong các lượt test (deadlock hiếm) |
