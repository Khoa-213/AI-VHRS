# Nguồn của từng thông số mô phỏng (kiểm tra 17/11/2026)

Mục đích: thay các giá trị do Claude tự chọn trong `configs/default.json` bằng giá trị có nguồn. Kết luận ngắn: **không có nguồn
công khai nào cho biết sai số thật của con FR3 này** (sai lệch hình học, độ cứng, sai số truyền động). Các nguồn chỉ cho
(a) thông số hãng công bố, (b) số đo trên robot khác, (c) số đo thật trong repo AI-VHRS.

Ký hiệu: **ĐO** = số đo thật trên robot của nhóm · **HÃNG** = hãng/nhà phân phối công bố · **TL** = tài liệu khoa học (robot khác)
· **KHÔNG CÓ** = không tìm được nguồn, bắt buộc phải đo.

## 1. Số đo thật đã có trong repo

| Đại lượng | Giá trị | Nguồn | Ý nghĩa và giới hạn |
|---|---|---|---|
| Sai lệch giữa vị trí ra lệnh và vị trí controller báo về ở cuối mỗi đoạn MoveL (REAL, job 291, 31/10/2026) | 238 đoạn / 4 lần chạy: xy max trung bình 0,051 mm, trung vị 0,046, P95 0,113, lớn nhất 0,141 mm; z trung bình 0,005 mm, \|z\| max P95 0,095 mm | `robot_agent/runs/job291/run-20261031-*.jsonl`, trường `motion_stats.end_error_*` (tính trong `vhrs_agent/linear_motion.py`) | **ĐO**. Đây là sai số bám/dừng theo **encoder của chính robot**, không phải độ chính xác tuyệt đối. Robot "tin" nó đã tới đúng chỗ trong khoảng ~0,05 mm. |
| Offset flange so với URDF | 99,9997 và 100,0019 mm, dư 0,011 / 0,009 mm | `robot_agent/runs/robot_inspection*.json` | **ĐO**. Xác nhận mô hình danh định khớp với controller, không nói gì về độ chính xác thật. |
| Khung giấy dò bằng bút (calibration.json, 31/10) | P0–P1 = 209,06 mm (A4: 210); P0–P2 = 298,69 mm (A4: 297); góc 89,97° | `robot_agent/calibration.json` → `probe_points` | **ĐO** nhưng trộn nhiều nguồn: dung sai cắt giấy, độ chính xác khi người vận hành jog tới góc, độ lệch bút, sai số robot. **Không tách được sai số robot** từ số này. |
| Độ cứng lò xo giữ bút | 0,2576 N/mm (ước lượng hình học, không đo) | `calibration.json` → `_spring_geometry_estimate` | Không phải số đo. Cho thấy bút gắn trên lò xo, nên "độ ấn" trong mô phỏng (bút cứng) không phản ánh thật. |

## 2. Thông số hãng công bố (FAIRINO FR3)

| Thông số | Giá trị | Nguồn |
|---|---|---|
| Tải định mức | 3 kg | [RoboDK](https://robodk.com/robot/ko/FAIR-Innovation/INO-FR3), [Qviro](https://qviro.com/product/fairino/fr3/specifications) |
| Tầm với | 622 mm | như trên |
| Độ lặp lại | ±0,02 mm (bản FR3 cơ bản); ±0,05 mm cho một số biến thể WML/WMS | như trên; [Encycam](https://encycam.com/?p=51801) |
| Cấu tạo khớp | hộp số harmonic, động cơ frameless, encoder kép, cảm biến mô-men | [DirectIndustry](https://www.directindustry.com/prod/fairino/product-4612966-2802403.html) (tóm tắt từ hồ sơ công ty FAIRINO) |
| Độ chính xác tuyệt đối | **không công bố** | — |
| Cỡ/tỉ số hộp số, độ phân giải encoder, độ cứng khớp | **không công bố** (catalogue PDF của hãng tải về được nhưng không trích được chữ) | — |

Lưu ý: bảng kết quả của MUKCa có một dòng "FR3". Đó là **Franka Research 3**, không phải FAIRINO FR3.

## 3. Tài liệu khoa học và catalogue (robot/linh kiện khác)

| Thông số | Giá trị trong nguồn | Nguồn | Áp dụng cho FAIRINO FR3? |
|---|---|---|---|
| Sai số tuyệt đối trước hiệu chuẩn | Franka Panda/FR3: 3,3–10,6 mm; KUKA iiwa 14: 0,72–0,81 mm; Kinova Gen3 lite: 4,7–6,0 mm (MAE theo socket, không dùng thiết bị đo ngoài) | MUKCa, arXiv:2503.12584 Bảng I | Không. Cho thấy mỗi hãng khác nhau tới 10 lần. |
| Sai số sau hiệu chuẩn MUKCa | Franka: 0,24–0,35 mm (tập kiểm tra); KUKA 0,27 mm; Kinova 2,7 mm | như trên | Chỉ để đối chiếu. |
| ABB IRB 120 trước/sau hiệu chuẩn bằng laser tracker | sai số khoảng cách trung bình 1,062 → 0,400 mm | [Luận án Nubiola, ÉTS](https://espace.etsmtl.ca/id/eprint/1432/13/NUBIOLA_BATLLE_Albert.pdf) | Không (robot công nghiệp). |
| Hiệu chuẩn UR5 bằng laser tracker | 71,9 → 20,9 µm (MAE) | [Khanesar et al., Nottingham](https://nottingham-repository.worktribe.com/OutputFile/9088747) | Không. |
| Độ chính xác truyền động của harmonic drive cỡ 14–17 | 1,0–1,5 arcmin (0,017–0,025°) | [Harmonic Drive CSF-14-80-GH](https://www.harmonicdrive.net/products/servo-mount-gearheads/harmonic-drive/csf-gh/14/csf-14-80-gh), [CSF-ULW brochure](https://www.harmonicdrive.net/_hd/content/documents1/CSF-ULW%20Brochure%20HR.pdf) | Chỉ khi FR3 dùng đúng loại này và controller đo góc ở phía động cơ. Chưa xác nhận. |
| Độ cứng xoắn harmonic drive cỡ 14 / 17 (tỉ số ≥ 80) | K1/K2 ≈ 0,47/0,61 ·10⁴ và 1,0/1,4 ·10⁴ N·m/rad | như trên | Chưa biết FR3 dùng cỡ nào. |
| Độ chính xác máy in 3D (dụng cụ socket) | "cỡ 0,1 mm" (BambuLab A1); khoảng cách socket đo bằng thước cặp sau khi in | MUKCa Sec. III-C, IV | Áp dụng nếu nhóm in bằng máy tương tự. |
| Số mẫu tối thiểu | ≥ 30 mẫu/socket | MUKCa Sec. IV-A | Áp dụng (nên dùng 30/socket thay vì 60 tổng). |
| λ | 1·10⁻⁴ | MUKCa Sec. IV-A | Áp dụng (đang dùng). |
| Độ lặp lại khi đặt bi vào socket | **không có số** trong MUKCa | — | **KHÔNG CÓ** |
| Góc nghiêng đạt được quanh socket | **không có số** trong MUKCa | — | **KHÔNG CÓ** |

## 4. Đối chiếu với giá trị đang dùng trong mô phỏng

| Thông số trong `default.json` | Đang dùng (Claude chọn) | Có nguồn? | Đánh giá |
|---|---|---|---|
| sigma_p_mm 0,5 / sigma_r_deg 0,1 (sai lệch hình học) → sai số danh định ≈ 0,75 mm | tự chọn | **KHÔNG CÓ** cho FAIRINO FR3 | Tài liệu về các cobot khác cho 0,07–10 mm. Giá trị 0,75 mm nằm trong khoảng đó nhưng **không có cơ sở để chọn**. |
| harmonic_amp_deg 0,003° | tự chọn | catalogue cho 0,017–0,025° | **Có thể nhỏ hơn thực tế 6–8 lần** nếu controller đo góc phía động cơ. Nếu dùng encoder phía đầu ra thì sai số này phần lớn bị loại bỏ. Chưa biết FR3 dùng loại nào. |
| stiffness (3, 3, 2, 1, 1, 1)·10⁴ N·m/rad | tự chọn | cùng bậc với catalogue cỡ 14–17 (0,5–1,4·10⁴) | Bậc độ lớn hợp lý, nhưng giá trị cụ thể **không có nguồn**. |
| payload_kg 0,6 | tự chọn | **KHÔNG CÓ** (chưa cân cụm kẹp bút) | Phải cân. |
| sigma_tool_mm 0,3 | tự chọn | **KHÔNG CÓ** | Phải đo. |
| sigma_seat_mm 0,02 | tự chọn | **KHÔNG CÓ** | Phải đo (mục 8 trong REAL_WORLD_VALIDATION_REQUIRED). |
| sigma_q_deg 0,001 | tự chọn | **KHÔNG CÓ** (độ phân giải encoder không công bố) | Đo bằng 100 lần đọc khi robot đứng yên. |
| sigma_d_mm 0,02 (khoảng cách socket) | tự chọn | phụ thuộc thước cặp sẽ dùng | Lấy từ datasheet của thước cặp thật. |
| probe: sigma_inplane 0,1 / normal 0,02 mm | tự chọn | **KHÔNG CÓ** | Đo bằng 10 lần dò lặp. |
| cone_deg 30 / spin 60 | tự chọn | **KHÔNG CÓ** | Phải thử thực tế. |
| n_total 60 | tự chọn | MUKCa: ≥ 30/socket | Nên sửa: S2 = 60, S3 = 90 (hoặc so sánh cùng tổng như hiện tại và nói rõ). |

## 5. Kết luận

1. **Không thể đưa ra "con số chính xác" cho sai số của robot FR3 của nhóm từ tài liệu**: hãng không công bố độ chính xác
   tuyệt đối, cỡ hộp số hay độ cứng khớp. Tài liệu chỉ có số của robot khác, chênh nhau tới 100 lần
   (0,07 mm ở UR5 → 10 mm ở Franka).
2. Có hai thông số tìm được nguồn trực tiếp: **độ lặp lại ±0,02 mm** (hãng) và **λ = 1e-4, ≥ 30 mẫu/socket** (MUKCa).
3. Có một thông số mà giá trị đang dùng **có thể quá nhỏ**: sai số truyền động 0,003° so với 0,017–0,025° trong catalogue
   harmonic drive.
4. Cách trung thực duy nhất là: (a) chạy lại mô phỏng **quét theo khoảng có nguồn** thay cho một giá trị tự chọn, và báo
   cáo kết quả theo từng mức; (b) đo trên robot thật các thông số đánh dấu KHÔNG CÓ.
