# Example: MongoDB query and update recipes

Copy-ready snippets for proc methods. All of them assume the standard proc
class (`mgdDB = database.get_db_conn(config.mainDB)`) and the sys.path header.
Rules behind them: [../references/mongodb-patterns.md](../references/mongodb-patterns.md).

## List with filter, search, and sort

```python
def list_vehicles(self, ownership, q=""):
    query = {"is_deleted": False}
    ownership = (ownership or "").strip().upper()
    if ownership in ["INTERNAL", "VENDOR"]:
        query["ownership"] = ownership
    # end if
    q = (q or "").strip()
    if q != "":
        pattern = re.escape(q)
        query["$or"] = [
            {"plate_number": {"$regex": pattern, "$options": "i"}},
            {"vendor_name": {"$regex": pattern, "$options": "i"}}
        ]
    # end if
    recs = self.mgdDB.db_vehicle.find(query).sort("plate_number", 1).limit(300)
    out = []
    for rec in recs:
        rec["id"] = str(rec.pop("_id"))
        out.append(rec)
    # end for
    return out
# end def
```

## Newest first, without ids (read-only display)

```python
recs = list(self.mgdDB.db_sample_item.find(
    {"is_deleted": False},
    {"_id": 0}
).sort("rec_timestamp", -1))
```

## Get one by id (safe against invalid ids)

```python
def get_vehicle(self, vehicle_id):
    try:
        oid = ObjectId(vehicle_id)
    except Exception:
        return None
    # end try
    rec = self.mgdDB.db_vehicle.find_one({"_id": oid, "is_deleted": False})
    if rec == None:
        return None
    # end if
    rec["id"] = str(rec.pop("_id"))
    return rec
# end def
```

## Resolve references in one query (avoid N+1)

```python
shipments = self.list_shipments()
ids = []
for s in shipments:
    ids.append(s.get("sender_id", ""))
    ids.append(s.get("receiver_id", ""))
# end for
contacts = contacts_proc().get_contacts_map(ids)
for s in shipments:
    s["sender"] = contacts.get(s.get("sender_id", ""), {})
    s["receiver"] = contacts.get(s.get("receiver_id", ""), {})
# end for
```

## Create through the model

```python
rec = database.new(self.mgdDB, "db_vehicle")
rec.put("plate_number", plate)
rec.put("vehicle_type", vehicle_type)
rec.put("ownership", ownership)
rec.insert()
saved = rec.get()
return {"status": "SUCCESS", "desc": "Armada dibuat", "id": str(saved.get("_id", ""))}
```

## Duplicate check before insert

```python
existing = self.mgdDB.db_vehicle.find_one({
    "plate_number": {"$regex": "^" + re.escape(plate) + "$", "$options": "i"},
    "is_deleted": False
})
if existing != None:
    return {"status": "ERROR", "desc": "Nomor polisi sudah terdaftar"}
# end if
```

## Partial update

```python
vehicle = self.get_vehicle(vehicle_id)
if vehicle == None:
    return {"status": "ERROR", "desc": "Armada tidak ditemukan"}
# end if
self.mgdDB.db_vehicle.update_one(
    {"_id": ObjectId(vehicle["id"])},
    {"$set": {"vehicle_type": vehicle_type, "vendor_name": vendor_name}}
)
return {"status": "SUCCESS", "desc": "Armada diperbarui"}
```

## Soft delete

```python
self.mgdDB.db_vehicle.update_one(
    {"_id": ObjectId(vehicle["id"])},
    {"$set": {"is_deleted": True}}
)
```

## Generated code from the atomic counter

```python
date_key = time.strftime("%Y%m%d")
code = self._next_code("AWB", date_key)    # -> "AWB-20261108-0001"
```

Reuse `_next_code` from `shipments_proc`; never use `count_documents() + 1`.

## Bulk status change + tracking log push

```python
oids = self._to_object_ids(manifest["shipment_ids"])
updated = self.mgdDB.db_shipment.update_many(
    {"_id": {"$in": oids}, "is_deleted": False},
    {
        "$set": {"status_utama": "IN_TRANSIT", "current_location": location},
        "$push": {"tracking_logs": {
            "milestone_status": "IN_TRANSIT",
            "location": location,
            "notes": "Berangkat dari " + origin + " via manifest " + manifest_code,
            "updated_by": updated_by,
            "timestamp": now_str
        }}
    }
).modified_count
```

## Counts for dashboards

```python
total = self.mgdDB.db_shipment.count_documents({"is_deleted": False})
in_transit = self.mgdDB.db_shipment.count_documents({
    "is_deleted": False,
    "status_utama": "IN_TRANSIT"
})
```

## Readable and fast: before / after

Each pair keeps the house style and shows the faster way to write it.

### Counts per status: one query instead of one per status

Before (6 round trips):

```python
out = []
for status in SHIPMENT_STATUSES:
    count = self.mgdDB.db_shipment.count_documents({
        "is_deleted": False, "status_utama": status
    })
    out.append({"status": status, "count": count})
# end for
return out
```

After (1 round trip, same output):

```python
pipeline = [
    {"$match": {"is_deleted": False}},
    {"$group": {"_id": "$status_utama", "count": {"$sum": 1}}}
]
found = {}
for row in self.mgdDB.db_shipment.aggregate(pipeline):
    found[row["_id"]] = row["count"]
# end for
out = []
for status in SHIPMENT_STATUSES:
    out.append({"status": status, "count": found.get(status, 0)})
# end for
return out
```

### List page: don't load what the page doesn't show

Before (every shipment's full tracking history is loaded for a table):

```python
recs = list(self.mgdDB.db_shipment.find(query).sort("rec_timestamp", -1).limit(300))
```

After:

```python
projection = {"tracking_logs": 0}
recs = self.mgdDB.db_shipment.find(query, projection).sort("rec_timestamp", -1).limit(300)
```

### Validate two references: one batch instead of two lookups

Before:

```python
cproc = contacts_proc()
if cproc.get_contact(sender_id) == None or cproc.get_contact(receiver_id) == None:
    return None, {"status": "ERROR", "desc": "Pengirim dan penerima harus ada di data master kontak"}
# end if
```

After:

```python
contacts = contacts_proc().get_contacts_map([sender_id, receiver_id])
if sender_id not in contacts or receiver_id not in contacts:
    return None, {"status": "ERROR", "desc": "Pengirim dan penerima harus ada di data master kontak"}
# end if
```

`get_contacts_map` does not filter `is_deleted`; add `"is_deleted": False`
to its query if deleted contacts must be rejected.

### State-guarded delete: one round trip, race-safe

Before (read, check, write: 2 round trips, and the status can change in
between):

```python
shipment = self.get_by_code(tracking_code)
if shipment == None:
    return {"status": "ERROR", "desc": "Order tidak ditemukan"}
# end if
if shipment.get("status_utama") != STATUS_REGISTERED:
    return {"status": "ERROR", "desc": "Order yang sudah masuk manifest tidak bisa dihapus"}
# end if
self.mgdDB.db_shipment.update_one(
    {"_id": ObjectId(shipment["id"])},
    {"$set": {"is_deleted": True}}
)
```

After (success path is 1 round trip; the extra read happens only to explain
a failure):

```python
query = {
    "tracking_code": tracking_code,
    "status_utama": STATUS_REGISTERED,
    "is_deleted": False
}
result = self.mgdDB.db_shipment.update_one(query, {"$set": {"is_deleted": True}})
if result.matched_count == 1:
    return {"status": "SUCCESS", "desc": "Order dihapus"}
# end if
if self.get_by_code(tracking_code) == None:
    return {"status": "ERROR", "desc": "Order tidak ditemukan"}
# end if
return {"status": "ERROR", "desc": "Order yang sudah masuk manifest tidak bisa dihapus"}
```

### "Already seen?" inside a loop: set instead of list

Before:

```python
codes = []
for rec in recs:
    code = (rec.get("active_manifest_code") or "").strip()
    if code != "" and code not in codes:
        codes.append(code)
    # end if
# end for
```

After:

```python
codes = set()
for rec in recs:
    code = (rec.get("active_manifest_code") or "").strip()
    if code != "":
        codes.add(code)
    # end if
# end for
query = {"manifest_code": {"$in": list(codes)}, "is_deleted": False}
```

### Existence check: fetch only `_id`

Before:

```python
if self.mgdDB.db_user.count_documents({"username": username, "is_deleted": False}) > 0:
```

After:

```python
existing = self.mgdDB.db_user.find_one(
    {"username": username, "is_deleted": False},
    {"_id": 1}
)
if existing != None:
```

### "Load more" paging: range on the sort key, not skip

```python
query = {"is_deleted": False}
if last_seen != None:
    query["rec_timestamp"] = {"$lt": last_seen}
# end if
recs = self.mgdDB.db_shipment.find(query, {"tracking_logs": 0}).sort("rec_timestamp", -1).limit(50)
```

The page sends back the `rec_timestamp` of its last row as `last_seen`.

## Anti-patterns (never do these)

```python
self.mgdDB.db_vehicle.insert_one({...})          # bypasses the schema model
self.mgdDB.db_vehicle.delete_one({...})          # physical delete
self.mgdDB.db_vehicle.remove({...})              # PyMongo 3 API, gone in 4
self.mgdDB.db_vehicle.find({"plate_number": {"$regex": q}})   # unescaped user regex
self.mgdDB.db_vehicle.find({})                   # missing is_deleted filter
for s in shipments:                              # N+1 updates instead of update_many
    self.mgdDB.db_shipment.update_one(...)
# end for
pymongo.MongoClient(...)                         # use database.get_db_conn
self.mgdDB.db_shipment.find(query).skip(5000)    # scans every skipped doc
self.mgdDB.db_user.count_documents(q) > 0        # existence check that counts all
{"$regex": ".*" + re.escape(q) + ".*"}           # redundant wrapper, use re.escape(q)
```
