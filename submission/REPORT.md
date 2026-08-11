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

- Challenge ID: `day13-k4-observability-v1` (`incident=rag_slow`, `affected_feature=monitoring`)
- Triệu chứng từ metrics: baseline p95 = 150ms; khi bật incident p95/p99 = 2651ms, vượt ngưỡng challenge 2000ms. Error rate vẫn 0%, cost và quality không tăng bất thường, nên đây là latency-only incident.
- Trace ID liên quan: Không có Langfuse cloud trong môi trường local (`tracing_enabled=false`), dùng local trace fallback theo correlation ID `req-d2627011`. Evidence: `submission/evidence/cp3_trace_waterfall.png`.
- Log line/correlation ID liên quan: `req-d2627011`; log cùng request có `request_received` -> `rag_retrieval_slow` (`service=rag`, `tool_name=mock_rag.retrieve`, `latency_ms=2500`, `payload.incident=rag_slow`) -> `response_sent` (`latency_ms=2651`). Evidence: `submission/evidence/cp3_root_cause_log_screenshot.png`.
- Root cause: Incident `rag_slow` làm bước RAG retrieval trong `mock_rag.retrieve` bị delay 2.5s cho các request feature `monitoring`, kéo toàn bộ `/chat` lên khoảng 2.65s/request.
- Fix action: Tắt incident/rollback thay đổi gây chậm RAG; trong production sẽ đặt timeout + fallback cache cho retrieval, kiểm tra vector store/index, và giảm dependency blocking trong request path.
- Preventive measure: Alert p95 latency theo feature, trace span riêng cho `retrieve`/`generate`, log structured cho tool latency, canary trước khi bật thay đổi RAG, và SLO guard để tự động rollback khi p95 vượt ngưỡng.

CP3 phản biện:

Bằng chứng root cause chắc chắn là chuỗi Metrics -> Trace -> Logs cùng một request. Metrics chỉ ra chỉ latency tăng (p95 150ms -> 2651ms, error 0%). Local trace waterfall cho thấy phần lớn thời gian nằm ở `mock_rag.retrieve` 2500ms, không phải LLM generation. Log thô cùng `correlation_id=req-d2627011` ghi rõ event `rag_retrieval_slow` với `payload.incident=rag_slow`, rồi `response_sent.latency_ms=2651`.

Nếu hệ thống chỉ có metrics mà không có log chi tiết, nhóm chỉ biết "latency tăng" nhưng không chứng minh được request nào, feature nào, span nào, hay dependency nào gây ra. Việc điều tra sẽ phải đoán giữa RAG, LLM, network, concurrency hoặc dữ liệu đầu vào, làm MTTR tăng và dễ fix sai chỗ.

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Nguyễn Thế Khiêm | Checkpoint 1 — correlation ID, log enrichment, PII redaction, error rate | 6b333de | Redact PII phải đặt trước bước ghi file, và regex quá tham sẽ che nhầm trace ID — cần neo bằng từ khóa. |
