# U3: đo phục dựng OT-1 trên ảnh chữ viết tay tiếng Việt thật (2026-11-12)

- Dữ liệu: 50 ảnh lấy đều từ `5CD-AI/Viet-Handwriting-gemini-VQA` (gốc UIT-HWDB + Cinnamon AI Challenge), danh sách mã ảnh ở bảng cuối; ảnh **không** nằm trong repo (giấy phép chưa rõ, chỉ dùng đo nội bộ). Tải lại bằng `scripts/fetch_hf_handwriting.py`, đo lại bằng `scripts/benchmark_recovery.py`.
- Cấu hình: khổ A4, lề 10 mm, engine `zhang-suen-skeleton` + vùng U4 (ngưỡng 0.6). Máy đo: máy phát triển Windows của dự án (CPU, không GPU).
- **Không đo được ở đây:** độ đúng thứ tự / chiều nét (ảnh không có quỹ đạo bút gốc), CER / WER (hệ thống chưa có nhận dạng chữ), chất lượng nét trên giấy thật (cần robot).

## Kết quả

- Chạy được: **50/50** ảnh. Lỗi: không có.
- Thời gian mỗi ảnh: trung vị 1.03 s, lớn nhất 3.90 s (NFR-01: ≤ 15 s mỗi trang OT-1).
- `similarity` ≥ 80 (mục tiêu NFR-02): **0/50** ảnh.
- Vùng U4: 6760 vùng, RESTORED 6 (0.1%).
- Thử độ nhạy (mực mờ nhân tạo trên ảnh thật, 50 ảnh: hộp giữa ảnh 30% × 40%, mực bị kéo 60% về màu giấy): vùng trong hộp bị gắn RESTORED **878/906 (96.9%)**; vùng ngoài hộp bị gắn nhầm 5/5423 (0.1%). Cùng hộp đó trên ảnh gốc có 871 vùng: **0 vùng (0%) biến mất hẳn** khi mực mờ (bị coi là nền, không có nét nên không có vùng để gắn nhãn). Đây là hư hại giả lập, không thay được ảnh hư hại thật.

| Chỉ số | Trung vị | P10 | P90 | Nhỏ nhất | Lớn nhất | Ý nghĩa / mục tiêu |
|---|---|---|---|---|---|---|
| similarity (IoU mực / nét, %) | 65.280 | 63.740 | 66.870 | 62.160 | 68.690 | NFR-02 ≥ 80 |
| topology_ratio (mảnh nét / mảnh mực) | 0.899 | 0.854 | 0.951 | 0.767 | 0.963 | gần 1 |
| endpoint_ratio (đầu nét / đầu khung xương) | 1.315 | 1.162 | 1.465 | 0.988 | 1.677 | gần 1; > 1 = nhấc bút thừa |
| strokes_per_char | 1.457 | 1.269 | 1.646 | 1.149 | 1.703 | tham khảo |
| region_word_ratio (vùng / từ) | 1.188 | 0.940 | 1.457 | 0.720 | 1.733 | gần 1 |
| mark_ratio (nét dấu / dấu trong văn bản) | 0.901 | 0.710 | 1.114 | 0.529 | 1.243 | gần 1 (thô) |
| confidence vùng | 0.986 | 0.899 | 1.000 | 0.498 | 1.000 | < 0.6 → RESTORED |
| fit vùng | 0.653 | 0.588 | 0.703 | 0.329 | 0.839 | IoU cục bộ |
| contrast vùng | 1.000 | 0.947 | 1.000 | 0.662 | 1.000 | độ đậm so với trang |
| giây / ảnh | 1.031 | 0.736 | 1.554 | 0.298 | 3.895 | NFR-01 ≤ 15 |

## Đọc kết quả và các thay đổi đã làm theo số đo

- **`similarity` không đạt 80 trên ảnh thật nào, nhưng không vì nét sai:** mọi ảnh nằm trong khoảng hẹp 62–69 kể cả ảnh rất sạch, trong khi `topology_ratio` ~0,9 và `endpoint_ratio` ~1,3 cho thấy nét bám đúng mực. Cách đo vẽ lại nét với **một độ dày đều** rồi so điểm ảnh với mực thật (dày mỏng, nhoè mép), nên có trần thấp. Kết luận: chỉ số này không dùng được làm ngưỡng NFR-02 cho ảnh thật; cần chỉ số khác (ví dụ so khung xương với khung xương, hoặc đo trên quỹ đạo bút thật). Cảnh báo `SIMILARITY_BELOW_80` vì vậy bật cho **mọi** ảnh thật; chủ dự án quyết **tạm tắt** (2026-11-12) đến khi có cách đo tốt hơn.
- **Đã đổi (U4):** lần đo đầu, ngưỡng tuyệt đối 0,6 trên `fit` gắn RESTORED cho **13,4%** vùng của ảnh sạch (báo động giả). Nay `fit` được so với trung vị của chính trang (`fit_rel`), giống cách `contrast` đã làm: còn 0,1%.
- **Đã đổi (phục dựng):** lần đo đầu, hộp mực mờ nhân tạo làm **91% vùng biến mất hẳn**, không cảnh báo (Otsu coi mực nhạt là nền). Đây là lỗi im lặng, trái chế độ FAITHFUL. Nay `_binarise` thêm ngưỡng thứ hai (nửa đường giữa Otsu và màu giấy) cho các mảnh mực nhạt không chạm mực đậm, đủ lớn và mảnh như nét bút: không vùng nào biến mất, 96,9% được gắn RESTORED, ảnh sạch không đổi.
- `region_word_ratio` ~1,19: vùng U4 hay tách một từ viết tay thành 2 (khoảng hở trong từ), đôi khi gộp. Chấp nhận được cho việc sửa theo vùng; chưa sửa.
- `endpoint_ratio` ~1,3: robot nhấc bút nhiều hơn mức mực gợi ý khoảng 30% (nét bị cắt ở chỗ giao nhau). Ảnh hưởng thời gian viết, chưa ảnh hưởng hình chữ; cần đo trên robot thật.

## Từng ảnh

| id | ok | similarity | strokes | topology | endpoint | vùng / từ | RESTORED | giây |
|---|---|---|---|---|---|---|---|---|
| 884 | có | 66.23 | 438 | 0.905 | 1.22 | 175 / 101 | 0 | 0.772 |
| 42 | có | 64.79 | 1551 | 0.946 | 1.344 | 277 / 246 | 0 | 3.35 |
| 119 | có | 66.96 | 1467 | 0.963 | 1.372 | 240 / 242 | 0 | 3.895 |
| 433 | có | 66.75 | 644 | 0.944 | 1.32 | 167 / 140 | 0 | 1.678 |
| 400 | có | 64.1 | 649 | 0.854 | 1.295 | 154 / 125 | 0 | 1.104 |
| 1096 | có | 66.9 | 456 | 0.855 | 1.263 | 126 / 108 | 0 | 1.277 |
| 187 | có | 65.82 | 277 | 0.767 | 1.368 | 58 / 57 | 0 | 0.323 |
| 644 | có | 65.72 | 454 | 0.888 | 1.182 | 136 / 97 | 0 | 1.005 |
| 645 | có | 65.24 | 390 | 0.861 | 1.161 | 118 / 81 | 1 | 0.775 |
| 999 | có | 65.34 | 637 | 0.906 | 1.539 | 110 / 117 | 0 | 1.119 |
| 616 | có | 66.65 | 460 | 0.903 | 1.173 | 135 / 105 | 0 | 0.934 |
| 274 | có | 65.43 | 501 | 0.928 | 1.575 | 73 / 96 | 0 | 0.914 |
| 511 | có | 65.25 | 705 | 0.866 | 1.38 | 162 / 133 | 0 | 1.448 |
| 750 | có | 65.85 | 560 | 0.93 | 1.677 | 96 / 103 | 0 | 0.991 |
| 588 | có | 66.87 | 623 | 0.812 | 1.531 | 116 / 112 | 0 | 1.034 |
| 866 | có | 65.21 | 481 | 0.901 | 1.376 | 117 / 112 | 0 | 1.182 |
| 199 | có | 66.28 | 497 | 0.885 | 1.432 | 100 / 112 | 0 | 1.136 |
| 1142 | có | 66.5 | 509 | 0.941 | 1.124 | 177 / 104 | 0 | 1.331 |
| 1009 | có | 65.25 | 611 | 0.938 | 1.227 | 179 / 129 | 0 | 1.252 |
| 1177 | có | 67.26 | 687 | 0.903 | 1.459 | 85 / 118 | 0 | 1.369 |
| 1103 | có | 66.07 | 428 | 0.927 | 1.223 | 131 / 92 | 0 | 0.926 |
| 932 | có | 62.16 | 409 | 0.892 | 1.15 | 139 / 86 | 0 | 0.836 |
| 421 | có | 64.72 | 455 | 0.954 | 1.465 | 101 / 95 | 0 | 0.895 |
| 631 | có | 66.03 | 348 | 0.961 | 1.162 | 97 / 82 | 0 | 1.227 |
| 692 | có | 64.55 | 653 | 0.91 | 1.302 | 167 / 130 | 0 | 1.27 |
| 878 | có | 64.04 | 468 | 0.873 | 1.253 | 158 / 103 | 0 | 0.706 |
| 1186 | có | 67.36 | 434 | 0.905 | 1.207 | 116 / 97 | 0 | 0.866 |
| 213 | có | 65.14 | 539 | 0.871 | 1.294 | 118 / 107 | 0 | 1.427 |
| 71 | có | 64.91 | 1514 | 0.953 | 1.315 | 293 / 257 | 4 | 3.578 |
| 447 | có | 65.31 | 544 | 0.876 | 1.264 | 135 / 101 | 0 | 0.96 |
| 831 | có | 63.74 | 486 | 0.907 | 1.204 | 132 / 118 | 0 | 1.019 |
| 347 | có | 65.92 | 371 | 0.873 | 1.239 | 125 / 88 | 0 | 0.547 |
| 940 | có | 65.07 | 421 | 0.942 | 1.376 | 127 / 85 | 0 | 0.99 |
| 941 | có | 64.96 | 517 | 0.854 | 1.359 | 113 / 101 | 0 | 0.96 |
| 701 | có | 64.45 | 604 | 0.827 | 1.187 | 161 / 125 | 0 | 0.873 |
| 455 | có | 62.95 | 621 | 0.88 | 1.139 | 198 / 143 | 0 | 1.114 |
| 705 | có | 64.22 | 651 | 0.87 | 1.316 | 141 / 123 | 0 | 1.255 |
| 1120 | có | 66.55 | 590 | 0.874 | 1.54 | 109 / 113 | 0 | 1.317 |
| 1223 | có | 64.71 | 429 | 0.915 | 1.345 | 111 / 103 | 0 | 0.736 |
| 78 | có | 63.49 | 683 | 0.958 | 1.302 | 136 / 109 | 0 | 1.793 |
| 254 | có | 66.27 | 512 | 0.898 | 1.395 | 110 / 120 | 0 | 1.243 |
| 466 | có | 62.78 | 494 | 0.896 | 1.238 | 126 / 101 | 0 | 1.103 |
| 111 | có | 68.69 | 607 | 0.951 | 1.333 | 125 / 102 | 1 | 1.554 |
| 360 | có | 65.03 | 519 | 0.921 | 1.462 | 108 / 102 | 0 | 1.012 |
| 499 | có | 63.61 | 576 | 0.881 | 1.381 | 115 / 113 | 0 | 1.029 |
| 917 | có | 66.48 | 487 | 0.826 | 1.378 | 108 / 86 | 0 | 0.853 |
| 778 | có | 66.27 | 434 | 0.884 | 1.315 | 108 / 96 | 0 | 1.0 |
| 814 | có | 65.52 | 632 | 0.848 | 1.22 | 158 / 112 | 0 | 1.154 |
| 503 | có | 65.06 | 154 | 0.88 | 1.381 | 35 / 30 | 0 | 0.298 |
| 218 | có | 64.37 | 408 | 0.901 | 0.988 | 158 / 112 | 0 | 0.614 |
