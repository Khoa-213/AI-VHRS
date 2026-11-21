# OT-2 Phase O1(a): thu glyph từ trang chữ tự do (2026-11-20)

Câu hỏi: hướng A (dùng lại chữ cái thật của người viết) có lấy được glyph từ một trang chữ tự do không, và glyph lấy được có
mang dấu hiệu của người viết không. Dữ liệu: 50 trang công khai UIT-HWDB (bộ U3 / E1, `benchmarks/data/viet_hw`), không ảnh
khách. Giả định: một trang là một người viết (manifest không có mã người viết; nếu hai trang cùng người thì điểm nhận diện
bên dưới thấp đi, không cao lên). Không gọi mô hình AI nào.

Cách làm: `scripts/benchmark_ot2_glyphs.py`.
- Phục dựng nét và vùng từ bằng code sản phẩm (U3 / U4). Gắn chữ của nhãn người vào vùng bằng `htr_align.match` (E2a: khoảng
  4 % vùng nhận sai chữ).
- Chia từ của trang làm hai nửa theo thứ tự đọc: nửa đầu là "mẫu" để lấy glyph, nửa sau giữ lại để đo.
- Một từ "tách được" khi mực phần thân rơi vào đúng số mảnh liền bằng số chữ cái, và số mảnh nhỏ (dấu thanh, mũ, trăng,
  chấm chữ i / j) đúng bằng số dấu cần. Chỉ từ tách được mới cho glyph.

## Kết quả

| Chỉ số | Kết quả |
|---|---|
| Từ mẫu tách được | **170 / 2661 (6,4 %)**; 4 / 50 trang không có từ nào |
| Từ giữ lại có đủ glyph để viết lại | **269 / 2683 (10,0 %)** |
| Nhận diện người viết: chữ cái thật ở nửa giữ lại, glyph gần nhất (chamfer) thuộc đúng trang của nó | **24 / 211 (11,4 %)**, đoán ngẫu nhiên 11,0 / 211 (5,2 %) |

Lý do từ không tách được, trên cả 5344 từ của 50 trang:

| Lý do | Số từ |
|---|---|
| Thân chữ ít mảnh hơn số chữ cái (viết liền) | 3147 (59 %) |
| Thân chữ nhiều mảnh hơn (nét đứt khi phục dựng) | 619 |
| Thân đúng nhưng số dấu khác | 559 |
| Không có mực (từ không gắn được, `UNREAD`) | 558 |
| Đếm khớp | 461 |

## Kết luận

1. **Không lấy được bộ glyph từ trang chữ tự do.** Phần lớn người viết nối chữ, nên chỉ khoảng 6 % số từ cho glyph và một trang
   chỉ phủ 1–20 chữ cái. Cách này không đủ để viết nội dung mới. Kết quả này ủng hộ Q1 đã chốt: dùng **phiếu mẫu cố định, mỗi
   chữ cái một ô**, không thu glyph từ trang tự do.
2. **Glyph có mang dấu hiệu người viết, nhưng yếu với lượng mẫu này.** Nhận diện đúng gấp khoảng 2,2 lần đoán ngẫu nhiên,
   trên 1–6 mẫu mỗi chữ, và chỉ những chữ người đó viết tách rời. Con số này chưa nói được bộ glyph từ phiếu mẫu sẽ giống
   người viết đến đâu.
3. **Chưa đo được:** đọc được (Gemini đọc chữ ghép) và robot viết được. Không trang nào có đủ chữ để viết lại một đoạn, nên
   không có gì để đo. Hai chỉ số này chuyển sang O2, đo trên phiếu mẫu thật.

## Việc kế tiếp đề xuất

- **O2 cần một phiếu mẫu thật do người đồng ý viết** (chủ dự án hoặc thành viên nhóm, không phải khách), để đo cả bốn chỉ số
  của kế hoạch mục 5 trên đúng dữ liệu sản phẩm sẽ nhận.
- **O1(b)** (mô hình sinh nét) là hướng duy nhất xử lý được chữ viết liền. Theo Q3, trước khi tải sẽ báo tên, nguồn, dung
  lượng và giấy phép.

Dữ liệu trung gian ở `benchmarks/data/ot2/` (không commit). Chạy lại: `.venv/Scripts/python.exe scripts/benchmark_ot2_glyphs.py`
(khoảng 5 phút, không gọi mạng).
