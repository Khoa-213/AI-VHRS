# Nghiên cứu vật tư: giấy, bút, mực cho robot viết tay (2026-11-24)

**Trạng thái: đề xuất để chủ dự án và nhóm chọn. Chưa có loại nào được thử trên robot FR3 của dự án.** Các nhận định dưới đây đến từ tài liệu nhà sản xuất, tiêu chuẩn ISO, kinh nghiệm của người dùng máy vẽ bút (pen plotter) và suy luận từ ràng buộc của hệ thống. Chỗ nào là suy luận đều ghi rõ. Loại "tốt nhất" chỉ chốt được sau bài thử ở mục 8.

Không có giá bán trong tài liệu này: giá và nguồn hàng tại Việt Nam chưa được kiểm tra.

## 1. Tóm tắt khuyến nghị

Robot hiện giữ bút **vuông góc với giấy**, ép bằng **lò xo** (0,3 đến 1,0 N) và viết **chậm** (15 đến 40 mm/s). Ba điều này quyết định gần hết việc chọn bút:

1. **Bút nên mua thử trước (hợp với cách giữ bút hiện tại):**

   | Vai trò | Loại bút | Ứng viên | Vì sao |
   |---|---|---|---|
   | Bút chính cho phục dựng (OT-1) và thư | Fineliner mực pigment 0,1 / 0,3 / 0,5 mm | Staedtler pigment liner 308; Uni Pin; Sakura Pigma Micron | Viết được khi giữ thẳng đứng, lực rất nhẹ, nét đúng cỡ ghi trên bút, mực pigment bền sáng và chống nước. Staedtler ghi mở nắp 18 giờ không khô |
   | Bút viết hằng ngày, nhiều màu (OT-3, OT-2) | Gel 0,38 / 0,5 mm | uni-ball Signo; Pilot G2; Zebra Sarasa Clip (có bộ màu Vintage) | Nhiều màu có tên chính hãng, lực nhẹ, người dùng máy vẽ xác nhận chạy ổn |
   | Chữ trên giấy tối màu (thiệp) | Gel trắng / nhũ vàng / nhũ bạc | uni-ball Signo Broad UM-153; Sakura Gelly Roll | Mực pigment đục, phủ được nền tối |
   | Thư gốc viết bằng bút bi; giấy couché | Bút bi mực loãng 0,5 / 0,7 mm | Uni Jetstream; một loại bút bi Thiên Long để so | Mực gốc dầu bám được giấy tráng phủ, viết được xa nhất. Cần lực lớn nhất trong các loại |
   | Nét thanh nét đậm, thư pháp | Bút lông đầu cứng (fude) | Tombow Fudenosuke đầu cứng; Pentel Fude Touch; Uni Pin Brush | Đổi độ ép là đổi bề rộng nét, viết được khi giữ thẳng đứng |
   | Giấy bóng / couché | Bút lông dầu ngòi nhỏ | Staedtler Lumocolor permanent S (0,4 mm) / F (0,6 mm) | Bám bề mặt trơn, hãng ghi mở nắp nhiều ngày không khô |

2. **Bút máy (fountain pen) để sang giai đoạn sau.** Bút máy cho nét giống thư cũ nhất, nhưng viết tốt nhất ở góc khoảng 45°, trong khi robot đang giữ bút 90°. Cần đồ gá nghiêng và thử các nét đẩy ngược ngòi trước khi bán. Danh mục hiện đang bật bút `FOUNT`: nên thử ngay hoặc tạm tắt (mục 9).
3. **Mực cho phục dựng nên là mực pigment** (bền sáng, chống nước) vì thư phục dựng là kỷ vật. Màu nên có: đen, xanh bi, xanh đen, nâu sepia, tím, xám đậm.
4. **Giấy cho thư: không tráng phủ, mặt mịn, 90 đến 120 gsm, không axit (ISO 9706).** Giấy dày nằm phẳng hơn, mà lực ép của robot phụ thuộc độ phẳng của giấy.
5. **Ảnh cho UI nên là ảnh quét bản robot tự viết** (mục 7), không tải ảnh của hãng về dùng: đúng với sản phẩm thật và không vướng bản quyền.

## 2. Ràng buộc của hệ thống quyết định việc chọn bút

Lấy từ `docs/ROBOT_INTEGRATION.md`, `docs/UPGRADE_AI_ROBOT_PLAN.md` và danh mục trên Supabase ngày 2026-11-24.

| Ràng buộc | Giá trị hiện tại | Hệ quả khi chọn bút |
|---|---|---|
| Hướng bút | Cố định, vuông góc với giấy | Hợp: fineliner, bút kỹ thuật, gel, rollerball, bút lông đầu nhỏ. Bút bi viết được. Bút máy không ở góc lý tưởng |
| Lực ép | Lò xo, vòng hở theo độ nén Z; `f_target_n` 0,3 đến 1,0 N; sai số phụ thuộc độ phẳng giấy | Ưu tiên bút cần ít lực. Bút đổi nét theo lực (bút lông) sẽ lộ sai số lực thành sai số bề rộng nét |
| Tốc độ | `v_max_mm_s` 15 đến 40 mm/s (bài thử ISO cho bút bi chạy 75 mm/s) | Không lo đứt mực vì nhanh. Lo ngược lại: mực nước thấm nhiều khi đi chậm và đọng chấm ở đầu nét |
| Độ chính xác | NFR-04: lệch ≤ 0,5 mm | Cần ngòi cứng, thân bút tròn hoặc lục giác đều, không có đệm cao su ở chỗ kẹp. Bút bấm có độ rơ ở ngòi |
| Thời gian mở nắp | Một trang viết hàng chục phút, có thời gian chờ giữa các job | Bút mau khô ngòi sẽ hỏng nét đầu. Cần số liệu "mở nắp bao lâu" |
| Tiếng Việt có dấu | Chữ 5 mm vẫn phải rõ dấu (ệ, ỗ, ằ) | Thư cỡ chữ nhỏ cần nét ≤ 0,5 mm (suy luận, cần thử) |
| Tay kẹp | JODELL EPG40-050 | Chưa có số đo đường kính / khối lượng bút tối đa trong tài liệu. Tham khảo: máy AxiDraw nhận bút tới 16 mm, 45 g |

## 3. So sánh các loại bút với cách viết của robot

| Loại | Giữ thẳng đứng | Lực cần | Tuổi thọ ngòi | Mở nắp lâu | Bền sáng / chống nước | Ghi chú |
|---|---|---|---|---|---|---|
| Fineliner pigment | Tốt (suy luận: cùng kiểu ngòi ống thẳng với bút kỹ thuật, loại mà wiki AxiDraw ghi là giữ thẳng đứng) | Rất nhẹ | Ngòi sợi / nhựa mòn nhanh trên giấy nhám | Staedtler: 18 giờ (cỡ 0,05 đến 0,8 mm) | Có | Nét đều, đúng cỡ |
| Rollerball mực nước | Tốt | Nhẹ | Ngòi kim loại, bền | Chưa có số liệu | Tuỳ loại: uni-ball Eye mực pigment (không phải màu nào cũng chống nước) | Wiki AxiDraw chọn Pilot Precise V5 cho bản vẽ nhiều màu cần chính xác |
| Gel | Tốt | Nhẹ đến vừa | Ngòi kim loại | Chưa có số liệu | Loại pigment thì có | Có thể đứt nét trên giấy có vân; màu đục viết được giấy tối |
| Bút bi gốc dầu | Viết được | Lớn nhất: bài thử ISO 12757-1 dùng 1,5 N, góc khoảng 75° | Bền nhất, viết xa nhất | Không khô | Loại "documentary" (ISO 12757-2) thì có | Máy không có lò xo ép thì viết bút bi không đều; robot này có lò xo |
| Bút lông đầu cứng (fude) | Tốt | Nhẹ; lực quyết định bề rộng nét | Ngòi sợi, mòn | Chưa có số liệu | Tuỳ loại (Uni Pin Brush, Pigma Brush là pigment) | Cần hiệu chuẩn lực → bề rộng |
| Bút lông dầu ngòi nhỏ | Tốt | Nhẹ | Ngòi sợi mòn dần từ nhọn thành bẹt | Lumocolor: nhiều ngày (một nhà bán ghi tối đa 2 ngày) | Có | Thấm xuyên giấy mỏng không tráng phủ |
| Bút máy | Không lý tưởng: nên 45° | Gần như bằng 0 | Ngòi kim loại, rất bền | Dễ khô hơn mong muốn (wiki AxiDraw nói về Pilot Metropolitan) | Tuỳ mực | Lượng mực ra đổi theo tốc độ; cần bảo dưỡng |
| Bút sơn (Posca) | Viết được | Phải lắc và ấn ngòi để ra mực | - | Khô giữa chừng khi viết lâu | Có | Không hợp robot |

Số liệu đáng chú ý:

- Hội đồng Người tiêu dùng Hồng Kông cho máy vẽ xoắn ốc tới hết mực: bút bi trung bình **1.052 m**, bút gel trung bình **699 m**; các bút cùng mẫu lệch nhau tới hơn 9 %.
- Hệ thống đã ghi `total_stroke_mm` cho mỗi phác thảo và có trường `specs.line_life_m` cho bút, nên đếm được khi nào cần thay bút (việc chưa làm, chỉ là gợi ý).

## 4. Bộ bút đề xuất theo chức năng

### 4.1 OT-1: phục dựng chữ viết tay từ ảnh cũ

Mục tiêu là bản viết lại nhìn giống bản gốc và giữ được lâu.

| Bản gốc viết bằng | Giai đoạn 1 (giữ bút thẳng đứng) | Giai đoạn 2 (có đồ gá nghiêng 45°) |
|---|---|---|
| Bút bi | Bút bi mực loãng 0,5 hoặc 0,7 mm, xanh / đen | Như giai đoạn 1 |
| Bút máy, bút chấm mực, nét đều | Fineliner pigment chọn cỡ gần bề rộng nét gốc (0,1 / 0,3 / 0,5 mm) | Bút máy ngòi EF / F |
| Bút máy nét thanh nét đậm | Bút lông đầu cứng, đổi lực theo `width_hint` của từng nét | Bút máy ngòi mềm hoặc ngòi lá tre |
| Bút chì | Chưa có loại bút tương ứng trong enum `pen_category`. Tạm thời: fineliner xám (Uni Pin có xám đậm, xám nhạt) | Thêm loại bút chì nếu cần (đổi DB) |

- Phần "bản gốc viết bằng gì" là suy luận từ thói quen viết ở Việt Nam (bút máy mực tím / xanh đen, sau này là bút bi), chưa có nguồn kiểm chứng.
- Bút lông ở chế độ đổi lực phụ thuộc vào bảng hiệu chuẩn lực → bề rộng nét (kế hoạch U9), chưa có.
- Bút máy luyện chữ bán ở Việt Nam có hai kiểu ngòi: **lá tre** (tạo nét thanh đậm, hợp chữ cỡ vừa đến to) và **kim tinh** (nét mảnh). Đây là ứng viên rẻ cho giai đoạn 2.

### 4.2 OT-3: viết theo mẫu chữ (thư, thiệp, lời chúc)

- Gel 0,38 / 0,5 mm làm bút mặc định: nhiều màu, tên màu chính hãng rõ ràng.
- Thiệp nền tối: gel trắng / vàng / bạc. uni-ball Signo Broad UM-153 có bi 1,0 mm nhưng nét thật khoảng 0,6 mm. Mẹo của người dùng máy vẽ: chạy mỗi nét hai lần, lượt sau ngược chiều, để nét đục đều.
- Tiêu đề kiểu thư pháp: bút lông đầu cứng.
- Giấy couché / mặt bóng của giấy Ivory: bút bi hoặc bút lông dầu ngòi nhỏ.

### 4.3 OT-2: viết bằng nét chữ của khách (đang tắt)

Dùng chung bút với OT-3: gel hoặc fineliner. Không cần loại riêng.

### 4.4 Ứng viên cụ thể

| Loại (`pen_category`) | Ứng viên | Thông tin đã kiểm chứng từ nguồn |
|---|---|---|
| FINELINER | **Staedtler pigment liner 308** | Cỡ 0,05 / 0,1 / 0,2 / 0,3 / 0,4 / 0,5 / 0,6 / 0,7 / 0,8 / 1,0 / 1,2 mm. Mực pigment, không tẩy được (theo ISO 12757-2), bền sáng, chống nước trên giấy. Mở nắp 18 giờ không khô (ISO 554) với cỡ 0,05 đến 0,8 mm; vài trang khu vực ghi 12 giờ |
| FINELINER | **Uni Pin** | Mực đen có cỡ 0,03 đến 1,2 mm và ngòi brush. Có sepia, xám đậm, xám nhạt (số cỡ tuỳ nơi bán). Mực pigment "Super Ink" chống phai, chống nước. Một người đánh giá thấy màu sepia gần như đen |
| FINELINER | **Sakura Pigma Micron** | Số trên bút không phải mm: 003 = 0,15; 005 = 0,20; 01 = 0,25; 02 = 0,30; 03 = 0,35; 05 = 0,45; 08 = 0,50; 10 = 0,60; 12 = 0,70 mm. Mực pigment lưu trữ, chống nước. Đen có mọi cỡ; xanh, đỏ, lục, nâu, sepia chỉ có ở vài cỡ |
| GEL | **uni-ball Signo** | Wiki AxiDraw nêu tên. Signo Broad UM-153 (trắng, vàng, bạc): mực pigment đục, chống nước, viết tốt trên giấy tối |
| GEL | **Pilot G2** | Wiki AxiDraw nêu tên; một người đánh giá ghi nét vẫn liền ở tốc độ vẽ cao nhất. Là bút bấm (có độ rơ ở ngòi, cần thử NFR-04) |
| GEL | **Zebra Sarasa Clip** | Bộ Vintage 0,5 mm có Sepia Black, Dark Gray, Bordeaux Purple, Cassis Black, Camel Yellow; mực gel pigment gốc nước. Chưa thấy nguồn xác nhận chống nước |
| GEL | **Sakura Gelly Roll** | Trắng, nhũ, nhiều màu; 3 cỡ nét. Nên chạy chậm để khỏi phải đi nét lần hai |
| BALLPOINT | **Uni Jetstream** | Mực gốc dầu độ nhớt thấp, ra mực nhẹ tay hơn bút bi thường. Có 0,38 / 0,5 / 0,7 / 1,0 mm. Một nhà bán ghi Jetstream hết mực nhanh hơn bút bi khác |
| BALLPOINT | **Thiên Long** (TL-027, TL-095…) | Bán rộng rãi ở Việt Nam, ngòi 0,5 mm, có mực tím. Chưa có số liệu lực viết hay độ bền mực |
| BRUSH | **Tombow Fudenosuke đầu cứng** | Ít mềm, kiểm soát tốt, hợp chữ nhỏ |
| BRUSH | **Pentel Fude Touch Sign Pen** | Mềm hơn Fudenosuke đầu cứng, đổi nét nhiều hơn theo lực. Mực gốc nước, có thể thấm trên giấy mỏng |
| MARKER | **Staedtler Lumocolor permanent** | S ≈ 0,4 mm, F ≈ 0,6 mm, M ≈ 1,0 mm, B 1,0 đến 2,5 mm. "DRY SAFE": mở nắp nhiều ngày không khô |
| MARKER | **Sharpie Ultra Fine** | Wiki AxiDraw dùng cho bản vẽ tô nhiều màu. Ngòi sợi mòn dần |
| (chưa có trong enum) | **Rollerball mực nước**: Pilot Precise V5 (theo hiểu biết của người viết, ở châu Á bán dưới tên Hi-Tecpoint V5), uni-ball Eye UB-157 | V5 là lựa chọn của wiki AxiDraw cho bản vẽ nhiều màu cần chính xác. UB-157: bi 0,7 mm, nét khoảng 0,5 mm, mực pigment; người dùng báo chỉ một số màu chống nước |
| FOUNTAIN (giai đoạn 2) | Pilot Kakuno; Platinum Preppy; Lamy Safari F / M | Kakuno: dung sai chặt, đổi cụm ngòi được khi thân còn kẹp trên máy. Preppy: rẻ, dung sai không đều giữa các cây. Safari: wiki AxiDraw ghi ra mực rất đều ở nhiều tốc độ, không tắc |

## 5. Mực và màu

- **Ưu tiên mực pigment cho mọi sản phẩm khách giữ lâu.** Fineliner pigment, gel pigment và mực pigment cho bút máy đều chống nước và bền sáng hơn mực nhuộm (dye).
- **Màu nên có cho phục dựng:** đen, xanh bi, xanh đen, nâu sepia, tím, xám đậm. Danh mục hiện chỉ có đen, xanh dương, đỏ và một màu xanh đen cho bút máy.
- **Màu cho thiệp:** thêm trắng, nhũ vàng, nhũ bạc (chỉ viết trên giấy tối), đỏ đô.
- **Mực bút máy (giai đoạn 2):**

  | Mực | Tính chất | Lưu ý |
  |---|---|---|
  | Platinum Carbon Black | Pigment carbon, chống nước, lưu trữ | Hạt carbon có thể làm tắc bút nếu để lâu: rửa bút ít nhất mỗi tuần |
  | De Atramentis Document | Chống nước, lưu trữ, pha màu được | Dùng khi cần màu bền ngoài đen |
  | Pilot Iroshizuku (24 màu) | Ra mực đều, không tắc | Người dùng máy vẽ khuyên dùng; các nguồn đã đọc không ghi chống nước |
  | Platinum Classic (Sepia Black, Cassis Black, Lavender Black…) | Có sắt: viết ra nhạt rồi sẫm dần trong 1 đến 24 giờ, chống nước tăng theo thời gian | Mực khô tay, cần bút dễ rửa. Sepia Black hợp vẻ thư cũ |
- **Mã màu `hex_code`:** không nên chép mã màu trên mạng. Nên lấy từ ảnh quét bản robot viết (mục 7) và ghi nguồn `MEASURED` trong `specs`.

## 6. Giấy

| Nhóm trong danh mục (`surface`) | Loại giấy thực tế | Bút hợp | Bút cần tránh hoặc phải thử |
|---|---|---|---|
| PLAIN | Giấy Fort (không tráng phủ) 80 đến 100 gsm | Fineliner, gel, bút bi, rollerball | Bút lông dầu (thấm xuyên), bút lông (thấm loang trên giấy mỏng) |
| ART | Giấy thư cao cấp không tráng phủ 90 đến 120 gsm: Clairefontaine Triomphe 90 gsm, Rhodia 80 đến 90 gsm, Midori MD khoảng 80 gsm, Conqueror (Arjowiggins) | Tất cả, kể cả bút máy | Giấy có vân nổi (laid, linen): ngòi nhỏ và gel dễ đứt nét |
| CARD | Ivory 250 / 300 gsm (thường một mặt nhám, một mặt bóng), Bristol 230 đến 350 gsm | Mặt nhám: gel, fineliner, bút bi. Mặt bóng: bút bi, bút lông dầu | Mực nước trên mặt bóng |
| COATED / GLOSSY | Couché 80 đến 300 gsm (tráng cao lanh) | Bút bi gốc dầu, bút lông dầu ngòi nhỏ | Gel, fineliner, bút lông gốc nước: phải thử thời gian khô và độ lem |
| (chưa có) | Kraft 50 đến 175 gsm | Gel trắng, mực tối màu | Hút mực mạnh: thử độ loang |

- **Giấy cho bút máy:** Tomoe River (52 gsm) chịu mực ướt tốt nhất nhưng lâu khô và mỏng; Clairefontaine và Rhodia mịn nhất, ít loang; Midori MD khô nhanh hơn Tomoe River. Định lượng gsm không nói lên độ chịu mực: lớp gia keo và lớp phủ quan trọng hơn.
- **Độ phẳng (suy luận từ cách robot ép bút):** lực viết = độ nén lò xo, nên tờ giấy vênh 0,5 mm đã đổi lực đáng kể. Giấy 90 đến 120 gsm nằm phẳng hơn giấy 52 đến 80 gsm. Giấy rất mỏng cần kẹp hoặc bàn hút.
- **Độ bền của giấy:** giấy "permanent" theo ISO 9706 (bản 1994) có pH 7,5 đến 10 và lượng dự trữ kiềm ≥ 2 % CaCO3; bản 2025 đổi cách đo pH và giới hạn chất dễ oxy hoá. Tiêu chuẩn này áp dụng cho giấy, không áp dụng cho bìa. Khi mua giấy cho đơn phục dựng nên hỏi nhà cung cấp chứng nhận này.
- **Vẻ thư cũ:** giấy màu kem / ngà không tráng phủ 100 đến 120 gsm. Giấy dó và giấy xuyến chỉ rất hút mực, không phẳng, chỉ hợp bút lông: chưa nên đưa vào danh mục (suy luận).

## 7. Ảnh giấy, bút, mực cho UI

Nhóm cần ảnh nét bút và màu mực để FE hiển thị đúng. Có hai nguồn ảnh:

| Nguồn | Ưu | Nhược |
|---|---|---|
| Ảnh của hãng / nhà bán (đường dẫn ở mục 10) | Có sẵn, đẹp | Có bản quyền, không được tự ý chép về hay nhúng thẳng. Màu trên ảnh quảng cáo không khớp nét robot viết trên giấy của xưởng |
| **Ảnh quét bản robot tự viết (khuyến nghị)** | Đúng sản phẩm thật, của riêng xưởng, lấy luôn được mã màu và bề rộng nét đo thật | Tốn một buổi viết và quét |

Cách làm đề xuất:

1. Với mỗi bút + mực, cho robot viết một thẻ mẫu cố định: một đường thẳng, một đường lượn, dòng chữ "Nét Việt" và một ô tô kín.
2. Quét 600 dpi, cắt cùng một khung, nền là chính loại giấy đó.
3. Tải lên bằng API ảnh danh mục (migration 0030, đang làm): `PUT /manager/pens|inks|papers/{id}/image`. FE nhận `image_url` từ catalog.
4. Lấy mã màu trung bình của ô tô kín làm `hex_code`; ghi bề rộng nét đo được vào hồ sơ vật tư (`material_profiles.line_width_mm`).
5. Ảnh giấy: quét một góc tờ giấy trắng dưới cùng ánh sáng, để thấy màu và vân giấy.

Trước khi có ảnh, FE giữ cách hiển thị hiện tại (vạch theo bề rộng nét, chấm màu theo `hex_code`).

## 8. Bài thử trên robot để chốt loại tốt nhất

Chạy cho từng ứng viên, trên ba loại giấy (PLAIN 80 gsm, ART 120 gsm, CARD 250 gsm):

| Bài thử | Cách làm | Đo gì |
|---|---|---|
| Lực | Viết cùng một dòng ở `f_min`, `f_target`, `f_max` | Nét có liền không, bề rộng nét, vết hằn giấy |
| Tốc độ | 10 / 20 / 40 mm/s | Đứt nét, đọng mực, bề rộng |
| Đầu nét | 20 lần hạ bút liên tiếp | Chấm mực ở đầu nét |
| Chữ nhỏ có dấu | "Kính gửi quý khách ệ ỗ ằ ữ" ở cỡ 3, 5, 8 mm | Dấu có rõ không |
| Mở nắp | Dừng 5 / 15 / 30 / 60 phút rồi viết tiếp | Nét đầu có ra mực không |
| Khô và lem | Miết ngón tay sau 10 giây, 60 giây | Thời gian khô (`specs.drying_s`) |
| Nước | Nhỏ giọt nước sau 24 giờ | Chống nước (`specs.waterproof`) |
| Lệch vị trí | Chồng ảnh quét lên phác thảo | NFR-04 (≤ 0,5 mm) |
| Viết xa | Đếm `total_stroke_mm` tới khi nét nhạt | `specs.line_life_m` |

Tiêu chí chốt: đạt NFR-04 và NFR-05, không đứt nét sau 30 phút mở nắp, khô dưới 60 giây trên giấy bán kèm. Kết quả ghi vào `specs` với nguồn `MEASURED` và vào `material_profiles`.

## 9. Điểm cần xem lại trong danh mục hiện tại

| Điểm | Hiện trạng | Đề xuất |
|---|---|---|
| Bút máy `FOUNT` đang bật | Robot giữ bút 90°, bút máy nên viết ở 45° | Thử ngay; nếu nét không đều thì tạm tắt tới khi có đồ gá nghiêng |
| Giấy couché `COATED150_A4` | Đang cho phép gel, fineliner, bút lông | Thử độ lem; nhiều khả năng chỉ nên giữ bút bi và thêm bút lông dầu |
| Bút bi `BALL07` | `f_target_n` 1,0 N, `f_max_n` 1,4 N; bài thử ISO cho bút bi dùng 1,5 N | Chọn bút bi mực loãng, hoặc đo lại lực trên robot |
| Loại `MARKER` | Có trong enum, chưa có bút nào | Thêm một bút lông dầu ngòi nhỏ cho giấy bóng |
| Tên bút chung chung ("Gel pen 0.5 mm"), `specs` rỗng | Không biết là bút hãng nào | Sau khi thử, điền `specs.brand`, `supplier_sku`, `tip_mm`, `ink_base` |
| Màu mực | Đen, xanh dương, đỏ, xanh đen | Thêm sepia, tím, xám đậm cho OT-1; trắng, vàng, bạc cho thiệp tối màu |
| Rollerball, bút chì | Không có trong enum `pen_category` | Chỉ thêm (đổi DB) nếu nhóm quyết định bán |

## 10. Nguồn

Máy vẽ bút và cách chọn bút:
- [Pens for AxiDraw (Evil Mad Scientist wiki)](https://wiki.evilmadscientist.com/Pens_for_AxiDraw)
- [Why I use fountain pens with pen plotters (lostpixels.io)](https://lostpixels.io/writings/fountain-pens-plotters)
- [7 beautiful pens for AxiDraw (abakcus.com)](https://abakcus.com/7-beautiful-pens-for-axidraw)

Tiêu chuẩn và phép thử:
- [ISO 12757-1 (bút bi, bản xem trước)](https://cdn.standards.iteh.ai/samples/1129/d31cfcb55e2c4394a2d8c24916bd511a/ISO-12757-1-1998.pdf)
- [ISO 27668-1:2017 (bút gel)](https://standards.iteh.ai/catalog/standards/iso/5ce31887-f52c-412e-bd8c-98d285272755/iso-27668-1-2017)
- [Hội đồng Người tiêu dùng Hồng Kông: thử bút bi và bút gel](https://www.consumer.org.hk/en/press-release/p-557-ballpoint-pens-and-gel-ink-pens)
- [ISO 9706:2025 (giấy bền lâu)](https://standards.iteh.ai/catalog/standards/iso/46e7add9-ef1c-4c04-b7a5-610153fb4cfc/iso-9706-2025)
- [Thư viện Quốc hội Mỹ: so sánh các tiêu chuẩn giấy bền lâu](https://loc.gov/preservation/resources/rt/perm/pp_x3.html)

Bút (trang hãng hoặc nhà bán, có ảnh nét và bảng màu):
- [Staedtler pigment liner 308](https://www.staedtler.com/uk/en/products/products-for-colouring/fineliners/pigment-liner-308-fineliner-m308/)
- [Staedtler Lumocolor permanent](https://www.staedtler.com/us/en/products/markers/permanent-marker/)
- [uni PIN: các cỡ ngòi](https://uniball.co.uk/blog/2020/03/02/take-a-look-at-the-new-uni-pin-nib-sizes/)
- [Đánh giá bút Uni Pin (The Well-Appointed Desk)](https://www.wellappointeddesk.com/2019/11/pen-review-uni-pens/)
- [Sakura Pigma Micron 005 (Royal Talens)](https://www.royaltalens.com/products/sakura-pigma-micron-005-0-20-mm)
- [Sakura Pigma Micron: bảng cỡ (Currys)](https://currys.com/products/sakura-pigma-micron-single-pens)
- [Uni Jetstream: hướng dẫn toàn dòng (JetPens)](https://www.jetpens.com/blog/Uni-Jetstream-A-Comprehensive-Guide/pt/758)
- [So sánh bút bi mực loãng (The Gentleman Stationer)](https://www.gentlemanstationer.com/blog/2025/2/8/comparing-low-viscosity-ballpoint-pens-jetstream-vs-acroball-vs-anterique-vs-ohto)
- [uni-ball Signo Broad UM-153 trắng (Cult Pens)](https://cultpens.com/products/uni-ball-signo-broad-gel-rollerball-pen-um-153-white)
- [Zebra Sarasa Clip Vintage 5 màu](https://japanesetaste.com/products/zebra-sarasa-clip-vintage-color-gel-ink-pens-5-colors-0-5mm-jj15-5c-vi)
- [uni-ball Eye: đánh giá (Parka Blogs)](https://www.parkablogs.com/content/review-uni-ball-eye-rollerball-pen)
- [Tombow Fudenosuke đầu cứng và đầu mềm](https://thehappyevercrafter.com/blog/tombow-fudenosuke-hard-tip-vs-soft-tip/)
- [So sánh bút lông (JetPens)](https://www.jetpens.com/Compare?categories_id=221)

Mực bút máy:
- [Pilot Iroshizuku (Pilot châu Âu)](https://www.pilotpen.eu/our-universes/fine-writing/iroshizuku-inks/)
- [Platinum Carbon Black: đánh giá (Goulet Pens)](https://www.gouletpens.com/blogs/fountain-pen-blog/platinum-carbon-black-fountain-pen-ink-review)
- [Platinum Classic, mực có sắt (Wonder Pens)](https://wonderpens.ca/blogs/pens-and-things/platinum-classic-iron-gall-inks)
- [Bảng màu Diamine do cộng đồng làm (Mountain of Ink)](https://mountainofink.com/blog/diamine-ink-chart)

Giấy:
- [Thứ bậc giấy hợp bút máy (The Gentleman Stationer)](https://www.gentlemanstationer.com/blog/2021/3/10/hierarchies-of-fountain-pen-friendly-paper)
- [Giấy tốt cho mực bút máy (FPR)](https://fprevolutionusa.com/blogs/news/best-papers-fountain-pen-ink)
- [Các loại giấy in thông dụng (meta.vn)](https://meta.vn/hotro/cac-loai-giay-in-16769)
- [Giấy Ford là gì (FPT Shop)](https://fptshop.com.vn/tin-tuc/dien-may/giay-ford-174000)
- [Giấy Conqueror là gì (FPT Shop)](https://fptshop.com.vn/tin-tuc/dien-may/giay-conqueror-174672)
