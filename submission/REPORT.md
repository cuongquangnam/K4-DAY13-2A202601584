# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: 100/100 — xem [cp1-validate-logs.png](evidence/cp1-validate-logs.png)
- Tổng số traces:
- Số PII leak còn lại: 0 (`Potential PII leaks detected: 0` trên 20 log record)
- Link/đường dẫn dashboard:

## 3. Logging và tracing

- Evidence correlation ID: [cp1-validate-logs.png](evidence/cp1-validate-logs.png) — 10 request sinh 10 correlation ID duy nhất (`req-<8 hex>`), validator báo `Unique correlation IDs found: 10`. ID được lấy từ header `x-request-id` nếu client gửi, nếu không thì middleware tự sinh; ID này được bind vào structlog contextvars nên xuất hiện trong mọi log record của request và được trả lại qua header `x-request-id`.
- Evidence PII redaction: [cp1-pii-redaction.png](evidence/cp1-pii-redaction.png) — email, số điện thoại VN và số thẻ trong `data/logs.jsonl` đều đã thành `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`. Ngoài ra `user_id` được hash bằng SHA-256 (12 ký tự) thay vì log nguyên văn.
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
| Nguyễn Thế Khiêm | Checkpoint 1 — correlation ID, log enrichment, PII redaction, error rate | 6b333de | Redact PII phải đặt trước bước ghi file, và regex quá tham sẽ che nhầm trace ID — cần neo bằng từ khóa. |
