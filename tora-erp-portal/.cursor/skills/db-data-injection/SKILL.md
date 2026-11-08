---
name: db-data-injection
description: >-
  Writes ready-to-run mongosh scripts for the TORA ERP portal (SLAPZ, MongoDB
  database tora_logistics) that the user copies and runs themselves, instead
  of the agent touching the database. Checks relationships between
  collections first and updates every related collection (references,
  denormalized names, code counters, activity log). Use when the user asks to
  inject, seed, insert, import, add dummy / sample data, bulk update, fix,
  rename, or delete data directly in the database ("masukkan data", "isi data
  langsung ke DB", "query insert", "data dummy").
---

# DB data injection — give the query, never run it

## Golden rules

1. **Never execute anything against the database yourself.** No `mongosh`,
   no `python -c`, no test client, no seed script runs, no MCP database
   calls. Your output is a script; the user runs it.
2. End every answer with a clear instruction, in the user's language, e.g.:
   *"Salin query di atas, buka mongosh (atau MongoDB Compass › tab Mongosh)
   ke database `tora_logistics`, tempel, lalu jalankan. Jalankan bagian
   **Cek** dulu, baru bagian **Eksekusi**."*
3. **Check relationships before writing.** Read
   [references/relationships.md](references/relationships.md), then re-check
   `slapz102_core/model.py` and the owning `*_proc.py` (they are the source of
   truth; collections may have been added since this skill was written).
4. **Adjust related collections in the same script**: referenced ids,
   denormalized copies (names, codes), code counters, and `db_record_log`.
   Never leave the app in a state its own UI could not have produced.
5. **Look up references by a readable key** (contact name, plate number,
   tracking code, invoice number) inside the script. Never ask the user for
   24-hex ids and never hard-code ids you invented.
6. **Fail loudly.** If a required reference is missing or ambiguous, the
   script throws before writing anything.
7. **Soft delete only** (`is_deleted: true`), never `deleteOne/deleteMany`
   or `drop`.
8. **Idempotent**: running the script twice must not create duplicates
   (check the natural key first, skip or update).

The database name is `MONGO_DB_NAME` from `slapz102_core/config.py`
(default `tora_logistics`); tests use `slapz_test`. Confirm with the user if
they run a different environment.

## Workflow

```
- [ ] 1. Restate what will change, in one or two sentences
- [ ] 2. List affected collections: target + referenced + dependent
         (relationships.md "Who points at me" column)
- [ ] 3. Note what is NOT possible in plain mongosh (e.g. password hashes)
         and how the user should do it instead
- [ ] 4. Write the script: Cek -> Eksekusi -> Verifikasi -> Batalkan
- [ ] 5. Explain each block in one line and give the copy/run instruction
```

## Script template

Always use this shape (see [examples/queries.md](examples/queries.md)):

```js
// ===== 0. Database (works when pasted or loaded as a file) =====
db = db.getSiblingDB("tora_logistics");

// ===== 1. Helper: framework fields (same as database.new()) =====
const NOW = Date.now() + 7 * 3600 * 1000;                       // Jakarta clock, as the app stores it
const STAMP = new Date(NOW).toISOString().slice(0, 19).replace("T", " ");
function base(id) {
  return { _id: id, ipkey: id.toString(), pkey: id.toString() + "-0000-0-" + NOW,
           rec_timestamp: NOW, rec_timestamp_str: STAMP, is_deleted: false };
}
function mustOne(coll, query, label) {                           // exactly one live match or stop
  const found = db[coll].find(Object.assign({ is_deleted: false }, query)).limit(2).toArray();
  if (found.length !== 1) throw new Error(label + ": " + found.length + " data cocok, harus tepat 1");
  return found[0];
}

// ===== 2. Cek (read only) =====
// ...find the references, print what will be used...

// ===== 3. Eksekusi =====
// ...insertOne / updateOne / updateMany, counters, record log...

// ===== 4. Verifikasi =====
// ...find the new / changed documents...

// ===== 5. Batalkan (jalankan hanya jika perlu) =====
// ...updateMany({_id: {$in: [...]}}, {$set: {is_deleted: true}})...
```

## Field rules (match what the app writes)

- **Framework fields on every insert**: `_id`, `ipkey`, `pkey`,
  `rec_timestamp`, `rec_timestamp_str`, `is_deleted: false` (helper `base()`).
- **Every schema field present** with its default from `model.py`; no fields
  outside the schema (the app is schema-first).
- **References are `id.toString()`** (24-hex string), not `ObjectId`, except
  the document's own `_id`.
- **Text is stored HTML-escaped** by the app (`&` → `&amp;`, `<` → `&lt;`,
  `"` → `&quot;`, `'` → `&#x27;`). Escape these characters in inserted text
  or avoid them.
- **Enums in UPPERCASE** exactly as the proc constants (`CLIENT`, `DRAFT`,
  `REGISTERED`, ...). Dates as `"YYYY-MM-DD"`; amounts as numbers.
- **Computed values are computed in the script** the same way the proc does
  (invoice totals, tax amounts, due dates) — never typed by hand.
- **Codes from counters**: when inserting a document with a generated code
  (AWB, MAN, ANT, invoice number), take the next value from
  `db_code_counter` with `findOneAndUpdate({$inc})` and seed it with `$max`
  first, so the app never re-issues the number.
- **History**: add a `db_record_log` entry (CREATE / CHANGE / EVENT) for
  models that have a log (contact, user, invoice) with
  `author_id: "SYSTEM", author_name: "Sistem"` unless the user names someone.

## Things plain mongosh cannot do safely

| Need | Tell the user |
|---|---|
| User password (`werkzeug` hash) | Create the user in Pengaturan › Pengguna, or generate a hash with `python3 -c "from werkzeug.security import generate_password_hash as h; print(h('SandiBaru123'))"` and paste it into the script |
| Physical delete | Not allowed; use the soft-delete block |
| Changing a confirmed (POSTED) invoice's lines/amounts | Reset ke Draft in the UI first, or cancel and create a new one |
| Bulk changes > ~10k documents | Split into batches; give the batch loop |

## Reference

- Collection map, references, denormalized copies, counters, log models:
  [references/relationships.md](references/relationships.md)
- Full worked scripts (insert contact, invoice with number + totals, rename
  with propagation, safe soft delete, shipment with AWB):
  [examples/queries.md](examples/queries.md)
