# Báo cáo Day 13 — Observability cho hệ thống AI

## 1. Thông tin nhóm

| Trường | Nội dung |
|---|---|
| **Tên nhóm** | AETAODONG |
| **Repository URL** | https://github.com/cuongquangnam/K4-DAY13-2A202601584 |
| **Commit SHA cuối** | 6b333de |
| **Thành viên và vai trò** | Xem bảng bên dưới |

| Thành viên | Vai trò |
|---|---|
| Trương Công Cường | Tracing & Prompt Version |
| Phạm Thanh Hưng | Dashboard, SLO & Alert |
| Nguyễn Thế Khiêm | Logging & PII |
| Đỗ Đức Tiến | Incident, Report & Demo |

---

## 2. Kết quả kỹ thuật tổng quát

| Hạng mục | Kết quả |
|---|---|
| Điểm `validate_logs.py` | **100/100** — xem [cp1_validator_output.txt](evidence/cp1_validator_output.txt) & [cp1_validator_screenshot.png](evidence/cp1_validator_screenshot.png) |
| Tổng số log records phân tích | 22 records |
| Records thiếu trường bắt buộc | 0 |
| Records thiếu enrichment | 0 |
| Unique correlation IDs | 10 |
| PII leaks còn lại | **0** |
| Dashboard contract | **HỢP LỆ: 6/6 panel** |
| Challenge ID | `day13-k4-observability-v1` |
| Incident điều tra | `rag_slow` — feature `monitoring` |

---

## 3. Logging và PII redaction

### 3.1 Kiến trúc logging

Hệ thống sử dụng **structlog** với pipeline xử lý theo thứ tự (`app/logging_config.py`):

1. `merge_contextvars` — ghép context từ middleware (correlation_id, user_id_hash, session_id, feature, model, env)
2. `add_log_level` — gắn level
3. `TimeStamper(fmt="iso", utc=True, key="ts")` — timestamp ISO 8601 UTC
4. `scrub_event` — **quét và che PII trên toàn bộ event dict** (đệ quy vào nested dict/list)
5. `StackInfoRenderer`, `format_exc_info`
6. `JsonlFileProcessor` — ghi vào `data/logs.jsonl`
7. `JSONRenderer` — render ra stdout

### 3.2 Correlation ID

`CorrelationIdMiddleware` (`app/middleware.py`) chạy ở đầu mỗi request:
- `clear_contextvars()` — **bắt buộc** để tránh kế thừa context của request trước trong cùng worker
- Lấy `x-request-id` từ header client hoặc tự sinh `req-<8hex>` bằng UUID4
- `bind_contextvars(correlation_id=...)` — ID tự động xuất hiện trong **mọi** log line của request
- Gán vào `request.state.correlation_id` để trả lại qua `ChatResponse.correlation_id`

> **Lưu ý**: Header `x-request-id` và `x-response-time-ms` trong response chưa được bổ sung (còn là `TODO` trong middleware — dòng 25-27). Đây là điểm có thể cải thiện.

**Evidence**: [cp1-validate-logs.png](evidence/cp1-validate-logs.png) — 10 request → 10 correlation ID duy nhất dạng `req-<8hex>`.

### 3.3 PII redaction

Module `app/pii.py` định nghĩa 7 pattern regex cho PII Việt Nam:

| Pattern | Mô tả |
|---|---|
| `email` | Địa chỉ email |
| `phone_vn` | SĐT Việt Nam (+84 hoặc 0x, nhiều format) |
| `credit_card` | Số thẻ 16 chữ số |
| `cccd` | CCCD 12 chữ số |
| `passport_vn` | Hộ chiếu Việt Nam (neo bằng keyword) |
| `address_vn` | Địa chỉ (neo bằng keyword: số nhà, đường, phường...) |
| `bank_account_vn` | Số tài khoản ngân hàng (neo bằng keyword) |

**Hàm chính**:
- `scrub_text(text)` — thay thế bằng `[REDACTED_<TYPE>]`
- `summarize_text(text, max_len=80)` — scrub rồi cắt ngắn, dùng trong payload log
- `hash_user_id(user_id)` — SHA-256, lấy 12 ký tự đầu → không bao giờ log raw user ID

**Tích hợp trong logging**: `scrub_event` áp dụng đệ quy qua toàn bộ event dict (kể cả nested dict, list), đảm bảo PII không lọt qua bất kỳ trường nào trước khi ghi file.

**Evidence**:
- [cp1-pii-redaction.png](evidence/cp1-pii-redaction.png) — log hiển thị `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`
- [cp1_manual_pii_checks.txt](evidence/cp1_manual_pii_checks.txt) — kiểm tra `Select-String` xác nhận không có `@`, `4111` trong logs
- [cp1_redacted_log_excerpt.jsonl](evidence/cp1_redacted_log_excerpt.jsonl) — mẫu log đã được scrub

### 3.4 Log enrichment

Mỗi request API gắn vào structlog context (`bind_contextvars` trong `main.py`):
`user_id_hash`, `session_id`, `feature`, `model`, `env` — xuất hiện trong **tất cả** log line của request nhờ `merge_contextvars`.

---

## 4. Prompt versioning

### 4.1 Cơ chế

Module `app/prompt_management.py` — hàm `resolve_prompt()`:

1. Khi `tracing_enabled=True`: gọi Langfuse `client.get_prompt(name, label=label, ...)` với cache 60s, timeout 2s, max_retries=0 — fail fast với fallback local
2. Khi `tracing_enabled=False`: dùng `DEFAULT_PROMPT_TEMPLATE` local

**Metadata được gắn vào trace** (cả `update_current_trace` lẫn `update_current_generation` trong `app/agent.py`):
```
prompt_name, prompt_label, prompt_version, prompt_source, prompt_fetch_error
```

### 4.2 Hai phiên bản prompt

| | v1 (baseline) | v2 (candidate) |
|---|---|---|
| **Prompt name** | `day13-chat` | `day13-chat` |
| **Label** | `production` | `candidate` |
| **Source** | `local` (hoặc `langfuse` nếu có key) | `langfuse` |

> **Lưu ý**: Môi trường lab chạy `tracing_enabled=false` (không có Langfuse cloud key), nên `prompt_source="local"` và `prompt_version="local-v1"`. Bằng chứng trace Langfuse cloud với `prompt_version` số nguyên từ managed prompt chưa được thu thập — đây là phần còn thiếu của checkpoint 2.

### 4.3 Trace metadata mẫu

Trong `app/agent.py`, mỗi trace được update với:
- `user_id` = SHA-256 hash 12 ký tự
- `session_id`, `tags=["lab", feature, model]`
- metadata: `correlation_id`, `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source`
- generation: `model`, `usage_details`, `cost_details`, `doc_count`, `query_preview`

---

## 5. Dashboard, SLO và Alert

### 5.1 Dashboard contract — HỢP LỆ: 6/6 panel

File: `config/dashboard.yaml` — nguồn dữ liệu `data/logs.jsonl`, time range 60 phút, refresh 30s

| Panel ID | Tiêu đề | Metrics | Ngưỡng |
|---|---|---|---|
| `latency` | Latency percentiles | p50, p95, p99 (ms) | p95 ≤ 3000ms |
| `traffic` | Request traffic | count, rate/min | rate ≥ 1 req/min |
| `errors` | Error rate & breakdown | error_rate_pct, count_by_value | error_rate ≤ 2% |
| `cost` | Cost over time | sum/min, total (USD) | total ≤ $2.5 |
| `tokens` | Input/output tokens | sum tokens_in, tokens_out | sum ≤ 50,000 |
| `quality` | Quality proxy | mean quality_score [0–1] | mean ≥ 0.75 |

Dashboard HTML render: [evidence/dashboard.html](evidence/dashboard.html)

### 5.2 SLO — cửa sổ 28 ngày (`config/slo.yaml`)

| SLI | Objective | Target |
|---|---|---|
| `latency_p95_ms` | P95 < 3000ms | 99.5% cửa sổ |
| `error_rate_pct` | Error rate < 2% | 99.0% cửa sổ |
| `daily_cost_usd` | Tổng cost < $2.5/ngày | 100% |
| `quality_score_avg` | Quality mean ≥ 0.75 | 95% cửa sổ |

### 5.3 Alert rules (`config/alert_rules.yaml`)

| Alert | Severity | Điều kiện | Runbook |
|---|---|---|---|
| `high_latency_p95` | warning | p95 > 3000ms trong 5 phút | `docs/alerts.md#alert-1` |
| `elevated_error_rate` | critical | error_rate > 5% trong 3 phút | `docs/alerts.md#alert-2` |
| `cost_budget_exceeded` | warning | daily_cost > $2.5 | `docs/alerts.md#alert-3` |

---

## 6. Điều tra challenge chính thức

### 6.1 Thông tin

| Trường | Giá trị |
|---|---|
| Challenge ID | `day13-k4-observability-v1` |
| Incident | `rag_slow` |
| Affected feature | `monitoring` |
| Latency threshold | 2000ms |

### 6.2 Bước 1 — Triệu chứng từ Metrics

Evidence: [cp3_metrics.json](evidence/cp3_metrics.json)

| Metric | Baseline | Incident | Nhận xét |
|---|---|---|---|
| `latency_p50` | 150ms | **2651ms** | Tăng ~17.7× |
| `latency_p95` | 150ms | **2651ms** | Vượt ngưỡng 2000ms |
| `error_rate_pct` | 0.0% | 0.0% | Không có lỗi |
| `avg_cost_usd` | $0.0018 | $0.0017 | Không đổi |
| `quality_avg` | 0.84 | 0.84 | Không đổi |

**Kết luận**: Đây là **latency-only incident** — chỉ latency tăng đột biến, error rate/cost/quality bình thường. Cần đào sâu vào trace/log.

### 6.3 Bước 2 — Trace waterfall

Evidence: [cp3_trace_waterfall.txt](evidence/cp3_trace_waterfall.txt) & [cp3_trace_waterfall.png](evidence/cp3_trace_waterfall.png)

```
agent.run /chat                         ~2650 ms
  mock_rag.retrieve rag_retrieval_slow   2500 ms   ← dominant span / root cause
  FakeLLM.generate                        ~150 ms
```

Span `mock_rag.retrieve` chiếm **2500ms / 2650ms ≈ 94.3%** tổng thời gian. Root cause **không phải LLM** — là **RAG retrieval**.

### 6.4 Bước 3 — Log thô chứng minh root cause

Evidence: [cp3_root_cause_log.json](evidence/cp3_root_cause_log.json) — 3 log lines cùng `correlation_id=req-d2627011`:

```
[request_received]    ts=09:44:40.514  feature=monitoring
[rag_retrieval_slow]  ts=09:44:40.515  service=rag  tool_name=mock_rag.retrieve
                                       latency_ms=2500  payload.incident=rag_slow
[response_sent]       ts=09:44:43.167  latency_ms=2651  quality_score=0.9
```

Tất cả 5 challenge requests đều có `body_latency_ms=2651ms` (evidence: [cp3_challenge_run_output.txt](evidence/cp3_challenge_run_output.txt)).

### 6.5 Root cause

> **Incident `rag_slow` làm `mock_rag.retrieve` sleep 2.5 giây cho mọi request feature `monitoring`.** Toàn bộ `/chat` phải chờ retrieval, đẩy p50/p95/p99 lên 2651ms — vượt ngưỡng challenge 2000ms.

```python
# app/mock_rag.py
if STATE["rag_slow"]:
    log.warning("rag_retrieval_slow", ...)
    time.sleep(2.5)  # ← blocking sleep gây latency spike
```

### 6.6 Fix action và Preventive measure

**Fix ngay**: Tắt incident `POST /incidents/rag_slow/disable`; trong production: rollback thay đổi RAG, kiểm tra index/connection pool.

**Phòng ngừa**:
- Đặt **timeout** cho RAG retrieval (ví dụ 500ms) + fallback cache/local corpus
- Tạo **span riêng** cho `retrieve()` và `generate()` để nhanh khoanh vùng
- Alert theo **feature**: `high_latency_p95_monitoring` riêng, không chỉ alert toàn service
- **Canary deploy** khi thay đổi cấu hình RAG hoặc vector index
- **SLO guard tự động**: khi p95 vượt ngưỡng → trigger rollback pipeline

---

## 7. Phân tích kiến trúc code

### 7.1 Tổng quan module

| Module | Chức năng |
|---|---|
| `app/main.py` | FastAPI app, endpoints `/health`, `/metrics`, `/chat`, `/incidents/*` |
| `app/agent.py` | `LabAgent` — orchestrate RAG + LLM, cập nhật trace, ghi metrics |
| `app/middleware.py` | `CorrelationIdMiddleware` — sinh/truyền correlation ID |
| `app/logging_config.py` | structlog pipeline, PII scrubbing, ghi JSONL |
| `app/pii.py` | 7 regex pattern PII Việt Nam, scrub/hash/summarize |
| `app/metrics.py` | In-memory metrics: latency, cost, tokens, errors, quality |
| `app/tracing.py` | Wrapper Langfuse — graceful fallback khi không có SDK/key |
| `app/prompt_management.py` | Resolve prompt từ Langfuse hoặc local với fallback |
| `app/schemas.py` | Pydantic schemas: ChatRequest, ChatResponse, LogRecord |
| `app/mock_llm.py` | FakeLLM — simulate generation với token counting |
| `app/mock_rag.py` | Mock retrieval với corpus và incident simulation |
| `app/incidents.py` | Global STATE dict cho 3 incident types |
| `app/challenge.py` | Load & validate `challenge.json`, ordered queries |

### 7.2 Luồng request

```
Client
  → CorrelationIdMiddleware (sinh correlation_id, bind contextvars)
  → /chat endpoint (bind enrichment: user_id_hash, session_id, feature, model, env)
  → agent.run() [@observe tracing]
      → mock_rag.retrieve() (có thể bị rag_slow / tool_fail)
      → resolve_prompt() (Langfuse hoặc local fallback)
      → FakeLLM.generate() (có thể bị cost_spike)
      → _heuristic_quality()
      → langfuse_client.update_current_trace/generation()
      → metrics.record_request()
  ← ChatResponse (correlation_id, latency_ms, tokens, cost, quality)
```

### 7.3 Điểm mạnh

1. **PII scrubbing đệ quy** — `_scrub_value` xử lý nested dict/list, tránh bỏ sót PII trong payload lồng nhau
2. **Graceful degradation** — `tracing.py` và `prompt_management.py` đều có fallback khi Langfuse không khả dụng
3. **Quality heuristic** — `_heuristic_quality()` cho điểm dựa trên docs, độ dài answer, keyword overlap và redaction penalty
4. **In-memory metrics** — `percentile()` tự implement, snapshot đầy đủ p50/p95/p99/error_rate/cost/tokens/quality
5. **Challenge config validation** — `load_challenge()` validate chặt chẽ cohort, incident name, seed type, query fields

### 7.4 Điểm còn thiếu / TODO

| Vấn đề | File | Dòng |
|---|---|---|
| Header `x-request-id` và `x-response-time-ms` chưa set trong response | `app/middleware.py` | 25-27 |
| Prompt versioning Langfuse cloud chưa có evidence trace thật | — | — |
| Evidence dashboard screenshot runtime chưa có | `submission/evidence/` | — |
| Đóng góp cá nhân cần bổ sung commit SHA cho 3 thành viên còn lại | `submission/REPORT.md` | §8 |

---

## 8. Test coverage

| Test file | Nội dung kiểm thử |
|---|---|
| `tests/test_pii.py` | `scrub_text` — email, 5 format SĐT VN |
| `tests/test_prompt_management.py` | Local fallback, Langfuse resolve, timeout fallback, SDK fallback |
| `tests/test_challenge_config.py` | Missing file, valid config, unknown incident, practice vs official, seed ordering |
| `tests/test_agent_prompt_trace.py` | Agent trace metadata |
| `tests/test_chat_observability.py` | Chat observability |
| `tests/test_dashboard_validator.py` | Dashboard YAML validation |
| `tests/test_metrics.py` | Metrics recording |
| `tests/test_tracing_adapter.py` | Tracing adapter |
| `tests/test_validate_logs.py` | Log validation |
| `tests/test_cli_windows_encoding.py` | Windows UTF-8 encoding |

---

## 9. Đóng góp cá nhân

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Nguyễn Thế Khiêm | Checkpoint 1 — correlation ID, log enrichment, PII redaction, error rate | `6b333de` | Redact PII phải đặt trước bước ghi file; regex quá tham sẽ che nhầm trace ID — cần neo bằng từ khóa |
| Trương Công Cường | Checkpoint 2 — tracing, prompt versioning, Langfuse integration, `@observe` decorator | _(cần bổ sung commit SHA)_ | `@observe` chỉ hoạt động khi Langfuse SDK khả dụng; fallback dummy client cần implement đủ method |
| Phạm Thanh Hưng | Checkpoint 2 — dashboard contract YAML, SLO, alert rules, validate_dashboard script | _(cần bổ sung commit SHA)_ | Dashboard contract phải khớp đúng panel ID, aggregation và operator — validator kiểm tra từng trường |
| Đỗ Đức Tiến | Checkpoint 3 — chạy challenge, điều tra incident, root cause analysis, báo cáo | _(cần bổ sung commit SHA)_ | Luồng Metrics → Trace → Logs giúp thu hẹp hypothesis từ "latency tăng" → "RAG span" → "rag_slow incident" trong dưới 5 phút |

---

## 10. Evidence checklist

| Hạng mục | File | Trạng thái |
|---|---|---|
| Validate logs 100/100 | [cp1_validator_output.txt](evidence/cp1_validator_output.txt) | ✅ |
| Validate logs screenshot | [cp1_validator_screenshot.png](evidence/cp1_validator_screenshot.png) | ✅ |
| PII redaction screenshot | [cp1-pii-redaction.png](evidence/cp1-pii-redaction.png) | ✅ |
| PII redacted log excerpt | [cp1_redacted_log_excerpt.jsonl](evidence/cp1_redacted_log_excerpt.jsonl) | ✅ |
| Manual PII grep checks | [cp1_manual_pii_checks.txt](evidence/cp1_manual_pii_checks.txt) | ✅ |
| Challenge run output | [cp3_challenge_run_output.txt](evidence/cp3_challenge_run_output.txt) | ✅ |
| Challenge metrics JSON | [cp3_metrics.json](evidence/cp3_metrics.json) | ✅ |
| Metrics screenshot | [cp3_metrics_screenshot.png](evidence/cp3_metrics_screenshot.png) | ✅ |
| Root cause log JSON | [cp3_root_cause_log.json](evidence/cp3_root_cause_log.json) | ✅ |
| Root cause log screenshot | [cp3_root_cause_log_screenshot.png](evidence/cp3_root_cause_log_screenshot.png) | ✅ |
| Trace waterfall text | [cp3_trace_waterfall.txt](evidence/cp3_trace_waterfall.txt) | ✅ |
| Trace waterfall screenshot | [cp3_trace_waterfall.png](evidence/cp3_trace_waterfall.png) | ✅ |
| Dashboard HTML | [dashboard.html](evidence/dashboard.html) | ✅ |
| Prompt v1/v2 trace evidence | _(Langfuse cloud trace)_ | ⚠️ Cần bổ sung |
| Dashboard runtime screenshot | _(ảnh dashboard live)_ | ⚠️ Cần bổ sung |
