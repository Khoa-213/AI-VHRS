# V2 Phase E2a: gắn chữ cho từng vùng U4 (2026-11-19)

Câu hỏi của E2-e: gắn chữ đọc được vào từng vùng U4 của trang OT-1 có đủ đúng không (≤ 5 % vùng sai, không vùng nào bị bịa chữ). 50 trang công khai của U3 (như `E_htr_benchmark_2026-11-19.md`), vùng do bộ phục dựng thật tính (A4, lề 10 mm).

## Cách A (bỏ): Gemini đọc từng khung đánh số

Khung + số của từng vùng vẽ lên ảnh, Gemini trả JSON {số khung: chữ}. Thử 3 trang (884, 42, 119), 10 lượt gọi (`scripts/benchmark_htr_regions.py`). Gemini đọc đúng **thứ tự** chữ nhưng **gán nhầm khung**: U4 hay cắt một từ thành hai vùng ("h" + "ỏi", "th" + "ành"), Gemini lại đặt cả từ vào một khung rồi trượt sang khung sau (trang 884 dòng 2: từ khung 28 trở đi lệch 1–2 khung), có từ bị chép vào hai khung. Đo theo dóng hàng từ đã ra 62/591 vùng sai, và cách đo đó còn không thấy lỗi lệch khung, nên số thật cao hơn. Khung giả trên dải bị che: 0/15 bị điền chữ. Không chạy tiếp 47 trang còn lại.

## Cách B (đang đề xuất): đọc cả trang, gắn chữ vào vùng trên máy

- Bản chép cả trang: kết quả Gemini của E1 (đã có, **không gọi thêm lượt nào**).
- Gắn chữ: `scripts/htr_align.py` (Python thuần, không thêm thư viện). Vùng → dòng (theo dõi dòng chạy xiên, đuôi chữ "g" / "y" về đúng dòng) → đơn vị (vùng chồng nhau như dấu trên chữ là một) → quy hoạch động khớp từng từ với 1–4 đơn vị liền nhau theo độ rộng chữ dự kiến, cho phép bỏ vùng nhiễu / từ không có mực; đầu dòng của bản chép phải rơi vào đầu dòng mực. Từ khớp kém hoặc bản chép ghi `[?]` → vùng **UNREAD** (không đoán).
- Bộ gắn chữ được chỉnh trên 3 trang 884, 42, 119; sau đó **đóng băng** (sha256 `569a42ab841b…`) rồi mới bốc ngẫu nhiên 6 trang khác để soát. Hai sửa đổi sau đó đều do trang bị che lộ ra: `[?]` / `...` là chỗ trống chứ không phải một từ (6 trang không đổi vùng nào), và hai "dòng" cùng độ cao tại chỗ là một dòng (chỉ đổi 9 vùng của trang 1223, đã soát lại). Bản hiện tại `8051c2bdb453…`.

### Đúng / sai theo từng vùng (soát bằng mắt, trang chưa dùng để chỉnh)

Không có đáp án theo vùng nên mỗi trang được vẽ thành bảng kiểm (khung từng nhóm vùng + chữ được gắn) và soát từng nhóm. **Người soát là AI (Claude), không phải người**; chỉ tính lỗi gắn sai chỗ và vùng nhận thiếu / thừa chữ, không tính lỗi chính tả do Gemini đọc sai một chữ (đã đo ở E1, CER 0,024).

| Trang | Vùng READ | Vùng sai | Ghi chú |
|---|---|---|---|
| 941 | 107 | 2 (1.9%) | một vùng rộng chứa 4 chữ "xác đến từng chi": chữ "chính" bị bỏ, 2 vùng nhận chữ lệch |
| 503 | 35 | 0 (0.0%) | – |
| 705 | 136 | 15 (11.0%) | dòng cuối viết chèn sát bên dưới ("địa này, anh à.") bị gộp vào dòng trên, cả dòng lệch |
| 347 | 109 | 0 (0.0%) | – |
| 111 | 118 | 0 (0.0%) | – |
| 1223 | 107 | 7 (6.5%) | một dòng dốc lên bị tách đôi; "không" bị bỏ, 7 vùng ở cuối dòng 1 / đầu dòng 2 lệch |
| **Tổng 6 trang, bản đóng băng** | **612** | **24 = 3.9%** | ngưỡng E2-e ≤ 5 %; số dùng để so ngưỡng |
| Tổng 6 trang, bản hiện tại | 614 | 17 = 2.8% | 1223: dòng dốc lên nay là một dòng; 9 vùng đổi chữ đều đúng; sửa sau khi đã thấy trang nên không dùng số này để so ngưỡng |

### Phủ vùng và thời gian (50 trang, không cần đáp án)

| Chỉ số | Giá trị |
|---|---|
| Vùng READ / tổng | 5742/6760 = 84.9% |
| Trang không có bản chép (Gemini chặn `RECITATION`) → toàn bộ UNREAD | 400, 1186 |
| Vùng READ trên trang có bản chép, trung vị / thấp nhất | 92.9% / 53.8% |
| Thời gian gắn chữ / trang, trung vị / lớn nhất | 0.18 s / 1.09 s (phục dựng: 1.0 s) |

### Bịa chữ (Test 5)

| Trang | Vùng | READ | Ghi chú |
|---|---|---|---|
| blank | 0 | 0 | bản chép E1 là `[?]`; phục dựng từ chối ảnh (`NO_STROKES_FOUND`) |
| noise | 0 | 0 | bản chép E1 là `[?]`; phục dựng từ chối ảnh (`IMAGE_TOO_NOISY`) |
| masked_884 (che 1/3 giữa) | 111 | 68 | so với cùng chỗ trên trang đủ: 31 giống, **21 khác**, 16 không so được; ví dụ chăng → chăng...; thời → cho; gian → bạn; gian → bạn |
| masked_42 (che 1/3 giữa) | 193 | 181 | so với cùng chỗ trên trang đủ: 134 giống, **13 khác**, 34 không so được; ví dụ Xã → xã; Lộ → lộ; 28-P. → 28; 28-P. → V, |
| masked_119 (che 1/3 giữa) | 159 | 150 | so với cùng chỗ trên trang đủ: 111 giống, **9 khác**, 30 không so được; ví dụ Lìn, → Lin,; Tung → Tông; Huyện → huyện; Hòa, → Xã |
| masked_433 (che 1/3 giữa) | 101 | 86 | so với cùng chỗ trên trang đủ: 33 giống, **34 khác**, 19 không so được; ví dụ cơ → giọng; tự → Chú; sở → xem; hào: → đó , |
| masked_400 (che 1/3 giữa) | 133 | 92 | so với cùng chỗ trên trang đủ: 0 giống, **0 khác**, 92 không so được |

Cách B không tự sinh chữ: chữ chỉ đến từ bản chép cả trang; vùng không có chữ tương ứng thì UNREAD. Bịa chữ chỉ có thể đến từ bản chép, và E1 không thấy Gemini điền phần bị che (5 trang) hay chép chữ từ trang trắng / nhiễu. Trên trang bị che, một vùng nhận chữ khác với trang đủ là từ bị đặt nhầm chỗ, không phải chữ bịa.

## Đọc kết quả

- **Trang viết bình thường: đạt ngưỡng nhưng sát.** 24/612 = 3,9 % vùng sai trên 6 trang bốc ngẫu nhiên (≤ 5 %). Lỗi không rải đều mà dồn theo cụm: 4/6 trang 0–2 %, còn 705 (11 %) và 1223 (6,5 %) mỗi trang có một chỗ bố cục lạ (dòng viết chèn sát bên dưới, dòng dốc bị tách đôi) làm cả đoạn sau lệch. Mẫu chỉ 6 trang / 612 vùng, khoảng tin cậy rộng; người soát là AI.
- **Trang bị che giữa (thay cho thư hư, mực phai): chưa ổn.** So với chính trang đó khi đủ, 21/52 vùng (884) và 34/67 vùng (433) nhận chữ khác, phần lớn là trượt chữ sang vùng bên cạnh; trang danh sách địa chỉ (42, 119) ít hơn (13/147, 9/120) và nhiều khác biệt ở đó chỉ là Gemini đọc lại khác (`Xã` → `xã`). Nguyên nhân thấy được: mép dải che cắt ngang chữ, bộ phục dựng gộp mảnh chữ bị cắt với chữ bên dưới thành một vùng, bản chép thì có `[?]`, nên số từ và số vùng không còn tương ứng. Thư OT-1 thật hay bị phai / rách từng mảng, nên đây là trường hợp sẽ gặp.
- **Không bịa chữ:** chữ chỉ đến từ bản chép; trang trắng / nhiễu bị phục dựng từ chối trước khi đọc; E1 không thấy Gemini điền phần bị che. Rủi ro còn lại là **đặt chữ đúng vào chỗ sai**, không phải chữ không có trên giấy.
- **UNREAD thay vì đoán:** 15 % vùng không nhận chữ (trang có bản chép: trung vị 7 %), chủ yếu là chữ in hoa (rộng hơn dự kiến), dấu rời, số nhà. 2/50 trang Gemini chặn `RECITATION` nên cả trang UNREAD (trang công khai có trong dữ liệu huấn luyện; thư thật ít gặp hơn nhưng chưa đo).
- **Chi phí:** gắn chữ 0,2 s / trang trên máy, không gọi thêm API, không thêm thư viện; một lượt Gemini cho cả trang như E1 (khoảng 1.100 token vào, 150 token ra mỗi trang).

**Đề xuất cho E2b:** dùng cách B, nhưng chỉ coi là **gợi ý có kiểm tra**: hiện chữ gợi ý theo vùng cho khách / Staff kèm trạng thái READ / UNREAD, không tự đổi nét hay tự xác nhận; trang có vùng UNREAD hoặc chi phí khớp cao → cảnh báo / chuyển Staff. Trước khi bật cho thư hư nặng cần sửa phần gộp mảnh chữ bị cắt và đo lại trên trang bị che. Phần gọi Claude khi Gemini lỗi (E2-d) chưa đo được vì chưa có `ANTHROPIC_API_KEY`.
