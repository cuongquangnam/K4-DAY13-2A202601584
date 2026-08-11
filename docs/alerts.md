# Alert Runbook — Day 13 Observability Lab

Mỗi alert dựa trên **triệu chứng user-facing / SLO**, không dựa tên implementation nội bộ
(ví dụ không alert theo `FakeLLM.generate` hay `STATE["rag_slow"]`).

Nguồn số liệu khi on-call:

```bash
curl -s http://localhost:8000/metrics | python -m json.tool
curl -s http://localhost:8000/health | python -m json.tool
# Logs: data/logs.jsonl
# Traces: Langfuse project → filter time range + tags lab
```

SLO reference: [`config/slo.yaml`](../config/slo.yaml) · Rules: [`config/alert_rules.yaml`](../config/alert_rules.yaml)

---

## Alert 1 {#alert-1}

| Mục | Chi tiết |
|---|---|
| **Tên** | `high_latency_p95` |
| **Severity** | warning |
| **SLI / SLO** | `latency_p95_ms` — objective **3000 ms**, target **99.5%** |
| **Điều kiện kích hoạt** | `latency_p95 > 3000ms` duy trì **≥ 5 phút** |
| **Ảnh hưởng tới người dùng** | Người dùng `/chat` thấy câu trả lời chậm, timeout cảm nhận (UX kém); queue backlog nếu traffic lab cao |
| **Owner** | on-call-engineer |

### Ba bước kiểm tra đầu tiên

1. **Metrics / Dashboard**  
   Mở panel **Latency percentiles** (60m). Xác nhận P95/P99 đang vượt 3000ms hay chỉ spike ngắn. So sánh với panel **Traffic** — latency tăng khi traffic ổn → nghi degradation nội bộ, không phải load.

2. **Traces (Langfuse)**  
   Lọc 5–10 phút gần nhất, tag `lab`, sắp xếp theo latency. Mở waterfall:  
   - `retrieve-context` dài → RAG/path chậm  
   - `generate-response` dài → model/gen path chậm  
   Ghi lại `trace_id` và metadata `prompt_version` / `correlation_id`.

3. **Logs**  
   Trong `data/logs.jsonl`, tìm `response_sent` có `latency_ms` > 3000 và khớp `correlation_id` (hoặc `payload.langfuse_trace_id`). Kiểm tra có `incident_enabled` gần đó (practice) hoặc error xen kẽ không.

### Mitigation tạm thời

- Tắt incident practice nếu đang bật:  
  `python scripts/inject_incident.py --scenario rag_slow --disable` (hoặc scenario đang active).
- Giảm concurrency load test / giới hạn traffic tạm thời.
- Nếu nghi prompt candidate nặng: rollback label `production` về version baseline trên Langfuse (xem [PROMPT_VERSIONING.md](PROMPT_VERSIONING.md)).
- Ghi status cho team; escalate nếu P95 > 5s sau 10 phút.

---

## Alert 2 {#alert-2}

| Mục | Chi tiết |
|---|---|
| **Tên** | `elevated_error_rate` |
| **Severity** | critical |
| **SLI / SLO** | `error_rate_pct` — objective **≤ 2%**, target **99.0%** (alert fire khi **> 5%** trong 3 phút — ngưỡng alert chặt hơn objective để giảm noise) |
| **Điều kiện kích hoạt** | `error_rate_pct > 5` duy trì **≥ 3 phút** |
| **Ảnh hưởng tới người dùng** | Tỷ lệ cao request `/chat` thất bại (HTTP 500), không nhận answer; chức năng chính không dùng được |
| **Owner** | on-call-engineer |

### Ba bước kiểm tra đầu tiên

1. **Metrics / Dashboard**  
   Panel **Error rate and breakdown**: đọc `error_rate_pct`, `errors_total`, bảng `error_breakdown` (theo `error_type`). Xác nhận đây là fail thật, không phải noise một-off.

2. **Logs**  
   Lọc `event == "request_failed"` trong cửa sổ alert. Lấy 3–5 dòng gần nhất: `error_type`, `correlation_id`, `payload.detail`. Phân nhóm — cùng một exception hay nhiều loại.

3. **Traces**  
   Mở Langfuse cùng time range. Trace lỗi thường thiếu generation hoàn chỉnh hoặc span ERROR. Kiểm tra span nào throw (retriever vs generation). Khớp `correlation_id` ↔ log line.

### Mitigation tạm thời

- Nếu do practice incident `tool_fail`:  
  `python scripts/inject_incident.py --scenario tool_fail --disable`.
- Restart API process nếu state in-memory (incidents flag) kẹt sau crash:  
  `uvicorn app.main:app --reload --env-file .env`.
- Rollback deploy / prompt label nếu coinciding với change gần nhất.
- Announce critical: tạm dừng demo load test cho đến khi error rate < 2%.

---

## Alert 3 {#alert-3}

| Mục | Chi tiết |
|---|---|
| **Tên** | `cost_budget_exceeded` |
| **Severity** | warning |
| **SLI / SLO** | `daily_cost_usd` — objective **$2.5 / ngày**, target **100%** (budget hard cap lab) |
| **Điều kiện kích hoạt** | `daily_cost_usd > 2.5` (cum trong ngày theo log/metrics cost) |
| **Ảnh hưởng tới người dùng** | Không hỏng UX ngay, nhưng burn rate LLM vượt ngân sách lab/demo; có thể buộc throttle hoặc cắt traffic |
| **Owner** | team-lead |

### Ba bước kiểm tra đầu tiên

1. **Metrics / Dashboard**  
   Panel **Cost over time** + **Tokens**: so `total_cost_usd` / `avg_cost_usd` với path `tokens_out_total`. Cost tăng thường đi cùng output tokens tăng.

2. **Logs**  
   Aggregate `sum(cost_usd)` và `sum(tokens_out)` trong ngày từ `response_sent`. Tìm request outlier (cost_usd bất thường cao).

3. **Traces**  
   Langfuse: lọc cost/tokens cao; kiểm tra `prompt_source`, `prompt_version`, model tag. Xác nhận có practice `cost_spike` hay generation path phình output.

### Mitigation tạm thời

- Tắt incident:  
  `python scripts/inject_incident.py --scenario cost_spike --disable`.
- Giảm traffic / dừng load test không cần thiết.
- Rollback prompt version nếu version mới làm answer dài hơn rõ rệt.
- Team-lead duyệt: tạm nâng budget lab **hoặc** khóa feature non-critical cho hết ngày.

---

## Ma trận triệu chứng nhanh

| Quan sát dashboard | Alert khả dĩ | Ưu tiên mở |
|---|---|---|
| P95 > 3s, error thấp | `high_latency_p95` | Trace waterfall latency |
| Error % > 5 | `elevated_error_rate` | Logs `request_failed` |
| Cost / tokens spike | `cost_budget_exceeded` | Tokens panel + generation metadata |
| Quality < 0.75 | (chưa page — theo dõi panel quality) | So 2 prompt version traces |

Khi đóng alert: ghi lại metric trước/sau, trace ID, log correlation ID vào `submission/REPORT.md`.
