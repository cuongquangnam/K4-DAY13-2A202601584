# Dashboard Spec — Day 13 AI Observability

Contract máy kiểm tra: [`config/dashboard.yaml`](../config/dashboard.yaml).  
Hướng dẫn dựng runtime: [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).  
SLO liên quan: [`config/slo.yaml`](../config/slo.yaml).

## Tóm tắt

| Mục | Giá trị |
|---|---|
| Tên dashboard | Day 13 AI Observability |
| Công cụ | **Spec + Streamlit/notebook local** (nguồn chuẩn `data/logs.jsonl`); Langfuse dùng để drill-down trace, không thay 6 panel contract |
| Nguồn dữ liệu chính | `data/logs.jsonl` (event-level). `/metrics` là snapshot runtime hỗ trợ |
| Khoảng thời gian mặc định | **60 phút** |
| Auto-refresh | **30 giây** |
| Số panel chính | **6** (đúng contract) |

Baseline runtime quan sát gần nhất (gọi `GET /metrics`):

```json
{
  "traffic": 10,
  "errors_total": 0,
  "error_rate_pct": 0.0,
  "latency_p50": 1100.0,
  "latency_p95": 1478.0,
  "latency_p99": 1478.0,
  "avg_cost_usd": 0.0021,
  "total_cost_usd": 0.0208,
  "tokens_in_total": 330,
  "tokens_out_total": 1319,
  "error_breakdown": {},
  "quality_avg": 0.88
}
```

Cách xem lại:

```bash
curl -s http://localhost:8000/metrics | python -m json.tool
python scripts/validate_dashboard.py
```

---

## Panel 1 — Latency percentiles

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `latency` — **Latency percentiles** |
| **Nhóm chỉ số** | Latency |
| **Nguồn** | `data/logs.jsonl` → event `response_sent`, field `latency_ms` |
| **Mapping /metrics** | `latency_p50`, `latency_p95`, `latency_p99` |
| **Aggregations** | P50, P95, P99 |
| **Loại biểu đồ** | Line theo thời gian (hoặc 3 single-value P50/P95/P99) |
| **Đơn vị** | ms |
| **Time range mặc định** | Last 60 minutes |
| **Refresh** | 30s |
| **Threshold / SLO line** | **P95 ≤ 3000 ms** (SLO `latency_p95_ms`, target uptime 99.5%) |
| **Query (pseudocode)** | `event == "response_sent" \| percentile(latency_ms, [50, 95, 99])` |
| **Cách đọc** | P50 = trải nghiệm điển hình; P95/P99 = đuôi chậm. Vượt line 3000ms → mở Langfuse lọc tag + latency cao |

---

## Panel 2 — Request traffic

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `traffic` — **Request traffic** |
| **Nhóm chỉ số** | Traffic |
| **Nguồn** | `data/logs.jsonl` → event `request_received` |
| **Mapping /metrics** | `traffic` (tổng request thành công qua lifetime process) |
| **Aggregations** | `count`, `rate_per_minute` (QPS ≈ rate/60) |
| **Loại biểu đồ** | Counter tổng + line rate theo phút (requests/min) |
| **Đơn vị** | requests_per_minute |
| **Time range mặc định** | Last 60 minutes |
| **Refresh** | 30s |
| **Threshold** | **rate_per_minute ≥ 1** (cảnh báo dashboard “im lặng” / không có traffic lab) |
| **Query (pseudocode)** | `event == "request_received" \| count() by 1m` |
| **Cách đọc** | Traffic drop đột ngột + error tăng → nghi ngờ outage; traffic tăng mạnh + latency tăng → quá tải |

---

## Panel 3 — Error rate and breakdown

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `errors` — **Error rate and breakdown** |
| **Nhóm chỉ số** | Error |
| **Nguồn** | `data/logs.jsonl` → `request_received`, `request_failed`, field `error_type` |
| **Mapping /metrics** | `error_rate_pct`, `error_breakdown`, `errors_total` |
| **Aggregations** | `error_rate_pct`, `count_by_value` (theo `error_type`) |
| **Loại biểu đồ** | Gauge/line tỷ lệ lỗi (%) + table breakdown theo loại lỗi |
| **Đơn vị** | percent |
| **Time range mặc định** | Last 60 minutes |
| **Refresh** | 30s |
| **Threshold / SLO line** | **error_rate_pct ≤ 2%** (SLO `error_rate_pct`, target 99.0%) |
| **Query (pseudocode)** | `count(request_failed) / count(request_received) * 100; count_by(error_type)` |
| **Cách đọc** | Rate > 2% → bảng `error_type` → log `request_failed` theo `correlation_id` → trace Langfuse |

---

## Panel 4 — Cost over time

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `cost` — **Cost over time** |
| **Nhóm chỉ số** | Cost |
| **Nguồn** | `data/logs.jsonl` → event `response_sent`, field `cost_usd` |
| **Mapping /metrics** | `total_cost_usd`, `avg_cost_usd` |
| **Aggregations** | `sum_by_minute`, `total` |
| **Loại biểu đồ** | Area/line chi phí theo phút + single-value tổng cửa sổ |
| **Đơn vị** | usd |
| **Time range mặc định** | Last 60 minutes (budget chiếu theo ngày trong SLO) |
| **Refresh** | 30s |
| **Threshold / budget line** | **total ≤ $2.5** / cửa sổ ngày (SLO `daily_cost_usd`) |
| **Query (pseudocode)** | `event == "response_sent" \| sum(cost_usd) by 1m; sum(cost_usd)` |
| **Cách đọc** | Spike cost thường đi kèm token spike hoặc incident `cost_spike`; so sánh `tokens_out` panel 5 |

---

## Panel 5 — Input and output tokens

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `tokens` — **Input and output tokens** |
| **Nhóm chỉ số** | Tokens |
| **Nguồn** | `data/logs.jsonl` → `tokens_in`, `tokens_out` trên `response_sent` |
| **Mapping /metrics** | `tokens_in_total`, `tokens_out_total` |
| **Aggregations** | `sum_by_field` (tổng input, tổng output) |
| **Loại biểu đồ** | Stacked bar / dual series line (input vs output) |
| **Đơn vị** | tokens |
| **Time range mặc định** | Last 60 minutes |
| **Refresh** | 30s |
| **Threshold** | **sum_by_field ≤ 50_000** tokens trong cửa sổ (guardrail lab) |
| **Query (pseudocode)** | `event == "response_sent" \| sum(tokens_in), sum(tokens_out)` |
| **Cách đọc** | Output tăng bất thường → cost và latency có thể tăng theo; kiểm tra model/prompt version trên Langfuse |

---

## Panel 6 — Quality proxy

| Trường | Giá trị |
|---|---|
| **ID / tên panel** | `quality` — **Quality proxy** |
| **Nhóm chỉ số** | Quality |
| **Nguồn** | `data/logs.jsonl` → `quality_score` trên `response_sent` |
| **Mapping /metrics** | `quality_avg` |
| **Aggregations** | `mean` |
| **Loại biểu đồ** | Line mean theo thời gian + single-value hiện tại (0–1) |
| **Đơn vị** | score_0_to_1 |
| **Time range mặc định** | Last 60 minutes |
| **Refresh** | 30s |
| **Threshold / SLO line** | **mean ≥ 0.75** (SLO `quality_score_avg`, target 95.0%) |
| **Query (pseudocode)** | `event == "response_sent" \| mean(quality_score)` |
| **Cách đọc** | Score giảm sau đổi prompt/label → so sánh 2 trace `prompt_version` trên Langfuse; rollback label nếu cần |

---

## Bố cục đề xuất (1 màn hình chính)

```text
┌──────────────────────┬──────────────────────┐
│ 1. Latency P50/P95/P99│ 2. Traffic (req/min) │
│    SLO P95 = 3000ms  │                      │
├──────────────────────┼──────────────────────┤
│ 3. Error rate %      │ 4. Cost USD over time│
│    + breakdown table │    budget $2.5       │
├──────────────────────┼──────────────────────┤
│ 5. Tokens in / out   │ 6. Quality mean      │
│    cap 50k           │    floor 0.75        │
└──────────────────────┴──────────────────────┘
```

Không thêm panel “noise” (HTTP span, CPU, v.v.) vào lớp chính — drill-down deep dùng Langfuse traces.

---

## Mapping Metrics → Traces → Logs (điều tra)

1. **Metrics/Dashboard**: phát hiện triệu chứng (P95, error %, cost, quality).
2. **Langfuse**: mở trace cùng khoảng thời gian, lọc `tags` / `session_id` / latency cao; xem span `retrieve-context` vs `generate-response`.
3. **Logs** (`data/logs.jsonl`): khớp `correlation_id` (hoặc `payload.langfuse_trace_id`) với trace; đọc `request_failed` / `response_sent`.

---

## Evidence checklist

- [ ] Ảnh dashboard hiển thị đủ **6 tên panel**
- [ ] Nhìn rõ **time range = 1h** (hoặc Last 60 minutes)
- [ ] Nhìn rõ **đơn vị** (ms, %, USD, tokens, score)
- [ ] Nhìn rõ **threshold/SLO line** trên ít nhất latency + error + cost + quality
- [ ] `python scripts/validate_dashboard.py` in `HỢP LỆ: 6/6 panel`
- [ ] Lưu ảnh vào `submission/evidence/` (vd. `dashboard-baseline.png`)

Validator chỉ kiểm tra contract YAML — ảnh runtime vẫn cần cho nộp bài.
