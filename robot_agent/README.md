# VHRS Robot Agent

Tiến trình Python trên **máy trạm cạnh robot** (không chạy trong BE). Điều khiển FAIRINO FR3 (hoặc mock / mô phỏng), đọc lực gripper, ghi nhật ký, đẩy tiến độ lên BE qua API `/technician/*` có sẵn,
và phục vụ **trình theo dõi từ xa** để Technical Staff xem và dừng job mà không đứng cạnh robot. Hướng dẫn đầy đủ: `../BE/docs/ROBOT_INTEGRATION.md`.

> Dừng bằng phần mềm không thay nút E-stop vật lý. Tác giả code chưa bao giờ chạy chế độ REAL; chỉ người vận hành chạy, tại chỗ.

## Môi trường mô phỏng 3D (PyBullet), không cần trình biên dịch C++

PyBullet không có gói dựng sẵn cho Python 3.11 trên Windows, nên dùng bản dựng sẵn của conda-forge qua micromamba (một file exe, không cần quyền admin):

```bash
python scripts/setup_sim_env.py       # tạo robot_agent/.simenv (Python 3.11 + PyBullet), tải mô hình FR3 và JavaScript của trình xem
.simenv/python.exe -m vhrs_agent.cli demo        # robot FR3 3D trong trình duyệt: http://127.0.0.1:8765/
.simenv/python.exe -m pytest -q                  # 73 test (14 test cần PyBullet)
```
Mô hình robot là URDF + STL **của hãng** (`FAIR-INNOVATION/frcobot_ros2`, repo không có file LICENSE nên chỉ dùng nội bộ, không commit): `vendor/fr3/`. Bản mô phỏng này chạy động học của hãng (cánh tay có khớp, giới hạn khớp, nhánh nghiệm, điểm kỳ dị, va chạm bàn), **không phải controller thật**.

## Chạy đúng kiến trúc: gọi RA BE (khuyến nghị, đường chính)

Máy trạm không cần mở cổng nào. **Cách chính: đăng nhập technical staff** (`VHRS_TECH_EMAIL`, `VHRS_TECH_PASSWORD`; thêm `"robot_id"` vào `agent.json` nếu phụ trách nhiều robot): agent tự xin khoá phiên ~4 giờ, tự gia hạn êm, bị từ chối `ROBOT_IN_USE` nếu robot đang do app khác điều khiển, và trả khoá khi thoát. Cách phụ: Manager cấp khoá cố định (`POST /manager/robots/{id}/agent-key`, hiện một lần) rồi đặt `VHRS_AGENT_KEY`. `agent.json` cần `backend_url`, `modes`, `run_dir` (và `"lan_server": false` nếu không muốn trang LAN); khoá đặt bằng biến môi trường, không ghi vào file:
```powershell
$env:VHRS_AGENT_KEY = "vhrs_ak_..."
.simenv\python.exe -m vhrs_agent.cli serve --config agent.json      # in "Backend link ON"
```
Từ đó app kỹ thuật viên điều khiển qua BE: `POST /technician/robot-commands` (LOAD, PREFLIGHT, DRY_RUN, RUN, PAUSE, RESUME, STOP, PAPER_CHANGED, IDENTIFY), xem sống ở `GET /technician/robots/{id}/live` và trang 3D `/viewer/robot.html`. Mất kết nối BE khi đang viết: viết nốt nét, nhấc bút, tạm dừng, cảnh báo cam, **không tự tiếp tục** (`link_loss_grace_s`, mặc định 6 giây). Cổng chạy THẬT tại chỗ (`real-enable`) giữ nguyên. Quy trình đầy đủ và các lệnh test: `BE/docs/ROBOT_REAL_TEST_RUNBOOK.md`; API: `BE/docs/FE_API_GUIDE.md` mục 7g. Lệnh hết hạn không bao giờ chạy trễ.

## Chạy như dịch vụ trên mạng nội bộ (đường phụ, để gỡ lỗi tại máy trạm) (người khác dùng bằng trình duyệt, không cần chạy code)

```bash
copy agent.example.json agent.json          # sửa backend_url, modes, ...
.simenv\python.exe -m vhrs_agent.cli serve --config agent.json     # mặc định nghe 0.0.0.0:8765
```
Mở `http://<IP máy trạm>:8765/`: đăng nhập bằng **tài khoản hệ thống** (Technical Staff điều khiển; Manager xem và dừng), chọn job, bấm **Tải job → Kiểm tra trước → Chạy thử pen-up → Chạy viết**, xem robot 3D, cảnh báo, nút Tạm dừng/Tiếp tục/DỪNG. Mọi nút là một lệnh gọi API (xem `BE/docs/FE_API_GUIDE.md` mục 7g), nên FE hoặc công cụ khác dùng được y như vậy.
- **Mở cổng cho máy khác trong LAN** (PowerShell, quyền admin, một lần): `New-NetFirewallRule -DisplayName "VHRS Robot Agent" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private`. Không mở ra Internet.
- **HTTPS**: đặt `tls_certfile`/`tls_keyfile` (hoặc đặt sau Caddy/nginx). Không có TLS thì mật khẩu đăng nhập đi trong mạng LAN dạng chữ thường: chỉ dùng trong mạng tin cậy.
- **Tự khởi động**: Task Scheduler "At startup" chạy lệnh `serve` ở thư mục `robot_agent` (hoặc NSSM làm dịch vụ Windows). Máy trạm cần tới được `backend_url` (Render) để đăng nhập và tải job.
- **Chỉ mô phỏng** (không nối robot): chạy ở bất kỳ máy nào với `modes: ["mock","sim"]`; nhiều người cùng xem một bản 3D.
- **Chạy robot THẬT qua API cần cả ba**: (1) `"real"` nằm trong `modes` của máy trạm nối robot; (2) **người ở máy trạm** chạy `.simenv\python.exe -m vhrs_agent.cli real-enable --config agent.json --job N --minutes 30` (gõ YES; file hết hạn, chỉ cho đúng job đó); (3) người gọi gửi mã xác nhận gắn với kế hoạch và job đã qua chạy thử pen-up. Một lệnh từ xa không thể tự bật robot thật.

## Chạy thử không cần robot

```bash
cd robot_agent
../BE/.venv/Scripts/python.exe -m vhrs_agent.cli demo          # mở http://127.0.0.1:8765/ để xem bút viết
../BE/.venv/Scripts/python.exe -m pytest -q                     # 59 test
../BE/.venv/Scripts/python.exe -m vhrs_agent.cli demo --scenario overforce   # diễn tập cảnh báo cam (bút ép quá mạnh)
../BE/.venv/Scripts/python.exe -m vhrs_agent.cli demo --scenario runaway     # diễn tập cảnh báo ĐỎ (robot giả lờ lệnh dừng)
```
`demo` viết "Xin chào Việt Nam" trên robot **mô phỏng** (chạy khô pen-up trước, rồi viết), số liệu hiệu chuẩn trong demo là dữ liệu thử, không phải số đo thật.

## Cài SDK Fairino (chỉ cần cho REAL)

```bash
python scripts/fetch_fairino_sdk.py      # tải commit 55bcce6 của SDK chính thức vào vendor/ (git-ignored)
```
Robot của xưởng: FR3 V6.0, controller V3.8.25-QX. Tương thích với SDK ghim **chưa xác minh**: chạy `connect()` chỉ-đọc và kiểm tra phiên bản trước tiên.

## Lệnh

| Lệnh | Việc |
|---|---|
| `cli demo` | mô phỏng + trình theo dõi |
| `cli run --backend URL --job N --mode mock\|sim [--dry-run] [--resume-from K] [--confirm-unknown]` | chạy job từ BE (cần `VHRS_TOKEN` trong môi trường). `--mode real` chưa được nối vào CLI: dành cho phiên có người vận hành, xem hướng dẫn mục 8 |
| `cli authorize --job N --config file.json` | in mã xác nhận REAL cho đúng job + kế hoạch |

Trình theo dõi chỉ nghe `127.0.0.1`; muốn xem từ máy khác phải đặt `--host` **và** `--token` (nút điều khiển cần header `X-Viewer-Token`).

## Cấu trúc

`kinematics.py` (động học FR3 từ URDF của hãng bằng PyBullet) + `sim_pybullet.py` (robot SIM có khớp, cung cấp góc khớp cho bản 3D), `port.py` (giao diện), `sim.py` (MOCK/SIM), `fairino_robot.py` (REAL, READY_FOR_HARDWARE_VALIDATION), `gripper.py` (giao thức + an toàn), `runner.py` (preflight, chạy khô, viết, dừng, khôi phục),
`ops.py` (báo lần chạy, cảnh báo, heartbeat lên BE; câu chữ dự phòng khi mất mạng), `bridge.py` (API BE), `viewer.py` + `static/` (theo dõi), `cli.py`.
