# OT-1 phục dựng v2: loại nhiễu và đo độ giống đúng (kế hoạch đã duyệt, R0–R4 xong)

Trạng thái: **chủ dự án DUYỆT Q1–Q5 theo khuyến nghị ngày 2026-11-21** (yêu cầu cùng ngày: độ giống khoảng 80 %, sửa lỗi ở
ảnh thư có dòng kẻ, thiết kế chi tiết mô hình phục dựng loại bỏ tác nhân gây nhiễu). R0–R4 xong; v2 nằm sau tham số Admin `ot1_recovery_engine`; **mặc định v2 từ 2026-11-22** (chủ dự án yêu cầu), `v1` giữ để quay lui. Tiến độ ở mục 8.

## 1. Hiện trạng và chẩn đoán (đo 2026-11-21, ảnh chủ dự án gửi, chạy ở máy, không ghi DB)

| | Ảnh 1: thư cũ, giấy vở có dòng kẻ, rách, gấp | Ảnh 2: phong bì, giấy trơn, nền gỗ (đã cắt vùng) |
|---|---|---|
| Kích thước ảnh sau khi đọc | 740 × 851 px (ảnh nhỏ) | 1530 × 615 px |
| Số nét / số chữ (ước) | 1.198 / ~300 | 272 / ~110 |
| "Độ giống" hiện tại (IoU pixel, nét đều) | 50,2 % | 60,9 % |
| IoU nếu vẽ lại theo bề rộng nét thật từng điểm | 57,0 % | 50,3 % |
| **F1 với dung sai 2 px** (nét dò được so với mực đã tách) | **98,4 %** (P 99,6, R 97,1) | **98,3 %** (P 99,7, R 97,0) |
| Phần "mực" là đường ngang dài (dòng kẻ) | ≥ 12,9 % (đo thiếu vì dòng kẻ bị chữ cắt) | 0 % |

Kết luận:
1. **Bước dò nét gần như đúng hoàn toàn với ảnh mực nó nhận được** (F1 98 % ở dung sai 2 px). Con số 50–60 % thấp chủ yếu
   do cách đo: IoU từng pixel của nét mảnh 2–3 px rất nhạy với lệch 1 px. Bài đo U3 (2026-11-12) đã thấy điều này
   (62–69 % dù dò đúng) và cảnh báo `SIMILARITY_BELOW_80` đã bị tắt vì thế.
2. **Cái sai thật nằm trước đó, ở bước quyết định đâu là mực.** Ảnh 1 có độ giống 50 % nhưng nét sinh ra là rác: dòng kẻ,
   mép rách, nếp gấp, mép phông nền đều được coi là mực, và thước đo hiện tại **không thấy** điều đó vì nó so nét với
   chính ảnh mực bị lẫn nhiễu. Tức là đẩy con số hiện tại lên 80 % không làm bản phục dựng tốt hơn.
3. Ảnh 2: thiếu nắn phối cảnh (nghiêng ~9°, chỉ bù được 5°), nét thanh của chữ hoa kiểu thư pháp dính cục, chữ bị co vào A5
   nên sai kích thước thật, ảnh không cắt thì vân gỗ thành nét.

Vì vậy kế hoạch làm hai việc song song: **đổi thước đo** để 80 % có nghĩa là "giống bản gốc thật", và **thêm tầng loại nhiễu**
trước bước dò nét.

## 2. Mục tiêu (đặt trước khi đo, không chỉnh sau)

- **Độ giống v2 ≥ 80 %** trên bộ benchmark (mục 4), đo so với **mặt nạ mực đúng (ground truth)**, không so với ảnh mực
  do chính bộ phục dựng tách ra.
- **Tỷ lệ nét rác ≤ 5 %** (độ dài nét sinh ra nằm ngoài mực thật) trên mọi nhóm nhiễu; từng nhóm nhiễu (dòng kẻ, nếp
  gấp, rách, nền, nghiêng, ảnh nhỏ) đạt F1 ≥ 75 %.
- Ảnh 1: không còn nét nào là dòng kẻ, mép rách, nếp gấp hay phông nền; chỗ rách mất chữ được đánh dấu `RESTORED`.
- Ảnh 2: nắn thẳng, không còn nét từ nền gỗ khi **không cắt tay**; nét thanh không dính cục.
- Không chậm quá 5 giây / trang trên Render; không thêm thư viện pip vào sản phẩm.
- Nếu không đạt 80 % thì báo đúng số đo, không đổi mục tiêu hay thước đo sau khi đo.

## 3. Thiết kế bộ phục dựng v2 (hướng A: thị giác máy cổ điển, trong sản phẩm)

Mỗi tầng xuất ra một **mặt nạ** và **lý do bỏ** để Staff xem lại được (không lặng lẽ xoá).

```
ảnh → S0 kiểm chất lượng → S1 tìm tờ giấy, nắn phối cảnh, mặt nạ giấy → S2 làm phẳng sáng / bóng
    → S3 mô hình màu mực → S4 bỏ dòng kẻ (giữ chỗ nét cắt qua) → S5 bỏ nếp gấp, mép rách, vết bẩn
    → S6 nhị phân thích nghi có trễ → S7 phân loại từng mảnh mực / nhiễu → S8 dò nét (giữ bộ hiện tại, sửa nét thanh)
    → S9 đặt đúng kích thước thật → S10 độ tin cậy vùng v2 + độ giống v2
```

**S0. Kiểm chất lượng ảnh.** Dùng lại `handwriting_image` (nét, sáng, tương phản). Thêm: cạnh ngắn của **vùng giấy** < 1.200
px thì cảnh báo `LOW_RESOLUTION` (ảnh 1 chỉ 740 px: nét 2,8 px, khó tách khỏi dòng kẻ). Không chặn, chỉ cảnh báo khách
chụp lại.

**S1. Tìm tờ giấy và nắn phối cảnh.**
- Giấy là vùng sáng, ít bão hoà màu, liền khối, lớn nhất. Ngưỡng trên kênh L (Lab) + độ bão hoà, đóng mở hình thái học,
  lấy các thành phần lớn.
- Một tờ nguyên (ảnh 2): xấp xỉ đường viền thành tứ giác → `getPerspectiveTransform` → ảnh thẳng, đúng tỉ lệ cạnh.
- Giấy rách nhiều mảnh (ảnh 1): mặt nạ = hợp các mảnh; nắn theo `minAreaRect` của hợp (không ghép mảnh, không đoán phần
  mất). Lỗ thủng / phần thiếu bên trong khung giấy → **vùng mất** (dùng ở S10).
- Ngoài mặt nạ giấy: không bao giờ là mực (bỏ nền gỗ, phông, bóng tay). Một **dải mép** rộng ~2 × bề rộng nét dọc mép giấy
  và mép rách: mực chỉ được giữ nếu nối tiếp từ bên trong (mép rách không thành nét).
- Không tìm được giấy (ảnh chụp sát, không thấy mép) → giữ cả ảnh như hiện nay, ghi `PAPER_NOT_FOUND` trong cảnh báo.
- `crop_box` và xoay 90° của khách vẫn áp trước S1; S1 thay cho việc khách phải cắt tay chính xác.

**S2. Làm phẳng sáng và bóng.** Giữ `_flatten` nhưng chỉ tính nền trong mặt nạ giấy (nền gỗ không kéo lệch); hạt nhân lớn
hơn cho bóng nếp gấp; giấy ố vàng được chia về trắng.

**S3. Mô hình màu mực (theo từng ảnh).**
- Lấy các điểm tối hơn giấy trong mặt nạ, đổi sang Lab, gom cụm (k-means 2–4 cụm trên a, b, L) bằng OpenCV.
- Gán nhãn cụm bằng đặc trưng hình học của chính các điểm trong cụm: cụm nằm trên các đường ngang dài cách đều = **dòng
  kẻ**; cụm đậm, nét cong, độ rộng thay đổi = **mực bút**; cụm rất nhạt, rộng, mép mờ = **bóng / vết bẩn**.
- Kết quả: bản đồ **xác suất mực** 0–1 cho mỗi pixel (màu + độ tối), thay cho một ngưỡng Otsu duy nhất.
- Bút cùng màu với dòng kẻ (bút xanh nhạt trên kẻ xanh): S3 không tách được, S4 dựa vào hình học.

**S4. Bỏ dòng kẻ, giữ chỗ nét chữ cắt qua.**
- Sau S1 ảnh đã thẳng: tìm đường gần ngang bằng mở hình thái học (phần tử dài ~1/12 bề rộng) + chiếu ngang; xác nhận bằng
  **khoảng cách đều** (vở kẻ: các dòng cách nhau gần bằng nhau) và độ dày đều. Tương tự cho lề dọc (thường đỏ).
- Pixel trên dải dòng kẻ bị bỏ, **trừ chỗ có nét chữ đi qua**: có mực liền mạch ngay trên và ngay dưới dải (vượt quá bề dày
  dòng kẻ) và hướng nét hai bên khớp nhau → nối nét qua dải bằng nội suy thẳng.
- Nét chữ nằm sát và song song dòng kẻ (gạch chân, dấu ngã dài): giữ nếu màu thuộc cụm mực S3; ghi vào lý do để Staff xem.

**S5. Nếp gấp, mép rách, vết bẩn.**
- Nếp gấp: đường mảnh dài (≥ 25 % cạnh trang), gần thẳng, tương phản thấp, thường có dải bóng bên cạnh. Tìm bằng bộ lọc
  đường gờ Hessian (tự viết bằng numpy / OpenCV) ở thang ≥ bề rộng nét, lọc theo độ dài và độ thẳng → mặt nạ bỏ; chỗ nét
  chữ cắt qua xử lý như S4.
- Mép rách bên trong khung giấy: đã có từ S1 (dải mép).
- Vết bẩn / ố: mảnh mực to, đặc, mép mờ, không giống nét bút (độ đặc cao, độ rộng nét lớn gấp nhiều lần nét trung vị) →
  bỏ, ghi lý do.

**S6. Nhị phân thích nghi có trễ.** Sauvola (tự viết, dùng tích phân ảnh của OpenCV) trên bản đồ xác suất mực: ngưỡng cao
tạo hạt, ngưỡng thấp mở rộng theo liên thông (hysteresis). Thay cho Otsu + "mực nhạt" hiện tại, giữ được nét thanh và chữ
mờ mà không lấy thêm nền.

**S7. Phân loại từng mảnh: mực hay nhiễu.** Mỗi thành phần liên thông có đặc trưng: diện tích, độ dài khung xương, độ rộng
nét trung vị và độ lệch, độ thẳng, hướng, màu (cụm S3), khoảng cách tới mép giấy, có nằm trên dòng kẻ / nếp gấp không. Một
bộ luật có điểm (không học máy) cho ra `INK` / `NOISE` kèm lý do. Mảnh bị bỏ được lưu lại (toạ độ + lý do) để Staff bật lại
nếu là chữ.

**S8. Dò nét.** Giữ Zhang-Suen + đồ thị + ghép nét hiện tại (F1 98 % ở bảng trên). Sửa:
- Nét thanh dính nét đậm (chữ hoa thư pháp ảnh 2): làm mảnh ở hai mức ngưỡng; nét thanh tách được thì dò riêng.
- Cắt gai theo bề rộng nét thật thay cho một hằng số.

**S9. Kích thước thật.** Khi S1 tìm được giấy và khách chọn khổ giấy, quy đổi mm / px theo cạnh giấy thật, đặt chữ **đúng
vị trí và kích thước** như bản gốc thay vì co vào khổ. Không tìm được giấy thì giữ cách hiện tại.

**S10. Độ tin cậy vùng v2 và độ giống v2.**
- Vùng có nét bị nối qua dòng kẻ / nếp gấp, nằm sát vùng mất, hoặc có mảnh bị S7 bỏ bên trong → hạ độ tin cậy, nhãn
  `RESTORED` để Staff xem. Vùng toàn dòng kẻ không còn (S4), nên không còn vùng "rác" được chấm 1,00 như ảnh 1.
- **Độ giống v2 hiển thị trong sản phẩm** = F1 có dung sai (τ = nửa bề rộng nét, tối thiểu 1 px) giữa nét vẽ lại và mặt nạ
  **mực đã làm sạch**. Trong sản phẩm không có mặt nạ đúng, nên con số này chỉ nói "nét khớp mực đã tách". Chất lượng tách
  mực được bảo đảm bằng benchmark mục 4.
- Ngưỡng độ khó `suggest_complexity` (độ giống < 70 → COMPLEX, ≥ 85 → SIMPLE) phải hiệu chỉnh lại theo thước đo mới
  trên benchmark (giả định, Manager xem lại).

**Tương thích và quay lui.** `ENGINE_VERSION` "1" → "2"; phác thảo cũ giữ nguyên từng byte. Cờ `system_settings`
`ot1_recovery_engine` (`v1` / `v2`, mặc định `v1` tới khi chủ dự án bật). Không đổi schema; `sketch_regions.metrics` thêm
khoá (JSON có sẵn). API: thêm `noise_removed` (danh sách mảnh bị bỏ + lý do) cho Staff (thực tế R4: nằm trong `trajectory.engine.pages[]`, không thêm trường API); FE có thể vẽ lớp này.

## 4. Đo thế nào

**Bộ benchmark (dựng bằng script, có hạt giống cố định, ghi rõ là tổng hợp).**
- Nguồn chữ sạch: các trang chữ viết tay công khai đã dùng ở E1 / O1 (đã được phép, không tải thêm). Trang sạch nền trắng →
  nhị phân → **mặt nạ đúng**.
- Ghép nhiễu có kiểm soát, mỗi loại một nhóm và một nhóm trộn: giấy vở dòng kẻ (xanh / tím / xám, cách dòng 7–10 mm, lề
  đỏ), nếp gấp (đường bóng + gờ), rách (cắt mặt nạ, xoay lệch mảnh), nền gỗ / vải / bàn (ảnh nền sinh bằng nhiễu, không tải),
  nghiêng phối cảnh 0–15°, ố vàng, ảnh nhỏ (cạnh ngắn 700–900 px), bút cùng màu dòng kẻ.
- Khoảng 200 ảnh. Đây là ảnh **tổng hợp**, chỉ dùng để so v1 / v2 và tìm lỗi, không thay cho đo trên ảnh thật.
- **Ảnh thật:** 2 ảnh chủ dự án gửi (và ảnh thêm nếu có), lưu ở `benchmarks/data/` (không commit). Mặt nạ đúng cho ảnh
  thật cần người tô / duyệt (Q2).

**Số đo (cố định trước khi đo).**
- Độ giống v2 = F1@τ so với mặt nạ đúng (τ = nửa bề rộng nét, ≥ 1 px).
- Tỷ lệ nét rác = độ dài nét sinh ra cách mực thật > τ, chia tổng độ dài.
- Độ phủ = phần mực thật có nét đi qua trong τ.
- Số nét, thời gian / trang, số vùng `RESTORED`.
- Báo cáo `docs/benchmarks/OT1v2_*.md`: v1 so với v2, theo từng nhóm nhiễu, kèm ảnh.

## 5. Các phase

| Phase | Nội dung | Đầu ra | DB |
|---|---|---|---|
| **R0 Đo trước** | Script dựng benchmark, độ giống v2, đo **v1** làm mốc (cả 2 ảnh thật) | `docs/benchmarks/OT1v2_R0_*.md` | Không |
| **R1 Giấy** | S0, S1, S2, S9: tìm giấy, nắn phối cảnh, mặt nạ, dải mép, kích thước thật | Test + đo lại | Không |
| **R2 Dòng kẻ** | S3, S4, S6: mô hình màu, bỏ dòng kẻ giữ chỗ cắt, nhị phân thích nghi | Test + đo lại | Không |
| **R3 Nhiễu còn lại** | S5, S7, S8: nếp gấp, vết bẩn, phân loại mảnh, nét thanh | Test + đo lại | Không |
| **R4 Sản phẩm** | S10, cờ `ot1_recovery_engine`, `noise_removed` trong API, ngưỡng độ khó mới, `FE_API_GUIDE.md` | Toàn suite Supabase | Thêm 1 dòng `system_settings` (chỉ thêm). Thực tế (R4): không cần, tham số có mặc định trong code, dòng chỉ có khi Admin đổi |
| **R5 (tuỳ chọn) Mô hình học** | Chỉ khi R3 chưa đạt 80 %: mạng tách mực nhỏ (U-Net), huấn luyện ngoài sản phẩm trên benchmark tổng hợp, xuất ONNX, chạy bằng `cv2.dnn` (OpenCV đã có, không thêm pip) | Kế hoạch + duyệt riêng | Không |

Mỗi phase báo số đo cho chủ dự án trước khi sang phase sau.

## 6. Rủi ro

- Bút cùng màu và cùng độ đậm với dòng kẻ: chỉ còn hình học, nét ngang trùng dòng kẻ có thể bị bỏ (S7 giữ lại cho Staff bật).
- Ảnh nhỏ như ảnh 1 (740 px): nét chỉ 2–3 px, giới hạn vật lý; cảnh báo chụp lại là cách chắc nhất.
- Chữ bị mất ở chỗ rách: FAITHFUL không bịa; ASSISTED chỉ đánh dấu, phần viết bù vẫn là việc của Staff / HTR gợi ý.
- 80 % trên benchmark tổng hợp chưa chắc là 80 % trên thư thật; con số thật phụ thuộc Q2.
- Thời gian: S1–S7 thêm khoảng 1–2 giây / trang (ước tính, sẽ đo).

## 7. Câu hỏi cho chủ dự án

| | Câu hỏi | Khuyến nghị |
|---|---|---|
| Q1 | Đổi "độ giống" sang F1 có dung sai, đo so với mặt nạ mực đúng trên benchmark (mục 2–4), mục tiêu ≥ 80 %? | Có. IoU pixel hiện tại không phản ánh chất lượng (ảnh rác vẫn 50 %, ảnh sạch dò đúng 98 % vẫn chỉ 61 %) |
| Q2 | Mặt nạ đúng cho ảnh thật: ai tô? | AI tạo mặt nạ nháp từ v2, chủ dự án / Staff sửa và duyệt trên 2 ảnh hiện có + 5–10 ảnh thư cũ thêm nếu có |
| Q3 | Dùng 2 ảnh vừa gửi để đo (lưu `benchmarks/data/`, không commit, không gửi ra ngoài)? | Có |
| Q4 | Thứ tự R0 → R4, R5 chỉ khi chưa đạt? | Có; OT-1 dùng v1 tới khi chủ dự án xem số đo R4 và tự bật v2 |
| Q5 | Kích thước thật (S9): cần khổ phong bì (DL 220 × 110 mm…)? | Để sau: hiện BR-07 chỉ A4 / A5 / A6; thêm khổ là đổi nghiệp vụ, hỏi riêng |

## 8. Tiến độ

- **R0 xong (2026-11-21, commit `a659f44`):** `scripts/benchmark_ot1v2.py`, báo cáo `docs/benchmarks/OT1v2_R0_baseline_2026-11-21.md`.
  220 ảnh tổng hợp (22 nguồn chữ thật × 10 nhóm nhiễu, có mặt nạ đúng). Mốc v1: F1 v2 **71,5 %** chung, tỷ lệ rác 29,4 %;
  nền gỗ 24,6 %, trộn 23,2 %, dòng kẻ khó 67,5 %, dòng kẻ cùng màu 75,0 %; ảnh sạch 89,3 % nhưng độ phủ chỉ 84 % (đầu nét bị cắt,
  đường tâm lệch). IoU cũ không phân biệt được ảnh sạch và ảnh toàn rác (66 % cả hai). Tiếp theo: R1 (tờ giấy).

- **R1 xong (2026-11-21, commit `a659f44`):** `app/services/stroke_ai/paper.py`, `recovery_v2.py` (chưa nối vào sản phẩm), `tests/test_ot1v2_paper.py` (7 test), báo cáo `docs/benchmarks/OT1v2_R1_paper_2026-11-21.md`.
  F1 v2 chung **81,7 %** (v1 71,5 %), nền gỗ 24,6 → 85,5 %, trộn 23,2 → 64,6 %, rác 29,4 → 17,3 %; 7 nhóm còn lại không đổi.
  Chưa đạt: từng nhóm ≥ 75 % (mixed, ruled_hard) và rác ≤ 5 %. Đổi so với kế hoạch: LOW_RESOLUTION đo bề rộng nét (và luật này hầu như không bật, cần cách đo khác), giấy rách lấy khung bao không xoay. Tiếp theo: R2 (dòng kẻ, nếp gấp, ố).
- **R2 xong (2026-11-21, commit `a659f44`):** `app/services/stroke_ai/ruling.py` (S4), `tests/test_ot1v2_ruling.py` (5 test), báo cáo `docs/benchmarks/OT1v2_R2_ruling_2026-11-21.md`.
  F1 v2 chung **85,4 %** (R1 81,7 %), ruled_hard 67,5 → 84,7 %, ruled_same 75,0 → 87,4 %, mixed 64,6 → 69,4 %, rác 17,3 → 9,3 %. 9 / 10 nhóm ≥ 75 %; chưa đạt: mixed, rác ≤ 5 %.
  Đổi so với kế hoạch: S6 (nhị phân có trễ) thử và bỏ (loang bóng nếp gấp), S3 (màu mực) dời sang R3; ngưỡng lưới dọc 15 % chọn khi xem ảnh thư thật. Thư thật: 649 nét (v1 1.198), dòng kẻ gần hết, dòng ngày đã dò được. Sửa thêm: seed GrabCut cố định (kết quả từng ảnh không còn phụ thuộc thứ tự chạy). Tiếp theo: R3.
- **R3 xong (2026-11-22, commit `a659f44`):** `app/services/stroke_ai/folds.py` (S5), rim + luật dải mép áp lại trong `recovery_v2.py`, S8 (làm mượt 3 / 0,4 px, 2.000 px), `ruling.DARKER`; `tests/test_ot1v2_r3.py` (5 test); báo cáo `docs/benchmarks/OT1v2_R3_noise_2026-11-22.md`.
  F1 v2 chung **92,9 %** (R2 85,4 %), mixed 69,4 → 85,6 %, cả 10 nhóm ≥ 85 %, rác chung 9,3 → 4,1 %; 217 / 220 ảnh tốt hơn > 2 điểm, 0 ảnh kém hơn. Chưa đạt: rác ≤ 5 % trên mọi nhóm (tear 10,3 %, mixed 12,5 %).
  Đổi so với kế hoạch: S7 thay bằng luật hình học (không dùng màu); đường nét nhiều hơn 40 % điểm. Thư thật: 682 nét, tiêu đề, ngày và các dòng giữa đều được dò (đính chính R2: ngày khi ấy chỉ được một phần); còn dòng kẻ trong vùng bóng gập. Thời gian máy dev ≤ 2,7 s / trang, Render chưa đo. Tiếp theo: R4 (R5 không cần theo điều kiện < 80 %).
- **R4 xong (2026-11-22, commit `a659f44`):** tham số Admin `ot1_recovery_engine` (v1 mặc định, không đổi DB), `engine.generate_ot1(recovery_engine)`, độ giống v2 `ink_f1` (F1 có dung sai so với mực đã làm sạch), `noise_removed` trong `trajectory.engine.pages[]`; `tests/test_ot1v2_product.py` (5) + 1 test API; báo cáo `docs/benchmarks/OT1v2_R4_product_2026-11-22.md`.
  Toàn suite Supabase THẬT 976 passed, 3 skipped, 0 failed (60,2 phút). **Ngưỡng độ khó không hiệu chỉnh được:** độ giống v2 96–99 % trên mọi ảnh, tương quan 0,30 với F1 thật; chủ dự án chọn (b) 2026-11-22: với v2 gợi ý K_cx không dùng độ giống (chỉ nhấc bút / ký tự, loại bút). Chưa đo thời gian trên Render.
- **Sau R4 (2026-11-22, chưa commit):** làm mảnh bằng bảng tra (giống hệt, nhanh hơn ~1,5–2 lần ở v1); giữ thân chữ L / T nằm trùng đường lưới dọc nhạt (`ruling.DARKER_SHORT_*`). Benchmark 92,89 % (không đổi). Chi tiết: `docs/benchmarks/OT1v2_R4_product_2026-11-22.md` mục 5.
- **Mặc định v2 (2026-11-22, chủ dự án yêu cầu, chưa commit):** `ot1_recovery_engine` mặc định `"v2"`, không đổi DB. Bỏ qua bước đo trên Render trước khi bật (giới hạn mục R4 báo cáo còn nguyên).
- **Sau R4, đợt 2 (2026-11-22, chưa commit):** dòng kẻ nhạt xét theo độ đậm (`ruling.LIGHT_LINE`), S3 lọc mực in khác màu bút (`_off_colour`), lỗ bấm (`_blobs`), gạch dưới bằng bút không phải nếp gấp (`folds.PEN_SHARE`), một hai đoạn thẳng lẻ không phải dòng kẻ (`MIN_LINES`), tờ giấy tràn mép ảnh không nắn 4 góc (`paper.CUT_OFF_SHARE`). Benchmark F1 93,11 %, rác 3,4 %. `noise_removed` thêm lý do `BLOB`, `COLOUR`. Chi tiết: báo cáo R4 mục 6.
- **Sau R4, đợt 3 (2026-11-22, chưa commit):** S8b, nét mảnh được dò trên bản phóng to của tờ giấy (`_fine_ink`), khử nhiễu vẫn ở cỡ gốc. Benchmark F1 93,60 %, độ phủ 91,0 %, 1 ảnh kém hơn R3 > 2 điểm; 1,74 giây / ảnh. Báo cáo R4 mục 7.
