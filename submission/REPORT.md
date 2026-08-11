# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: Baseline CP0 = 100/100; CP1 = 100/100 (22 log records, 0 missing required fields, 0 missing enrichment, 10 unique correlation IDs, 0 PII leaks)
- Tổng số traces:
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard:

## 3. Logging và tracing

- Evidence correlation ID: `submission/evidence/cp1_redacted_log_excerpt.jsonl`, `submission/evidence/cp1_redacted_log_screenshot.png`
- Evidence PII redaction: `submission/evidence/cp1_redacted_log_excerpt.jsonl`, `submission/evidence/cp1_redacted_log_screenshot.png`, `submission/evidence/cp1_manual_pii_checks.txt`
- Evidence trace waterfall:
- Giải thích một span đáng chú ý:

CP1 phản biện:

Log baseline ở CP0 chủ yếu chứng minh file `data/logs.jsonl` có JSON hợp lệ và có thể chấm được. Sau CP1, log được sinh từ request thật, mỗi request có `correlation_id` dạng `req-<8hex>`, có metadata phục vụ lọc/phân tích (`user_id_hash`, `session_id`, `feature`, `model`, `env`) và PII trong payload được che trước khi ghi file.

`clear_contextvars()` ở đầu middleware là bắt buộc vì structlog contextvars có thể được tái sử dụng trong cùng worker/task. Nếu không xóa context cũ, request sau có thể kế thừa `correlation_id` hoặc metadata của request trước, làm sai trace/log correlation và gây rò rỉ dữ liệu giữa người dùng.

## 4. Prompt versioning

- Prompt name:
- Version/label baseline:
- Version/label candidate:
- Trace ID của mỗi version:
- Bằng chứng đổi label hoặc rollback:

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`:
- Evidence dashboard:
- SLO đã chọn và lý do:
- Alert rules và runbook:

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| | | | |
