# 08 — Kịch bản demo và câu hỏi phản biện

Chỉ dùng chức năng đã có trong code. Chỗ nào chưa kiểm chứng trên robot thật được ghi rõ.

## 1. Thông điệp chính

- **Bài toán:** thư tay, lời chúc, bút tích cũ có giá trị vì là nét mực thật. In không thay được, viết tay số lượng lớn thì không đủ người.
- **Người dùng:** khách đặt viết; xưởng (Staff, kỹ thuật viên, Manager) vận hành.
- **Giải pháp:** chuỗi khép kín từ yêu cầu của khách tới nét mực trên giấy, trong đó AI hỗ trợ soạn và dựng nét, con người duyệt ở các điểm quyết định, và robot chỉ nhận đúng bản đã được duyệt.
- **Đầu ra:** tờ giấy viết bằng bút thật, kèm dòng xác thực và thẻ chứng nhận có mã QR.
- **Một câu để nhớ:** "Thứ robot viết là đúng bản khách đã xem và đã trả tiền, và hệ thống chứng minh được điều đó."

## 2. Ba nhóm demo

### Demo 1 — Luồng hoàn chỉnh (10–12 phút)

Dùng đơn OT-3 (viết theo mẫu) vì ổn định nhất.

| Bước | Thao tác | Điểm cần nói |
|---|---|---|
| 1 | Khách tạo đơn, gõ một câu tiếng Việt có đủ dấu, chọn giấy và bút | Vật tư được kiểm tương thích; giá ước tính tính ngay |
| 2 | Nhờ trợ lý AI đổi bố cục, rồi sửa một từ | AI gọi hàm của hệ thống, không tự vẽ nét; mỗi thay đổi có lịch sử |
| 3 | Gửi đơn; Staff nhận, xem phác thảo, chốt bản final | Nhãn "tái tạo bằng AI" trên ảnh xem trước |
| 4 | Staff lập báo giá, chỉnh giá vượt ngưỡng → Manager duyệt | Luật ±15% và phân quyền |
| 5 | Khách duyệt và đặt cọc (MOCK, nói rõ) | Bản ghi duyệt lưu hash phác thảo và IP |
| 6 | Manager xếp lịch | Gói sản xuất được ký; lịch không trùng được |
| 7 | Kỹ thuật viên tải gói, hiệu chuẩn, chạy mô phỏng 3D | Máy trạm kiểm chữ ký và hash |
| 8 | Robot viết | **Trực tiếp nếu đã tập thành công; nếu không thì mô phỏng + video quay trước, nói rõ** |
| 9 | Chụp ảnh, QC, khách nghiệm thu, thanh toán cuối, bàn giao | Thẻ chứng nhận QR |

Chuẩn bị trước: đơn mẫu ở từng trạng thái, để nhảy cóc nếu một bước chậm.

### Demo 2 — Xử lý tình huống bất thường (3–4 phút, chọn hai)

| Tình huống | Cách làm | Ổn định |
|---|---|---|
| File quỹ đạo bị sửa sau khi khách duyệt | Trên mô phỏng: đổi một byte, tải gói → `PRODUCTION_PACKAGE_INVALID`, có sự cố và nhật ký | Cao (có test) |
| Hai Staff cùng nhận một đơn | Hai trình duyệt bấm cùng lúc → một người nhận `ALREADY_ASSIGNED` | Cao |
| Callback thanh toán gửi hai lần | Gửi lại webhook → `ALREADY_PROCESSED`, đơn không đổi | Cao |
| Gọi thẳng API để nhảy trạng thái | Gọi chuyển trạng thái sai → `409 STATE_CONFLICT` từ trigger database | Cao |
| Khách huỷ sau khi đã cọc | Xem trước số hoàn theo BR-14/16, huỷ, Staff xác nhận hoàn | Cao |
| Mất liên lạc với backend khi đang viết | Trên mô phỏng: ngắt mạng → agent viết nốt nét rồi tạm dừng | Trung bình; chỉ làm trên mô phỏng |

Cập nhật 2026-11-28: TP-01 và TP-02 đã sửa và có test, nên có thể thêm hai tình huống trên mô phỏng: báo sự cố khi đang có lần chạy mở thì backend tự xếp lệnh STOP; còn cảnh báo đỏ thì lệnh RUN bị từ chối `RED_ALERT_OPEN` cho tới khi Manager đóng. Chưa thử hai tình huống này trên robot thật.

### Demo 3 — Điểm nhấn kỹ thuật (4–5 phút, chọn hai)

| Điểm nhấn | Cách làm |
|---|---|
| Từ ảnh thư tay tới đường nét | Tải ảnh thư trên vở kẻ; cho xem từng bước: tờ giấy được tìm, dòng kẻ bị bỏ, khung xương, nét có chấm đầu; danh sách thứ đã loại |
| Ghép dấu tiếng Việt | Gõ "Nguyễn Thị Hường, Đà Nẵng" với ba font khác nhau |
| Tối ưu thứ tự nét | Hai ảnh trước / sau với quãng nhấc bút được vẽ ra |
| Nhãn vùng phục dựng | Ảnh có vùng mực phai → vùng `RESTORED` hiện cho khách |
| Chuyển động có kiểm | Xem 3D: nhấc bút, hạ bút, tốc độ chậm lại ở chỗ cong (trên mô phỏng) |

## 3. Phương án dự phòng

| Sự cố | Dự phòng | Phải nói với hội đồng |
|---|---|---|
| Robot hoặc máy trạm lỗi | Video một lần viết thật quay liên tục + bản viết thật mang theo + mô phỏng 3D trực tiếp | "Đây là video quay ngày …; phần đang chạy là mô phỏng" |
| Mất Internet | Chạy BE + Postgres cục bộ trên laptop (đã chứng minh dựng được trong vài phút), web trỏ về localhost | "Đang chạy bản cục bộ" |
| LLM lỗi hoặc hết hạn mức | Sửa đơn bằng form; trợ lý trả `AI_UNAVAILABLE` là hành vi đúng thiết kế | "Trợ lý là phần hỗ trợ, đơn vẫn làm được bằng form" |
| Render ngủ hoặc chậm | Mở trang trước 5 phút; dự phòng bản cục bộ | — |
| Storage lỗi | Dùng đơn OT-3 (không cần ảnh) | — |
| Thanh toán | Luôn MOCK khi demo | "Cổng ở chế độ thử; payOS thật đã chạy một giao dịch ngày 2026-10-22" |

Không dùng video dựng sẵn mà không nói. Không gọi mô phỏng là robot thật.

## 4. Giới hạn nên chủ động nêu

Nêu trước khi bị hỏi thì được điểm trung thực:
1. Robot mới viết thử; tốc độ còn chậm.
2. Điều khiển vị trí vòng hở, lực tì bằng lò xo thụ động; cảm biến lực là bước tiếp theo.
3. Phục dựng chữ viết tay là thị giác máy tính cổ điển, không phải mô hình học sâu.
4. "Viết bằng nét chữ của bạn" (OT-2) đang nghiên cứu, chưa mở.
5. Thanh toán và vận chuyển trong demo ở chế độ thử.
6. Số đo chất lượng hiện có là trên ảnh tổng hợp.

## 5. Câu hỏi phản biện và câu trả lời

Mỗi câu trả lời dựa trên code hiện có. **[Cần bổ sung]** = chưa đủ bằng chứng, phải làm thêm trước buổi bảo vệ.

**Tính thực tế và khác biệt**

1. *Vì sao không dùng máy in hoặc máy vẽ (plotter)?*
Máy in không cho nét mực có độ đậm nhạt và vết tì của bút thật. Máy vẽ làm được nét bút, và về bản chất đầu ra của hệ thống này là đường nét mà máy vẽ cũng chạy được. Cánh tay 6 trục cho ba thứ máy vẽ phẳng không có: giữ bút nghiêng theo góc, viết trên vật không phẳng hoặc không nằm sẵn trên bàn máy, và dùng lại được cho việc khác. Nói thật: với giấy phẳng khổ A4, máy vẽ rẻ và nhanh hơn; lựa chọn robot là theo định hướng đề tài. **[Cần bổ sung]** một ví dụ cụ thể mà máy vẽ không làm được, nếu muốn nhấn điểm này.

2. *Giá trị khác biệt của hệ thống là gì?*
Không phải "robot viết được chữ". Là chuỗi khép kín có kiểm soát: bản khách duyệt được niêm bằng hash và chữ ký, máy chỉ chạy đúng bản đó; cộng với toàn bộ nghiệp vụ của một xưởng (báo giá, cọc, lịch, kho, QC, giao hàng, hoàn tiền).

3. *Ai sẽ trả tiền cho dịch vụ này?*
Người cần thư tay số lượng vừa (thiệp cưới, thư cảm ơn khách hàng) và người muốn chép lại bút tích cũ. **[Cần bổ sung]** chưa có khảo sát thị trường hay đơn thật trong repo.

**AI**

4. *AI ở đây làm gì? Có phải chỉ gọi ChatGPT?*
Có hai phần tách biệt. Phần dựng nét là thị giác máy tính và hình học tự cài đặt, không dùng mô hình ngôn ngữ. Phần trợ lý dùng mô hình ngôn ngữ để hiểu yêu cầu và gọi 14 hàm của hệ thống; nó không sinh toạ độ, không đổi giá, không gửi đơn.

5. *Mô hình bịa thì sao?*
Tham số của mọi hàm đi qua đúng luật của form; id không tồn tại thì hàm trả lỗi. Sửa nét chỉ nhận tên lệnh và id, có giới hạn theo loại đơn và kiểm nét ngoài vùng không đổi. Thay đổi được lưu thành đề xuất kèm hash trạng thái gốc. Bản tới robot còn phải qua Staff chốt và khách duyệt.
Nói thật khi bị hỏi sâu: giao diện hiện tự áp dụng đề xuất và có nút hoàn tác; một số trường (số bản, ghi chú) chưa hoàn tác được.

6. *Hệ thống có học được nét chữ của một người không?*
Không. Hiện có hai khả năng: chép lại nét mực từ ảnh, và viết theo font một nét. Có code thử nghiệm số hoá bộ chữ cái của một người từ phiếu mẫu rồi ghép lại; chưa mở cho khách và chưa đo trên người thật. Khảo sát của nhóm cho thấy chưa có mô hình sẵn cho tiếng Việt (`docs/benchmarks/O1b_model_survey_2026-11-20.md`).

7. *Dữ liệu khách có gửi cho bên thứ ba không?*
Nội dung chat với trợ lý có, sau khi khách đồng ý chính sách theo phiên bản; tóm tắt đơn gửi đi không có tên, email, số điện thoại. Ảnh thư chỉ gửi đi khi khách bấm "đọc chữ" và đồng ý từng lần; tính năng này mặc định tắt. Phần dựng nét chạy hoàn toàn trên máy chủ.

**Độ chính xác**

8. *Độ chính xác bao nhiêu? Đo thế nào?*
Phục dựng: F1 đường tâm 94,88% trên 220 ảnh tổng hợp tạo từ 22 ảnh quét thật với 10 loại nhiễu. Đây là số đo trên tập có kiểm soát, chưa phải trên ảnh khách. Bản viết của robot: **[Cần bổ sung]** chưa có số đo; công cụ đo (so ảnh bản viết với phác thảo theo mm) đã có nhưng chưa hiệu chuẩn.

9. *Con số "độ giống 98%" trên màn hình nghĩa là gì?*
Là mức nét bám theo mực mà hệ thống đã giữ lại sau khi lọc. Nó cho biết bước dò nét có bỏ sót không, không phải độ chính xác so với chữ gốc.

10. *Thứ tự nét có giống người viết không?*
Là suy đoán có quy tắc: theo dòng, theo từ, chữ gốc trước dấu sau. Chưa đo được vì không có quỹ đạo bút gốc để so. Với robot, thứ tự nét ảnh hưởng thời gian chứ không ảnh hưởng hình dạng.

**Robot và an toàn**

11. *Robot đã viết thật chưa?*
Đã chạy trên FAIRINO FR3: chạy thử nhấc bút 45/45 nét và viết có mực. **[Cần bổ sung]** một lần viết trọn trang có video và log; hiện mới có ghi chép về 2 nét đầu.

12. *Điều khiển lực thế nào? Vòng kín hay vòng hở?*
Vòng hở theo vị trí. Lực tì do lò xo trong gripper giữ; độ nhấn tính theo F = k·x. Vị trí thật của đầu bút được đọc về để chặn bắt đầu khi lệch, chờ tới đích và dừng khi lệch quá ngưỡng, nhưng không dùng để sửa quỹ đạo. Cảm biến Hall đã có code giao thức và bộ giám sát, chưa nối phần cứng.

13. *Nếu phần mềm ra lệnh sai thì sao?*
Nhiều lớp: gói phải đúng chữ ký; kế hoạch được kiểm trong giấy, tầm với, hộp làm việc; mỗi lệnh chỉ dài tối đa 5 mm; không bao giờ gửi lại lệnh chuyển động; lệnh dừng đi kênh riêng; thiếu số đo thì từ chối chạy; chạy thật cần bật tại máy trạm, có mã xác nhận theo đúng kế hoạch và một lần chạy thử. Lớp cuối là E-Stop vật lý và phát hiện va chạm của bộ điều khiển.
Nói thật: phần mềm không kiểm va chạm; sàn Z hiện dựa vào hiệu chuẩn.

14. *Mất mạng hoặc mất điện giữa chừng?*
Mất liên lạc với backend quá 6 giây: viết nốt nét rồi tạm dừng. Lỗi kết nối tới bộ điều khiển: vào trạng thái "chưa rõ", cần người xác nhận. Tiến độ ghi ra file trước và sau mỗi nét nên tiếp tục đúng nét. Đã kiểm trên mô phỏng, chưa trên robot.

15. *Làm sao biết bản robot viết khớp với phác thảo?*
Hiện là người: kỹ thuật viên chụp ít nhất hai ảnh và chấm QC, khách nghiệm thu. Có công cụ so ảnh với phác thảo ra số mm nhưng mới là tham khảo.

**Vận hành**

16. *Khách đổi ý sau khi đã cọc?*
Phác thảo đã khoá. Khách huỷ được khi chưa viết, hoàn tiền theo quy tắc; có màn xem trước số hoàn. Chưa có luồng "sửa rồi duyệt lại" sau cọc.

17. *Robot hỏng giữa đơn?*
Kỹ thuật viên báo sự cố, job thành hỏng, đơn quay về hàng đợi xếp lịch, Manager nhận thông báo và xếp lại. Ngày giao dự kiến tự dời. (Sau khi sửa TP-01, hệ thống sẽ tự gửi lệnh dừng.)

18. *Một ngày làm được bao nhiêu đơn? Chi phí?*
**[Cần bổ sung]** Chưa có số đo thời gian viết thật; mô hình ước lượng dùng hằng số giả định. Cần đo một trang chuẩn rồi mới trả lời.

19. *Mở rộng lên nhiều robot, nhiều xưởng?*
Mô hình dữ liệu đã theo robot và kỹ thuật viên, lịch chống trùng ở database, mỗi robot một agent riêng. Backend hiện chạy một tiến trình với một số trạng thái trong bộ nhớ; muốn chạy nhiều tiến trình phải chuyển phần đó ra ngoài.

**Bảo mật và dữ liệu**

20. *Khách này xem được đơn của khách khác không?*
Không. Mọi truy vấn phía khách lọc theo chủ đơn và trả 404; có test tự động cho ma trận quyền trên mọi route.

21. *Thanh toán có an toàn không?*
Đơn chỉ đổi trạng thái từ callback máy chủ có chữ ký, kiểm số tiền, xử lý trùng. Chế độ demo là thử nghiệm. payOS thật đã chạy một giao dịch.

22. *Ảnh thư của khách lưu bao lâu?*
Thiết kế là xoá sau 90 ngày, bằng tác vụ nền có công tắc. **[Cần bổ sung]** xác nhận công tắc và tác vụ nền đang bật trên máy chủ.

**Đóng góp và giới hạn**

23. *Nhóm tự làm phần nào, dùng sẵn phần nào?*
Tự làm: pipeline dò nét (làm mảnh, đồ thị khung xương, ghép cạnh, thứ tự đọc), khử nhiễu giấy, ghép dấu tiếng Việt, tối ưu thứ tự nét, lập kế hoạch chuyển động và bộ kiểm, cơ chế gói ký, toàn bộ nghiệp vụ. Dùng sẵn: OpenCV cho phép toán ảnh cơ bản, font Hershey, mô hình ngôn ngữ qua API, SDK và bộ điều khiển FAIRINO (động học ngược và nội suy nằm trong bộ điều khiển), PyBullet cho mô phỏng.

24. *Giới hạn lớn nhất hiện nay và hướng tiếp?*
Ba thứ: chưa có số đo trên bản viết thật; điều khiển lực chưa có phản hồi; tốc độ viết chậm. Hướng tiếp: nối cảm biến Hall, chuyển động liên tục thay cho từng đoạn, đo sai lệch bằng công cụ so ảnh, rồi mới tới nét chữ cá nhân.

## 6. Bằng chứng cần thu trước buổi bảo vệ

- Video liên tục một lần viết trọn trang, kèm `run-*.jsonl` và `progress.json`.
- Ảnh bản viết đặt cạnh phác thảo, có thước; kết quả công cụ so ảnh trên ảnh đó.
- Thời gian viết một trang chuẩn.
- Video thử tạm dừng, dừng, tiếp tục đúng nét.
- Bảng đo độ cứng lò xo và các điểm dò.
- Ảnh màn hình phiên bản bộ điều khiển và SDK.
- Biên bản thử E-Stop vật lý.
