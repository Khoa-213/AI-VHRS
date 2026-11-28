# Hướng dẫn cho AI làm việc trong `robot_agent/`

Thư mục này là Robot Agent chạy ở máy trạm nối robot FAIRINO FR3. Luật chung của dự án nằm ở `../BE/CLAUDE.md` và `../BE/AI_PLAYBOOK.md`; giao tiếp tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh.

**Khi đang ở máy trạm và một bước chạy robot bị từ chối hoặc lỗi: đọc `WORKSTATION_TROUBLESHOOTING.md` trước khi làm gì khác.** File đó có bảng mã lỗi, nguyên nhân, việc cần làm, và nơi lấy bằng chứng.

Luật không thương lượng:

- Không gửi lệnh làm robot **thật** chuyển động khi người vận hành đứng tại máy chưa cho phép rõ ràng trong chính cuộc trò chuyện đó.
- Không sửa ngưỡng an toàn (`station_limits`, `watchdogs`, `workspace`, `unsensed_gripper`, `waive_dry_run`) để một lỗi biến mất, và không tự nghĩ ra số đo.
- Không xoá hay sửa tay `runs/pending_closes.json`, `runs/job*/progress.json`, `runs/REAL_ENABLED.json`.
- Không in secret (`agent.json` có thể chứa `agent_key`; `../BE/.env` trỏ vào database thật).
- Không sửa code để vượt một cổng kiểm tra; nếu cổng sai thật thì ghi bằng chứng và báo chủ dự án.
- Không commit, không push khi chưa được yêu cầu; không thêm dòng ghi công AI.
