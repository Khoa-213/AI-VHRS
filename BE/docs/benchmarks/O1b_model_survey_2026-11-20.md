# OT-2 Phase O1(b): khảo sát mô hình sinh nét chữ (2026-11-20)

Câu hỏi: có mô hình công khai nào sinh được **nét bút** (chuỗi điểm, không phải ảnh) theo phong cách một người từ vài mẫu,
dùng được cho tiếng Việt không. Chỉ đọc tài liệu và trang mã nguồn; **chưa tải gì** (Q3: báo trước khi tải).

## Ứng viên

| | SDT (CVPR 2023) | DiffInk (ICLR 2026) | DiffusionPen, One-DM (ECCV 2024) |
|---|---|---|---|
| Mã nguồn | github.com/dailenson/SDT, **MIT** | github.com/awei669/DiffInk, **MIT** | có mã |
| Đầu ra | **Nét bút** (`--store_type online`) hoặc ảnh | **Nét bút** của cả dòng chữ | Ảnh (không phải nét) |
| Đơn vị sinh | Từng ký tự | Cả dòng, có nối chữ | Từ / dòng |
| Mẫu phong cách | Vài ký tự của người viết | Một đoạn mẫu của người viết | 1–5 ảnh mẫu |
| Trọng số có sẵn | Có (Google Drive / Baidu): tiếng Trung, Nhật, Anh | Có (từ 2026-03-21), huấn luyện trên một phần CASIA-OLHWDB (tiếng Trung); README nói trọng số theo giấy phép của bộ dữ liệu | Tiếng Anh (IAM) |
| Tiếng Việt | Không có sẵn | Không có sẵn | Không có sẵn |
| Môi trường | Python 3.8, conda; bản PyTorch chưa đọc được | Python 3.8, conda; bản PyTorch chưa đọc được | - |

Loại DiffusionPen / One-DM: sinh ảnh, muốn ra nét lại phải qua bộ phục dựng U3, và nét đó không phải nét bút thật.

## Dữ liệu chữ viết tay tiếng Việt dạng nét

**HANDS-VNOnDB (ICFHR 2018)**:
- 200 người viết, 1146 đoạn, 7296 dòng, hơn 380.000 ký tự, dạng nét bút có thứ tự.
- Có bản cấp dòng, đoạn và từ. Theo kết quả tìm kiếm, `InkData_line.zip` khoảng 239 MB.
- **Giấy phép:** Creative Commons, "cho mục đích học thuật và nghiên cứu, không dùng thương mại; mục đích khác phải liên hệ
  trước" (theo kết quả tìm kiếm).
- Chưa đọc được trang gốc: tc11.cvc.uab.es từ chối kết nối, trang công cụ trên Google Sites đòi đăng nhập. Vì vậy chưa biết
  bản Creative Commons cụ thể, có phải đăng ký không, và dữ liệu có mã người viết không.

## Đánh giá

1. **Không có mô hình nào dùng ngay được cho tiếng Việt.** Muốn dùng phải huấn luyện lại hoặc tinh chỉnh trên HANDS-VNOnDB.
   Đây là việc nghiên cứu nhiều tuần, không phải một phase sản phẩm.
2. **DiffInk khớp nhất với điểm yếu O1(a) tìm ra (chữ viết liền).** Nó sinh cả dòng có nối chữ. Nhưng mô hình rất mới
   (2026), trọng số có sẵn chỉ cho tiếng Trung, và chưa rõ GPU 8 GB trên máy (RTX 4060 Laptop) có đủ để tinh chỉnh không.
3. **SDT hợp với vai trò FR-36 viết:** "bổ sung ký tự thiếu" trong bộ glyph của hướng A. Trọng số tiếng Anh sinh được chữ
   Latin a–z, còn dấu tiếng Việt vẫn ghép như hướng A. Mẫu phong cách SDT cần là nét bút thật, còn glyph của hướng A là nét
   phục dựng từ ảnh, nên có khoảng cách dữ liệu, phải đo mới biết.
4. **Giấy phép là rào cản cho sản phẩm.** Mã nguồn MIT, nhưng trọng số và dữ liệu đều theo giấy phép bộ dữ liệu: CASIA và
   HANDS-VNOnDB chỉ cho nghiên cứu, không thương mại. Mô hình huấn luyện trên chúng **không được đưa vào sản phẩm có thu
   tiền** nếu tác giả bộ dữ liệu chưa cho phép. Nghiên cứu nội bộ thì được.
5. **Máy hiện tại:**
   - Có GPU RTX 4060 Laptop 8 GB.
   - Môi trường `benchmarks/.venv-htr` (VietOCR) chỉ có PyTorch bản CPU, nên cần một môi trường riêng có CUDA, dùng Python 3.8
     như hai repo yêu cầu.
   - Ổ D còn trống khoảng 64 GB.

## Đề xuất bước kế tiếp (cần chủ dự án quyết)

- **B1, thử nhỏ, không huấn luyện:** tải mã SDT và trọng số tiếng Anh. Lấy vài chữ cái tách được từ O1(a) làm mẫu phong cách,
  rồi sinh chữ thiếu và đo bằng các chỉ số của kế hoạch mục 5.
  - Cần tải: mã SDT (nhỏ), trọng số SDT (dung lượng chưa ghi trong README, sẽ báo khi xem được), PyTorch bản CUDA (khoảng
    2–3 GB).
- **B2, nghiên cứu lớn:** tải HANDS-VNOnDB và tinh chỉnh DiffInk hoặc SDT cho tiếng Việt.
  - Cần đọc được điều khoản gốc của bộ dữ liệu, và đăng ký nếu có yêu cầu. Bước này có thể cần chủ dự án làm, vì trang gốc
    từ chối kết nối tự động.
  - Kết quả chỉ dùng cho nghiên cứu, trừ khi tác giả bộ dữ liệu đồng ý cho dùng thương mại.
- **Khuyến nghị:** làm O2 (phiếu mẫu, hướng A) cho sản phẩm trước. O1(b) dừng ở khảo sát này, cho tới khi có bộ glyph thật
  từ phiếu mẫu để thử B1. B2 chỉ làm nếu chủ dự án muốn theo hướng nghiên cứu (LI-10).

Nguồn: arXiv 2303.14736 (SDT), arXiv 2509.23624 (DiffInk), github.com/dailenson/SDT, github.com/awei669/DiffInk,
tc11.cvc.uab.es/datasets/HANDS-VNOnDB2018_1 (chỉ qua kết quả tìm kiếm), ECCV 2024 DiffusionPen / One-DM.
