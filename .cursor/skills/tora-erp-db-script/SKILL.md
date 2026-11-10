---
name: tora-erp-db-script
description: >-
  Give ready-to-run mongosh scripts for tora-erp-portal data (database
  tora_logistics) that the USER runs — never touch the database yourself.
  Checks relationships and updates every related collection (references,
  copied names, counters, record log). Use when asked to inject, seed,
  import, dump simulation data, add dummy data, bulk fix, rename, or delete
  data ("masukkan data", "data dummy", "query insert", "dump data").
---

# TORA ERP — data scripts (give the query, never run it)

## Rules

1. Never execute anything against the DB (no mongosh, python, test client,
   MCP). Output a script and tell the user: *"Salin, buka mongosh / Compass
   › Mongosh ke `tora_logistics`, jalankan bagian **Cek** dulu, lalu
   **Eksekusi**."*
2. Read [relationships.md](relationships.md), then confirm against
   `tora-erp-portal/slapz102_core/model.py` and the owning `*_proc.py`.
3. Update related data in the same script: copied names, counters,
   `db_record_log`, settlement on both sides. The result must look like
   something the app's own UI could have produced.
4. Find references by readable keys (name, number, code); never ask for or
   invent 24-hex ids. Missing / ambiguous → `throw` before writing.
5. Soft delete only. Idempotent (check the natural key; second run = no
   duplicate). Text HTML-escaped like the app (`esc()`). Compute totals the
   way the proc does; never type them by hand.
6. Every script: **Cek → Eksekusi → Verifikasi → Batalkan** (Batalkan
   commented out). One line of explanation per block.

## Helpers (top of every script)

```js
db = db.getSiblingDB("tora_logistics");
const NOW = Date.now() + 7 * 3600 * 1000;            // Jakarta clock, like database.new()
const STAMP = new Date(NOW).toISOString().slice(0, 19).replace("T", " ");
function base(id) { return { _id: id, ipkey: id.toString(), pkey: id.toString() + "-0000-0-" + NOW,
  rec_timestamp: NOW, rec_timestamp_str: STAMP, is_deleted: false }; }
function mustOne(coll, q, label) { const f = db[coll].find(Object.assign({ is_deleted: false }, q)).limit(2).toArray();
  if (f.length !== 1) throw new Error(label + ": " + f.length + " data cocok, harus tepat 1"); return f[0]; }
function esc(t) { return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#x27;"); }
function round2(n) { return Math.round(n * 100) / 100; }
function rp(n) { return "Rp " + (n < 0 ? "-" : "") + Math.abs(n).toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function logEntry(model, id, kind, body, changes) { db.db_record_log.insertOne(Object.assign(base(new ObjectId()), {
  model: model, record_id: id.toString(), kind: kind, body: body || "", changes: changes || [],
  author_id: "SYSTEM", author_name: "Sistem" })); }
function nextCode(key, used) {                         // atomic; never re-issues a number
  db.db_code_counter.updateOne({ counter_key: key }, { $max: { seq: used } }, { upsert: true });
  return db.db_code_counter.findOneAndUpdate({ counter_key: key }, { $inc: { seq: 1 } },
    { upsert: true, returnDocument: "after" }).seq; }
function rx(s) { return s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&"); }
```

Document number = prefix from `db_config` `accounting_sequences.data.<key>`
(fallback to the default in relationships.md), tokens `{TAHUN}` `{THN}`
`{BULAN}` from the document date, then `nextCode("SEQ:" + prefix,
<highest used with that prefix in its collection>)` padded. URL number =
`nextCode("SEQID:<type>", <highest seq of that type>)`.

## Not possible in plain mongosh

| Need | Tell the user |
|---|---|
| User password | Create the user in Pengaturan › Pengguna (werkzeug hash) |
| Change lines of a Terekam invoice | Reset ke Draft in the UI (reset its payments first) |
| > ~10k documents | Give a batched loop |
