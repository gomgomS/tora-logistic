# MongoDB Query Performance & Optimization Rules

## Objective
Always write efficient MongoDB queries. Prevent unnecessary database operations, full collection scans, excessive memory usage, and large data transfers.

Prioritize:
- Query performance
- Proper index utilization
- Minimal document retrieval
- Projection by default
- Reduced database load
- Efficient pagination
- Avoiding unnecessary aggregation operations

## 1. Avoid Expensive Query Patterns

Avoid or minimize the following operators and patterns unless absolutely necessary:

| Operator / Pattern | Risk | Preferred Approach |
|---|---|---|
| `$regex` | Can cause collection scans, especially contains searches and case-insensitive searches | Use indexed exact or prefix searches |
| `$where` | Executes JavaScript for documents | Use native MongoDB operators |
| `$expr` | May prevent efficient index usage depending on the expression | Prefer direct field comparisons |
| `$ne` | Often has low selectivity | Use positive matching conditions where possible |
| `$nin` | Often examines many documents | Use positive `$in` conditions where possible |
| `$not` | May result in inefficient query plans | Prefer explicit positive conditions |
| `$or` | Can be expensive when branches are not indexed | Index every relevant branch |
| Large `$in` | Large lists increase query planning and execution costs | Limit input size or batch requests |
| `$lookup` | Can be expensive when joining large collections | Index foreign join fields and filter early |
| `$unwind` | Expands document counts | Filter and limit input before unwinding |
| `$group` | Can consume significant CPU and memory | Filter early and reduce input documents |
| `$sort` | Can require in-memory sorting | Create an appropriate compound index |
| Large `$skip` | Performance degrades as offset increases | Use cursor-based pagination |
| `$facet` | Multiple pipeline branches can increase resource usage | Use only when necessary |
| Unbounded queries | May retrieve excessive documents | Always apply reasonable limits |

## 2. Projection Is Mandatory by Default

Always use projection when retrieving documents.

Never retrieve all fields using `find()` unless the entire document is genuinely required.

Bad:
```python
users = db.db_user.find({"status": "active"})
```

Good:
```python
users = db.db_user.find(
    {"status": "active"},
    {
        "_id": 1,
        "username": 1,
        "email": 1,
        "status": 1
    }
)
```

### Projection Rules
- Retrieve only fields required by the current operation.
- Exclude large fields such as images, binary data, HTML content, descriptions, and embedded arrays when they are not needed.
- Explicitly define projection fields for API responses.
- Avoid returning entire MongoDB documents to Flask templates or API clients.
- Use `_id: 0` when the document ID is not required.
- Do not use `{"field": 1}` indiscriminately if additional fields are needed.
- Avoid fetching sensitive fields such as passwords, tokens, and internal credentials unless explicitly required for authentication logic

---

## 3. Applying these rules in SLAPZ

The rules above, written in the house style (4-step query, `is_deleted`
filter, closing comments). Same example as section 2:

```python
def list_active_users(self, limit):
    query = {}
    query["is_deleted"] = False
    query["status"] = "ENABLE"

    projection = {}
    projection["_id"] = 0
    projection["fk_user_id"] = 1
    projection["username"] = 1
    projection["email"] = 1
    projection["status"] = 1

    cursor = self.mgdDB.db_user.find(query, projection)
    cursor = cursor.sort("rec_timestamp", -1)
    cursor = cursor.limit(limit)

    recs = list(cursor)
    return recs
# end def
```

Framework-specific notes:

- **Soft delete filter is a positive match.** Always `query["is_deleted"] = False`, never `{"is_deleted": {"$ne": True}}` (`$ne` rule above).
- **`_id: 0` is the default.** Templates and APIs use `slug`, `pkey`, or `fk_*` fields as identifiers, not `_id` (an `ObjectId` does not serialize to JSON).
- **Detail pages project too.** List the fields the page shows; do not fall back to `{"_id": 0}` alone when the document has large or sensitive fields.
- **`db_user.password`** is only projected inside the login/password-check proc method, never in lists, detail pages, or API responses.
- **Large `$in`:** cap the id list (for example 500) and batch beyond that.
- **`$or`:** every branch needs its own index; prefer one `$in` on a single field when the branches test the same field.
- **Cursor-based pagination:** see "Load more / infinite scroll" in `examples/mongodb-query.md` (`rec_timestamp` < last seen value).
- **Searching inside text** (contains, case-insensitive): only on small collections, always with an indexed equality filter plus `limit()`. For a real full-text search need, ask before adding a text index.

Review checklist for every new query:

- [ ] Has `is_deleted: False` and only positive conditions where possible
- [ ] Has an explicit projection (no sensitive or large fields that are not needed)
- [ ] Has a `limit()` (or is a `find_one`)
- [ ] Filter + sort are covered by one compound index (equality -> sort -> range)
- [ ] No query inside a loop; `$in` lists are capped
- [ ] Aggregations start with `$match`, and `$limit` comes before `$lookup` / `$unwind` when possible
- [ ] `explain()` shows `IXSCAN`, not `COLLSCAN`, and no in-memory `SORT` stage
