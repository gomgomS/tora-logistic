# MongoDB Patterns — SLAPZ (slapz102)

SLAPZ is schema-first: every collection has a template in
`slapz102_core/model.py`, and new records are built from that template.

## Contents

1. Schema registry (`model.py`)
2. Framework-managed fields
3. Creating records
4. Reading records
5. IDs and cross-document references
6. Updating records
7. Soft delete
8. Atomic counters and generated codes
9. Search
10. Bulk updates and embedded arrays
11. PyMongo 4 rules
12. Query style (easy to read)
13. Performance rules
14. Indexes

## 1. Schema registry (`slapz102_core/model.py`)

Register the collection in the `db` dict **before** using it:

```python
"db_vehicle": {
    "plate_number": "",
    "vehicle_type": "",
    "ownership": "INTERNAL",
    "vendor_name": ""
},
```

- Collection names start with `db_`.
- Every field has an empty or default value (`""`, `0`, `[]`, `{}`, `False`,
  or a default enum such as `"INTERNAL"`).
- Enum values are UPPERCASE strings (`"REGISTERED"`, `"PLANNED"`, `"OPEN"`).
- **Additions only**: never remove or rename a field, and never drop or rename
  a collection. Existing documents must keep working.
- Keep the comment table in `model.py` up to date when adding a collection
  (spec name and notes).

## 2. Framework-managed fields

`database.new()` adds these automatically. **Do not declare them in
`model.py`**:

| Field | Value |
|---|---|
| `_id` | new `ObjectId` |
| `ipkey` | `str(_id)` |
| `pkey` | `str(_id) + "-" + <random>-<counter>-<ms>` |
| `rec_timestamp` | creation time in ms (timezone from `config.JKTA_TZ`) |
| `rec_timestamp_str` | `"YYYY-MM-DD HH:MM:SS"` |
| `is_deleted` | `False` |

`rec_timestamp` / `rec_timestamp_str` serve as `created_at`; sort by
`rec_timestamp` for newest-first lists.

## 3. Creating records

Only through the model:

```python
rec = database.new(self.mgdDB, "db_contact")
rec.put("name", name)
rec.put("category", category)
rec.insert()
saved = rec.get()
new_id = str(saved.get("_id", ""))
```

- `put()` raises `ValueError("SETTING_NON_EXISTING_FIELD", ...)` for keys
  missing from the schema. This is by design: add the field to `model.py`
  instead of bypassing the model.
- Never call `insert_one()` directly for a registered collection.
- `rec.insert(lock=session)` accepts a PyMongo session when a transaction is
  required.

## 4. Reading records

Read through the collection handle on the proc:

```python
recs = list(self.mgdDB.db_sample_item.find(
    {"is_deleted": False},
    {"_id": 0}
).sort("rec_timestamp", -1))

rec = self.mgdDB.db_sample_item.find_one(
    {"slug": slug, "is_deleted": False},
    {"_id": 0}
)
```

- Every query includes `"is_deleted": False`.
- When the template does not need the id, project `{"_id": 0}`.
- When the template needs the id (edit/delete links, Select2), keep `_id` and
  convert it with a `_<entity>_public()` helper (section 5). Never send a raw
  `ObjectId` to Jinja or `jsonify`.
- Wrap cursors in `list(...)` before returning them from a proc.

## 5. IDs and cross-document references

- References between documents store the **24-hex `str(_id)`** of the target
  (`sender_id`, `vehicle_id`, `shipment_ids`, ...).
- Public dicts expose `id` instead of `_id`:

```python
def _contact_public(self, doc):
    doc["id"] = str(doc.pop("_id"))
    return doc
# end def
```

- Convert incoming ids safely; an invalid id means "not found", not a crash:

```python
try:
    oid = ObjectId(contact_id)
except Exception:
    return None
# end try
```

- Resolve many references with one `$in` query and a map, never one query per
  row (see `contacts_proc.get_contacts_map`).

## 6. Updating records

Partial updates go through the handle with `$set`, not through the model:

```python
self.mgdDB.db_contact.update_one(
    {"_id": ObjectId(contact["id"])},
    {"$set": {
        "name": name,
        "category": category
    }}
)
```

- Load and validate the record first (return an ERROR dict if not found).
- Only `$set` fields that exist in the schema.
- Use `modified_count` from the result when the caller needs a count.

## 7. Soft delete

Never physically remove documents:

```python
self.mgdDB.db_contact.update_one(
    {"_id": ObjectId(contact["id"])},
    {"$set": {"is_deleted": True}}
)
```

Do not use `delete_one`, `delete_many`, or `mongo_model.delete()` for business
data. The only allowed physical delete is dropping the scratch test database
in `tests/`.

## 8. Atomic counters and generated codes

Human-readable codes (AWB, manifest, delivery) come from `db_code_counter`
with an atomic `find_one_and_update` + `$inc`, so concurrent requests never
collide:

```python
def _next_code(self, prefix, date_key):
    counter_key = prefix + "-" + date_key
    rec = self.mgdDB.db_code_counter.find_one_and_update(
        {"counter_key": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER
    )
    return counter_key + "-" + str(rec["seq"]).zfill(4)
# end def
```

Reuse the existing `_next_code` in `shipments_proc` instead of writing a new
counter. Never generate codes with `count_documents() + 1`.

## 9. Search

Case-insensitive regex search always escapes user input:

```python
q = (q or "").strip()
if q != "":
    pattern = re.escape(q)
    query["$or"] = [
        {"name": {"$regex": pattern, "$options": "i"}},
        {"company_name": {"$regex": pattern, "$options": "i"}}
    ]
# end if
```

Add `.limit(n)` for autocomplete endpoints (Select2 uses 20).

## 10. Bulk updates and embedded arrays

Shipments embed their history in `tracking_logs`. A manifest status change
updates every attached shipment in **one** `update_many` that both `$set`s
the status and `$push`es the milestone:

```python
self.mgdDB.db_shipment.update_many(
    {"_id": {"$in": oids}, "is_deleted": False},
    {
        "$set": {"status_utama": new_status},
        "$push": {"tracking_logs": log_entry}
    }
)
```

- Never loop over shipments with one `update_one` each.
- Log entries always have exactly this shape:

```python
log_entry = {
    "milestone_status": "ARRIVED_HUB",
    "location": location,
    "notes": "Manifest " + manifest_code + " tiba di " + location,
    "updated_by": updated_by,
    "timestamp": shipments_proc().now_str()
}
```
- Aggregation-pipeline updates (`[{"$set": ...}]`) are acceptable when a value
  depends on other fields; follow the existing usage in `manifests_proc`.

## 11. PyMongo 4 rules

- Use `insert_one`, `update_one`, `update_many`, `find_one_and_update`,
  `count_documents`.
- The legacy `insert()`, `update()`, `remove()`, `count()` collection methods
  do not exist in PyMongo 4.
- Get the DB handle only via `database.get_db_conn(config.mainDB)`; never
  create a `MongoClient` in a module.

## 12. Query style (easy to read)

Every read method has the same four steps, in this order, so anyone can scan
it top to bottom:

1. Clean the inputs.
2. Build `query`, one filter per `if` block.
3. Run ONE query with projection, sort, and limit.
4. Shape the result in one loop.

```python
def list_shipments(self, filters):
    status = (filters.get("status") or "").strip().upper()
    service_type = (filters.get("service_type") or "").strip().upper()
    q = (filters.get("q") or "").strip()
    query = {"is_deleted": False}
    if status in SHIPMENT_STATUSES:
        query["status_utama"] = status
    # end if
    if service_type in SERVICE_TYPES:
        query["service_type"] = service_type
    # end if
    if q != "":
        query["$or"] = [
            {"tracking_code": {"$regex": re.escape(q), "$options": "i"}},
            {"po_number": {"$regex": re.escape(q), "$options": "i"}}
        ]
    # end if
    projection = {"tracking_logs": 0}
    recs = self.mgdDB.db_shipment.find(query, projection).sort("rec_timestamp", -1).limit(300)
    out = []
    for rec in recs:
        out.append(self._shipment_public(rec))
    # end for
    return out
# end def
```

Rules that keep queries readable:

- Fixed variable names: `query` (filter), `projection` (fields), `update`
  (the `$set`/`$push` dict), `recs` (cursor or list), `rec` (one doc), `out`
  (returned value). Never `q1`, `res2`, `tmp`.
- `query` always starts as `{"is_deleted": False}`; add one key per `if`.
- Compare enums against module constants (`STATUS_REGISTERED`,
  `SERVICE_TYPES`), never scattered string literals.
- When a query, projection, or update is longer than about three keys, give it
  its own variable instead of inlining it in the call.
- One MongoDB operator per line in multi-line dicts; close every block with
  its `# end ...` comment.
- Write a short comment above any query whose *reason* is not obvious (why
  this filter, why this limit), not what it does.
- Prefer plain equality over regex. Enum/code fields are stored normalized
  (UPPERCASE, trimmed), so `query["status_utama"] = status` is enough.
- Free-text search uses `re.escape(q)` with `"$options": "i"`. The
  `".*" + ... + ".*"` wrapper in older code is redundant; new code drops it.
  For "starts with" search use `"^" + re.escape(q)`.

## 13. Performance rules

Readable does not mean slow. Every new query must pass this checklist:

```
- [ ] Filter + sort fields are covered by an index (section 14)
- [ ] List queries have .limit(n): 300 for pages, 20 for autocomplete
- [ ] Projection excludes what the page doesn't show (tracking_logs on lists)
- [ ] No query or update inside a loop: batch with $in / update_many
- [ ] Filtering happens in MongoDB, not in Python, whenever MongoDB can do it
- [ ] Existence checks fetch only _id
- [ ] Per-group counts use one aggregate $group, not one count per group
```

**One round trip per batch.** Collect ids first, query once, then map:

```python
ids = set()
for rec in recs:
    ids.add(rec.get("sender_id", ""))
# end for
contacts = contacts_proc().get_contacts_map(list(ids))
```

Use a `set` for "already seen?" checks inside loops and convert to `list()`
for `$in`; use a dict for lookups by id. Never nest a loop to find a match.

**Existence check: only fetch `_id`.**

```python
existing = self.mgdDB.db_vehicle.find_one(
    {"plate_number": plate, "is_deleted": False},
    {"_id": 1}
)
if existing != None:
    return {"status": "ERROR", "desc": "Nomor polisi sudah terdaftar"}
# end if
```

Not `count_documents(...) > 0` (counts every match) and not a full document.

**Guarded update: one round trip, race-safe.** When the rule is "only if the
record is still in state X", put the state in the filter and read
`matched_count`, instead of `find_one` + check + `update_one`:

```python
result = self.mgdDB.db_shipment.update_one(
    {
        "tracking_code": tracking_code,
        "status_utama": STATUS_REGISTERED,
        "is_deleted": False
    },
    {"$set": {"is_deleted": True}}
)
if result.matched_count == 0:
    return self._explain_not_deletable(tracking_code)
# end if
```

The extra read to build a precise error message happens only on the failure
path. Keep the load-first style when the logic genuinely needs the
document's data (for example, to compute new values).

**Group counts in one query.**

```python
pipeline = [
    {"$match": {"is_deleted": False}},
    {"$group": {"_id": "$status_utama", "count": {"$sum": 1}}}
]
found = {}
for row in self.mgdDB.db_shipment.aggregate(pipeline):
    found[row["_id"]] = row["count"]
# end for
```

Use aggregation only for `$match` / `$group` / `$sort` / `$limit` / `$project`
summaries like this. Keep business decisions in Python.

**Paging.** Do not use `.skip()` for deep pages; it scans every skipped
document. Page by the sort key: `query["rec_timestamp"] = {"$lt": last_seen}`
with the same `.sort("rec_timestamp", -1).limit(n)`.

**Don'ts.**

- `find({})` without `is_deleted` or without `.limit()` on a growing collection.
- `list(cursor)` just to loop once; iterate the cursor directly unless you
  need `len()` or two passes.
- Regex on a field that has an exact value (codes, enums, ids).
- Leading `".*"` or unescaped user input in `$regex`.
- Python-side filtering of a large result that a query filter could remove.

## 14. Indexes

The repo does not create indexes yet, so every query currently scans its
collection. New filter/sort combinations must be backed by an index.

Order index keys **Equality, Sort, Range**: fields matched exactly first,
then the sort field, then range fields (`$gt`, `$lt`, `$in` with many values).

Indexes that match existing queries:

| Collection | Index | Serves |
|---|---|---|
| `db_shipment` | `tracking_code` (unique) | `get_by_code`, tracking, updates by code |
| `db_shipment` | `po_number` | public tracking `$or` |
| `db_shipment` | `is_deleted, status_utama, rec_timestamp -1` | lists, counts per status, available cargo |
| `db_manifest` | `manifest_code` (unique) | lookups by code |
| `db_manifest` | `is_deleted, status, rec_timestamp -1` | manifest lists, open counts |
| `db_contact` | `is_deleted, category, name` | contact lists, autocomplete |
| `db_user` | `username` (unique) | login, user management |
| `db_code_counter` | `counter_key` (unique) | prevents duplicate counters on concurrent upsert |

There is no index bootstrap in the framework. Do not invent one silently: when
a change needs a new index, list the exact call in your summary and ask
before adding setup code, for example:

```python
self.mgdDB.db_shipment.create_index(
    [("is_deleted", 1), ("status_utama", 1), ("rec_timestamp", -1)]
)
```

`$or` queries need an index on **each** branch, or MongoDB scans.
