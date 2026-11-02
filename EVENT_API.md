# Event ingestion API (generic vendor-neutral format)

`POST /events` accepts JSON from a configured source and requires the `X-Event-Api-Key` header. The local demo uses `EVENT_API_KEY`. Production integrations can set `EVENT_SOURCE_KEYS` to comma-separated `source:key` pairs (for example `vendor-a:secret-a,vendor-b:secret-b`) to require an independent credential for each source.

```json
{
  "event_id": "source-42-000019",
  "source": "SIMULATED-gate-west",
  "event_type": "entry",
  "occurred_at": "2026-11-01T10:15:00Z",
  "lot_id": "00000000-0000-0000-0000-000000000001",
  "slot_id": "00000000-0000-0000-0000-000000000002",
  "plate": null
}
```

`event_type` is one of `entry`, `exit`, `occupied`, or `vacated`. `event_id` is unique per operator; retries return HTTP 200 with `duplicate: true` and do not create another event. A successfully accepted event returns 202. Invalid payloads return FastAPI's 422 validation response. Plate is optional and should be omitted unless needed. This is a generic contract; vendor formats are UNKNOWN. Never expose source keys in browser code; rotate credentials when removing a source.
