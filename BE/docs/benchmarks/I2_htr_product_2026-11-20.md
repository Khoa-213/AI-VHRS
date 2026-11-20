# V2 Phase I2: đọc chữ viết tay qua code sản phẩm (2026-11-20)

Câu hỏi: đường đọc chữ của sản phẩm (`app/services/ai/htr.py`: `page_jpeg` → bên đọc đã cấu hình; rồi `htr_align.match` trên vùng của bộ phục dựng thật) có chạy thật và cho kết quả như lúc đo ở E1 / E2a không. 5 trang công khai UIT-HWDB (5 trang đã chấm bằng mắt ở E2a, không dùng để chỉnh bộ gắn), không có ảnh khách.

Chỉ số: CER / WER so với nhãn người của bộ dữ liệu (chuẩn hoá như E1, `exact`), số vùng nhận gợi ý (READ) / tổng vùng, và chặn của Phase I (`TOO_MANY_WORDS`). Câu trả lời thô lưu ở `benchmarks/data/htr_product/` (không commit).

| Trang | Bên đọc | Mô hình | Kết thúc | Giây | Token vào / ra | CER | WER | CER E1 | Vùng READ / tổng | Chặn |
|---|---|---|---|---|---|---|---|---|---|---|
| 941 | gemini | gemini-3.5-flash-lite | STOP | 11.0 | 1175 / 129 | 0.000 | 0.000 | 0.000 | 107 / 113 | - |
| 503 | gemini | gemini-3.5-flash-lite | STOP | 10.6 | 1148 / 33 | 0.000 | 0.000 | 0.000 | 35 / 35 | - |
| 705 | gemini | gemini-3.5-flash-lite | STOP | 9.7 | 1184 / 155 | 0.033 | 0.138 | 0.022 | 136 / 141 | - |
| 347 | gemini | gemini-3.5-flash-lite | STOP | 9.0 | 1187 / 113 | 0.018 | 0.045 | 0.025 | 109 / 125 | - |
| 111 | gemini | gemini-3.5-flash-lite | STOP | 8.3 | 1192 / 186 | 0.041 | 0.186 | 0.038 | 118 / 125 | - |

Trung bình trên 5 lượt đọc thành công: CER 0.018, WER 0.074; vùng READ 505 / 539.

Lượt gọi thật: 5 (mỗi trang × mỗi bên đọc có khoá).

**Claude chưa đo:** máy chạy không có `ANTHROPIC_API_KEY` (không tự tạo khoá). Đường dự phòng Claude chỉ được kiểm bằng `httpx.MockTransport` trong `tests/test_v2_htr_hints.py`, chưa gọi thật.

Bộ gắn chữ là bản có chặn `TOO_MANY_WORDS` của Phase I; trên 5 trang này chặn không bật (trang thật có tối đa 1,22 chữ / vùng mực trên 48 trang của E2a, ngưỡng là 1,5).
