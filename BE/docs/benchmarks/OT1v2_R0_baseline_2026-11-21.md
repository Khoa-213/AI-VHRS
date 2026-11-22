# OT-1 phục dựng v2, R0: benchmark nhiễu và mốc v1 (2026-11-21)

Kế hoạch: `docs/OT1_RECOVERY_V2_PLAN.md` (chủ dự án duyệt Q1–Q5 ngày 2026-11-21). Script: `scripts/benchmark_ot1v2.py`.
Chạy ở máy dev, không ghi DB, không gửi ảnh ra ngoài. Ảnh và kết quả chi tiết ở `benchmarks/data/ot1v2/` (không commit).

## 1. Bộ benchmark

- **Nguồn chữ:** 22 ảnh chữ viết tay tiếng Việt thật, lấy đều từ mẫu công khai 50 ảnh của U3 (`benchmarks/data/viet_hw/`,
  dùng nội bộ để đo, không tải thêm). Ảnh quét sạch, nên làm phẳng sáng + Otsu cho ra **mặt nạ mực đúng**.
- **Ghép nhiễu** (sinh bằng code, hạt giống 2026, không tải ảnh nền). Mọi phép hình học áp cho cả ảnh lẫn mặt nạ.
- **220 ảnh tổng hợp** = 22 nguồn × 10 nhóm:

| Nhóm | Nội dung |
|---|---|
| clean | giấy trắng ngà, không nhiễu (đối chứng) |
| ruled | dòng kẻ nhạt (xanh / tím / xám), 60 % có lề đỏ |
| ruled_same | dòng kẻ cùng màu mực |
| fold | 1–2 nếp gấp (gờ tối + dải bóng) |
| tear | giấy rách 2 mảnh, mảnh sau lệch / xoay, thấy nền ở khe |
| background | tờ giấy nằm trên nền vân gỗ, nghiêng 3–15° + phối cảnh |
| stain | giấy ố vàng + vết bẩn |
| lowres | cạnh ngắn 700–900 px |
| mixed | dòng kẻ + nếp gấp + rách + nền gỗ |
| ruled_hard | dòng kẻ xám đậm gần độ đậm mực, mực nhạt, nếp gấp, ảnh nhỏ (giống ảnh thư thật của chủ dự án) |

`ruled_hard` được thêm **trong R0, trước khi làm gì cho v2**: nhóm `ruled` cho v1 tới 87 % trong khi ảnh thư thật hỏng rõ,
nên `ruled` dễ hơn thực tế. Nhóm mới thêm vào cuối, 9 nhóm cũ giữ nguyên từng ảnh (số đo 9 nhóm không đổi giữa hai lượt).

**Giới hạn:** đây là ảnh tổng hợp. Nền gỗ, nếp gấp, vết rách là mô phỏng; con số trên ảnh thật có thể khác. Ảnh thật
(2 ảnh của chủ dự án) chưa có mặt nạ đúng: theo Q2, mặt nạ nháp sẽ sinh từ v2 rồi chủ dự án sửa / duyệt.

## 2. Thước đo (cố định trước khi đo)

- Nét của bộ phục dựng được quy ngược về pixel của ảnh đầu vào (bỏ phép co vào khổ giấy, xoay nghiêng, thu nhỏ) và vẽ
  rộng 1 px (đường tâm).
- Khung xương mặt nạ đúng (Zhang-Suen). `w` = bề rộng nét trung vị của mặt nạ đúng, `τ = max(1, w / 2)` px.
- **P** = phần đường tâm dự đoán nằm trong `τ` quanh khung xương đúng (1 − P = tỷ lệ nét rác).
- **R** = phần khung xương đúng có đường tâm dự đoán trong `τ` (độ phủ).
- **Độ giống v2 = F1(P, R).** Cột "IoU cũ" là con số sản phẩm đang hiển thị.

## 3. Mốc v1 (bộ phục dựng hiện tại, `ENGINE_VERSION` 1)

| Nhóm | n | **F1 v2** | P (1 − rác) | R (phủ) | IoU cũ | Số nét | Giây / ảnh |
|---|---|---|---|---|---|---|---|
| clean | 22 | 89,28 | 94,95 | 84,27 | 66,10 | 472 | 2,5 |
| ruled | 22 | 87,21 | 90,91 | 84,40 | 65,40 | 480 | 2,5 |
| ruled_same | 22 | 75,03 | 68,95 | 85,08 | 62,05 | 501 | 2,6 |
| fold | 22 | 86,76 | 89,18 | 84,56 | 63,99 | 486 | 2,5 |
| tear | 22 | 83,63 | 85,23 | 82,12 | 64,76 | 480 | 2,5 |
| **background** | 22 | **24,64** | 16,15 | 54,79 | 66,14 | 451 | 5,8 |
| stain | 22 | 89,30 | 94,98 | 84,29 | 66,13 | 471 | 2,5 |
| lowres | 22 | 88,69 | 94,66 | 83,46 | 65,88 | 465 | 2,1 |
| **mixed** | 22 | **23,23** | 14,83 | 55,35 | 61,19 | 521 | 6,1 |
| **ruled_hard** | 22 | **67,46** | 56,26 | 84,78 | 57,94 | 545 | 2,4 |
| **Tất cả** | 220 | **71,52** | 70,61 | 78,31 | 63,96 | 487 | 3,2 |

Ảnh thật (không có mặt nạ đúng, chỉ IoU cũ): thư dòng kẻ rách 50,16 % (1.198 nét, 100 / 387 vùng RESTORED); phong bì trên
nền gỗ không cắt 54,08 % (286 nét). Ảnh nét v1 vẽ đè lên ảnh gốc: `benchmarks/data/ot1v2/real_v1_R0/`.

## 4. Nhận xét

1. **IoU cũ không phản ánh chất lượng.** Nhóm background có IoU cũ 66,1 %, bằng nhóm clean, dù 84 % nét sinh ra là rác (P 16 %).
   Q1 (đổi thước đo) là cần thiết.
2. **Chỗ hỏng lớn nhất là nền ngoài tờ giấy** (background, mixed: F1 23–25 %): vân gỗ, khe sàn thành nét. Đây là việc của
   R1 (tìm tờ giấy, nắn phối cảnh, mặt nạ giấy).
3. **Dòng kẻ đậm / cùng màu** (ruled_hard 67 %, ruled_same 75 %): P chỉ 56–69 %, tức 31–44 % nét là dòng kẻ. Việc của R2.
4. **Độ phủ của v1 dừng ở ~84 % ngay cả trên ảnh sạch.** Phân tích 8 ảnh clean: 76 % chỗ thiếu chỉ lệch trong khoảng `τ`–`2τ`
   (đường tâm bị làm mượt / đơn giản hoá lệch khỏi tâm nét), 70 % nằm gần đầu mút nét (đầu nét bị cắt ngắn khi tỉa gai),
   chỉ 6 % là mảnh nhỏ (dấu, chấm) bị bỏ. Muốn đạt 80 % chung thì R3 (S8) phải sửa cả phần này, không chỉ loại nhiễu.
5. Nếp gấp, rách, ố, ảnh nhỏ: v1 đã 84–89 % trên ảnh tổng hợp; nếp gấp / rách tổng hợp có thể dễ hơn thật.

## 5. Mục tiêu cho các phase sau (không đổi so với kế hoạch)

F1 v2 ≥ 80 % trên toàn bộ 220 ảnh, từng nhóm ≥ 75 %, tỷ lệ rác (1 − P) ≤ 5 %. Mốc v1: 71,5 % chung, 3 nhóm dưới 75 %,
tỷ lệ rác 29,4 %.
