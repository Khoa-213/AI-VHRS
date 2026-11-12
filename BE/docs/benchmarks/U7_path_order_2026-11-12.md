# U7: thứ tự nét và quãng nhấc bút (2026-11-12)

Lệnh: `.venv/Scripts/python scripts/benchmark_path_order.py` (50 ảnh OT-1 trong `benchmarks/data/viet_hw`, 6 trang OT-3). Quãng nhấc bút = tổng khoảng cách thẳng trên giấy từ cuối nét này tới đầu nét kế (cùng số với `trajectory.compute_metrics`), **không** phải mô phỏng robot. Thời gian tiết kiệm tính theo tốc độ nhấc bút giả định 100 mm/s (`TRAVEL_SPEED_MM_S`, chưa đo trên robot).

Kiểm tra toàn vẹn (đủ nét, mỗi từ liền và giữ thứ tự, nét không đảo thì không đổi điểm): **56/56 trang đạt**.

## OT-1 (50 trang)

| Chỉ số | Trung vị | Nhỏ nhất | Lớn nhất |
|---|---|---|---|
| Quãng nhấc bút giảm (%), NN + 2-opt | 37.8 | 6.0 | 52.7 |
| Quãng nhấc bút giảm (%), chỉ NN | 36.4 | 1.8 | 52.0 |
| Thời gian nhấc bút bớt được (s, giả định) | 14.3 | 0.7 | 26.0 |
| Số cụm (từ) | 126 | 35 | 293 |
| Thời gian chạy bộ tối ưu (ms) | 29 | 7 | 82 |

Tổng: 201,810 mm → 129,350 mm.

## OT-3 (6 trang)

| Chỉ số | Trung vị | Nhỏ nhất | Lớn nhất |
|---|---|---|---|
| Quãng nhấc bút giảm (%), NN + 2-opt | 19.0 | 6.0 | 28.4 |
| Quãng nhấc bút giảm (%), chỉ NN | 15.4 | 0.0 | 28.4 |
| Thời gian nhấc bút bớt được (s, giả định) | 1.6 | 0.1 | 8.0 |
| Số cụm (từ) | 15 | 4 | 55 |
| Thời gian chạy bộ tối ưu (ms) | 3 | 1 | 10 |

Tổng: 7,149 mm → 5,678 mm.

## Giới hạn jerk (tuỳ chọn, mô phỏng)

889 nét viết của 5 trang, thông số mẫu v_max 40 mm/s, a_lat 2000, a_tan 1000 mm/s² (giá trị demo của `robot_agent`, **chưa đo trên FR3**). Thời gian = chỉ phần bút chạm giấy; jerk tính rời rạc giữa các điểm cách 0,2 mm.

| j_max (mm/s³) | Jerk lớn nhất | Thời gian viết (s) | Tăng | Tính (s) |
|---|---|---|---|---|
| tắt | 396,509 | 202.1 | – | – |
| 100,000 | 99,999 | 244.0 | +20.7% | 3.4 |
| 50,000 | 49,997 | 285.1 | +41.0% | 4.0 |
| 20,000 | 19,984 | 390.0 | +92.9% | 4.2 |

## Từng trang OT-3

| Trang | Nét | Cụm | Trước (mm) | Sau (mm) | Giảm | Nét đảo chiều |
|---|---|---|---|---|---|---|
| thiep-ngan p1 | 33 | 4 | 186 | 175 | 6.0% | 0 |
| loi-chuc p1 | 153 | 19 | 913 | 759 | 16.8% | 0 |
| thu-a5 p1 | 243 | 33 | 1442 | 1136 | 21.2% | 0 |
| thu-a4-deu p1 | 427 | 55 | 3437 | 2641 | 23.1% | 0 |
| chu-lon p1 | 33 | 4 | 581 | 543 | 6.5% | 0 |
| loi-tang + hinh ve | 36 | 11 | 590 | 423 | 28.4% | 3 |

## Giới hạn

- Chỉ đổi thứ tự **giữa các từ**; quãng nhấc bút **trong một từ** (giữa các nét của chữ, tới dấu thanh) giữ nguyên vì đó là thứ tự viết, và chiếm phần lớn quãng còn lại.
- Với OT-3 robot có thể viết các từ không theo thứ tự đọc (kết quả trên giấy giống hệt).
- Thời gian thật phụ thuộc tốc độ nhấc bút, thời gian hạ / nhấc bút và gia tốc của robot: phải đo trên FR3 (HW).
- Giới hạn jerk chỉ đo được trên mô phỏng: có giảm rung, có làm nét đẹp hơn hay không phải thử trên robot thật.
