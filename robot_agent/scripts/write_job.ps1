# One command for the whole writing sequence, stopping at the first step that fails. Every step that moves the REAL robot still asks you to type YES.
#
#   powershell -ExecutionPolicy Bypass -File scripts\write_job.ps1                 # from robot_agent: new sheet, write from the first stroke
#   powershell -ExecutionPolicy Bypass -File scripts\write_job.ps1 -KeepProgress   # same sheet: skip reset-progress (use `run --resume-from` by hand)
#   powershell -ExecutionPolicy Bypass -File scripts\write_job.ps1 -DryRunFirst    # also do the pen-up rehearsal first (needed after agent.json changed)
#   powershell -ExecutionPolicy Bypass -File scripts\write_job.ps1 -SkipDryRun      # waive the REAL pen-up rehearsal for this job (extra typed confirmation): the pen touches the paper at once
#
# The job, e-mail and mode come from console.json. Nothing here bypasses a safety gate: it only runs the same commands, in order.
param([switch]$KeepProgress, [switch]$DryRunFirst, [switch]$SkipDryRun, [int]$Minutes = 40)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".simenv\python.exe"
$job = (Get-Content (Join-Path $root "console.json") -Raw | ConvertFrom-Json).job_id
$con = @("-X", "utf8", "scripts\robot_console.py")

function Step([string]$title, [scriptblock]$cmd) {
    Write-Host ""
    Write-Host "=== $title" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "DỪNG: bước '$title' không thành công. Không chạy các bước sau. Gửi kết quả ở trên cho người hỗ trợ." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Job $job. E-Stop trong tầm tay, vùng robot trống, tờ giấy đúng vị trí và kẹp chặt." -ForegroundColor Yellow
if ($SkipDryRun) {
    Step "1. Cho phép robot thật chạy $Minutes phút cho job $job, BỎ QUA chạy thử (gõ YES rồi SKIP-DRY-RUN)" { & $py -X utf8 -m vhrs_agent.cli real-enable --config agent.json --job $job --minutes $Minutes --waive-dry-run }
} else {
    Step "1. Cho phép robot thật chạy $Minutes phút cho job $job (gõ YES)" { & $py -X utf8 -m vhrs_agent.cli real-enable --config agent.json --job $job --minutes $Minutes }
}
if (-not $KeepProgress) {
    Step "2. Đặt tiến độ về nét đầu (chỉ khi tờ giấy là tờ MỚI; gõ YES)" { & $py @con reset-progress }
}
Step "3. Nạp job và kiểm tra quỹ đạo" { & $py @con load --mode REAL }
Step "4. Đưa bút về điểm bắt đầu (robot di chuyển; gõ YES)" { & $py @con align-start --mode REAL }
Step "5. Kiểm tra trước khi chạy (robot không động)" { & $py @con preflight --mode REAL }
if ($DryRunFirst) {
    Step "5b. Chạy thử pen-up bằng robot thật (robot di chuyển, bút nhấc; gõ YES)" { & $py @con dry-run --mode REAL }
    Write-Host "Đợi robot dừng hẳn và 'status' báo DRY_RUN_DONE 45/45 rồi mới viết." -ForegroundColor Yellow
    & $py @con status
    $answer = Read-Host "Gõ VIET để tiếp tục sang viết thật, bất kỳ chữ khác để dừng"
    if ($answer -ne "VIET") { Write-Host "Đã dừng sau chạy thử."; exit 0 }
}
Step "5c. Đánh dấu job đang viết (WRITING)" { & $py @con start }
Step "6. VIẾT bằng robot thật (bút chạm giấy; gõ YES)" { & $py @con run --mode REAL }
Write-Host ""
Write-Host "Lệnh viết đã gửi. Trạng thái thật (đang chạy, xong hay lỗi):" -ForegroundColor Cyan
Start-Sleep -Seconds 5
& $py @con status
Write-Host "Theo dõi tiếp: .\.simenv\python.exe -X utf8 scripts\robot_console.py watch   |   khi xong: lại chạy 'status'." -ForegroundColor Cyan
