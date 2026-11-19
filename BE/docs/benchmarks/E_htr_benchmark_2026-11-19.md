# V2 Phase E phần 1: đo nhận dạng chữ viết tay tiếng Việt (HTR) (2026-11-19)

- Dữ liệu: 50 trang viết tay công khai của U3 (`5CD-AI/Viet-Handwriting-gemini-VQA`, gốc UIT-HWDB), đáp án = `label` do người gõ. Ảnh và kết quả từng trang ở `benchmarks/data/` (không commit, giấy phép chưa rõ).
- Đo lại: `scripts/benchmark_htr.py` (xem docstring). Máy: máy phát triển Windows, CPU 16 luồng, không GPU.
- CER / WER `exact`: chuẩn NFC, gộp khoảng trắng. `loose`: thêm chữ thường, bỏ dấu câu (dấu thanh giữ nguyên). `[?]` (chỗ mô hình báo không đọc được) được bỏ trước khi so, nên vẫn tính là thiếu chữ.

## Tổng hợp (50 trang)

| Engine | CER exact (trung vị) | CER exact P90 | WER exact (trung vị) | CER loose (trung vị) | WER loose (trung vị) | chèn thừa / ký tự (trung vị) | giây / trang (trung vị) | ghi chú |
|---|---|---|---|---|---|---|---|---|
| vietocr | 0.245 | 0.553 | 0.635 | 0.221 | 0.585 | 0.023 | 7.0 | nạp mô hình 2.6 s, RAM tối đa 699 MB, dòng tách trung vị 7 (50/50 trang) |
| gemini | 0.024 | 0.077 | 0.097 | 0.015 | 0.035 | 0.000 | 2.7 | mô hình `gemini-3.5-flash-lite`, 59 lượt gọi, 66887 token vào, 8387 token ra, lỗi 0, bị chặn RECITATION (trả rỗng, tính CER 1): 400, 1186 (50/50 trang) |

## Đọc kết quả

- **Gemini đọc tốt hơn hẳn:** CER trung vị 0,024 (khoảng 2 ký tự sai trên 100), WER 0,097; VietOCR CER 0,245, WER 0,635. Bỏ hoa thường và dấu câu, Gemini còn CER 0,015.
- **Nhưng số của Gemini có thể đẹp hơn thực tế:** bộ dữ liệu là bài viết công khai (UIT-HWDB), và **2/50 trang (400, 1186) bị Google chặn với lý do `RECITATION`** (câu trả lời trùng văn bản có sẵn), trả về rỗng. Điều này cho thấy một phần nội dung đã có trong dữ liệu huấn luyện. Thư tay của khách thật sẽ không có lợi thế đó. Trong sản phẩm, trả rỗng phải được coi là "không đọc được" (hỏi khách / chuyển Staff), không phải lỗi hệ thống.
- **Không thấy Gemini tự điền chữ:** trang trắng và trang nhiễu đều trả `[?]`; trang bị che 1/3 giữa trả 0,62–0,69 lượng chữ của bản không che (đúng tỉ lệ phần còn nhìn thấy), một trang ghi 15 chỗ `[?]`. Chưa đủ để kết luận tuyệt đối (5 trang), nhưng không có dấu hiệu "nhớ lại" phần bị che.
- **VietOCR luôn trả ra chữ:** trang nhiễu cho 370 ký tự vô nghĩa (dãy số), không có `[?]`. Muốn dùng phải có ngưỡng tin cậy theo dòng (VietOCR có trả xác suất) để chặn bịa chữ; bài đo này chưa dùng ngưỡng đó.
- **Phần lớn lỗi VietOCR là của chính mô hình, không chỉ do tách dòng:** trên 46 trang tách dòng hợp lý, CER trung vị vẫn 0,243. 4 trang tách sai (644, 645, 917, 218, dòng bị cắt đôi) cho CER 1,3–1,6. Cải thiện cần bộ dò dòng tốt hơn **và** huấn luyện thêm trên chữ viết tay; cả hai là việc lớn.
- **Tài nguyên:** VietOCR trên CPU 7,0 s / trang (trung vị), RAM tối đa 699 MB chỉ riêng tiến trình đo, cộng PyTorch khoảng 1 GB cài đặt: khó chạy trên gói máy chủ hiện tại cùng BE. Gemini 2,7 s / trang, không tốn RAM máy chủ.
- **Chi phí Gemini:** 59 lượt gọi, 66.887 token vào, 8.387 token ra (số thật từ API). Hệ thống chưa cấu hình giá (`LLM_PRICES` trống); **nếu** giá cỡ 0,1 USD / 1 triệu token vào và 0,4 USD / 1 triệu token ra thì cả đợt khoảng 0,01 USD (giả định, chưa kiểm hoá đơn).
- **Quyền riêng tư:** dùng Gemini nghĩa là gửi ảnh chữ viết của khách ra ngoài. Hiện chính sách là không gửi ảnh. Đây là quyết định của chủ dự án ở phần 2 (tích hợp), không quyết trong bài đo.
- **Chưa đo:** chữ viết tay của khách thật, ảnh chụp điện thoại (nghiêng, bóng), thư cũ phai mực, nhận dạng theo vùng U4 (ở đây đọc cả trang), mô hình khác (Claude, GPT đọc ảnh) và PaddleOCR.

## Kiểm tra bịa chữ (Test 5)

| Engine | Trang | Kết quả | Ghi chú |
|---|---|---|---|
| vietocr | blank | 0 ký tự | `` |
| vietocr | noise | 370 ký tự | `0360001001990 0360000000990 036000000099 03100100199000199 03600100199000199 030` |
| vietocr | masked_884 (che 1/3 giữa trang) | 347 ký tự = 0.79 × bản không che | CER so với cả đáp án 0.674, `[?]` 0 |
| vietocr | masked_42 (che 1/3 giữa trang) | 802 ký tự = 0.68 × bản không che | CER so với cả đáp án 0.453, `[?]` 0 |
| vietocr | masked_119 (che 1/3 giữa trang) | 677 ký tự = 0.61 × bản không che | CER so với cả đáp án 0.486, `[?]` 0 |
| vietocr | masked_433 (che 1/3 giữa trang) | 347 ký tự = 0.60 × bản không che | CER so với cả đáp án 0.536, `[?]` 0 |
| vietocr | masked_400 (che 1/3 giữa trang) | 466 ký tự = 0.78 × bản không che | CER so với cả đáp án 0.521, `[?]` 0 |
| gemini | blank | 3 ký tự | `[?]` |
| gemini | noise | 3 ký tự | `[?]` |
| gemini | masked_884 (che 1/3 giữa trang) | 284 ký tự = 0.63 × bản không che | CER so với cả đáp án 0.522, `[?]` 15 |
| gemini | masked_42 (che 1/3 giữa trang) | 812 ký tự = 0.69 × bản không che | CER so với cả đáp án 0.351, `[?]` 0 |
| gemini | masked_119 (che 1/3 giữa trang) | 686 ký tự = 0.62 × bản không che | CER so với cả đáp án 0.408, `[?]` 1 |
| gemini | masked_433 (che 1/3 giữa trang) | 362 ký tự = 0.62 × bản không che | CER so với cả đáp án 0.441, `[?]` 2 |
| gemini | masked_400 (che 1/3 giữa trang) | 353 ký tự = – (bản không che rỗng) × bản không che | CER so với cả đáp án 0.399, `[?]` 3 |

## Từng trang

| id | vietocr CER | vietocr WER | gemini CER | gemini WER |
|---|---|---|---|---|
| 884 | 0.217 | 0.564 | 0.022 | 0.020 |
| 42 | 0.191 | 0.577 | 0.042 | 0.163 |
| 119 | 0.190 | 0.554 | 0.037 | 0.153 |
| 433 | 0.242 | 0.571 | 0.052 | 0.079 |
| 400 | 0.305 | 0.632 | 1.000 | 1.000 |
| 1096 | 0.209 | 0.574 | 0.011 | 0.056 |
| 187 | 0.157 | 0.509 | 0.024 | 0.140 |
| 644 | 1.578 | 1.557 | 0.012 | 0.072 |
| 645 | 1.316 | 1.593 | 0.042 | 0.086 |
| 999 | 0.330 | 0.709 | 0.021 | 0.043 |
| 616 | 0.205 | 0.629 | 0.037 | 0.190 |
| 274 | 0.464 | 0.854 | 0.053 | 0.208 |
| 511 | 0.422 | 0.797 | 0.014 | 0.098 |
| 750 | 0.400 | 0.845 | 0.020 | 0.029 |
| 588 | 0.339 | 0.714 | 0.024 | 0.080 |
| 866 | 0.157 | 0.473 | 0.024 | 0.098 |
| 199 | 0.232 | 0.580 | 0.037 | 0.071 |
| 1142 | 0.234 | 0.644 | 0.015 | 0.087 |
| 1009 | 0.274 | 0.659 | 0.005 | 0.031 |
| 1177 | 0.513 | 0.907 | 0.147 | 0.161 |
| 1103 | 0.471 | 0.859 | 0.073 | 0.207 |
| 932 | 0.181 | 0.430 | 0.045 | 0.070 |
| 421 | 0.556 | 0.800 | 0.014 | 0.063 |
| 631 | 0.374 | 0.768 | 0.016 | 0.134 |
| 692 | 0.478 | 0.785 | 0.298 | 0.392 |
| 878 | 0.553 | 0.864 | 0.327 | 0.476 |
| 1186 | 0.338 | 0.649 | 1.000 | 1.000 |
| 213 | 0.202 | 0.477 | 0.053 | 0.056 |
| 71 | 0.168 | 0.525 | 0.029 | 0.132 |
| 447 | 0.132 | 0.446 | 0.002 | 0.010 |
| 831 | 0.247 | 0.644 | 0.040 | 0.186 |
| 347 | 0.237 | 0.625 | 0.025 | 0.080 |
| 940 | 0.387 | 0.694 | 0.015 | 0.071 |
| 941 | 0.221 | 0.515 | 0.000 | 0.000 |
| 701 | 0.448 | 0.872 | 0.072 | 0.136 |
| 455 | 0.271 | 0.678 | 0.037 | 0.133 |
| 705 | 0.285 | 0.634 | 0.022 | 0.081 |
| 1120 | 0.213 | 0.584 | 0.024 | 0.097 |
| 1223 | 0.329 | 0.728 | 0.017 | 0.097 |
| 78 | 0.244 | 0.651 | 0.065 | 0.294 |
| 254 | 0.294 | 0.700 | 0.043 | 0.217 |
| 466 | 0.237 | 0.465 | 0.016 | 0.069 |
| 111 | 0.184 | 0.578 | 0.039 | 0.176 |
| 360 | 0.210 | 0.588 | 0.002 | 0.010 |
| 499 | 0.223 | 0.549 | 0.020 | 0.106 |
| 917 | 1.333 | 1.802 | 0.013 | 0.070 |
| 778 | 0.245 | 0.635 | 0.011 | 0.073 |
| 814 | 0.232 | 0.580 | 0.022 | 0.107 |
| 503 | 0.215 | 0.500 | 0.000 | 0.000 |
| 218 | 1.575 | 1.679 | 0.077 | 0.161 |
