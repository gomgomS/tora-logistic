# Python Performance & Clean Code Engineering Rules (SLAPZ / slapz102)

## Objective

Write Python code that is:
- Highly performant and resource-efficient.
- Easy to read, understand, and maintain.
- Simple to debug and extend.
- Free from unnecessary operations.
- Efficient in CPU, memory, database access, and I/O.
- Compatible with the SLAPZ architecture (blueprint -> view -> proc) and house style.

**Core principle: Maximum practical performance without sacrificing readability.**

Do not write unnecessarily complicated code just to achieve micro-optimizations.

House style always wins over generic Python habits:
- Closing comments on every block (`# end if`, `# end for`, `# end while`, `# end def`, `# end class`, `# end try`, `# end with`).
- No f-strings (concatenation or `"".join(...)`), no type annotations, no relative imports.
- `== None` / `!= None`.
- Explicit `for` loops are the default; see section 2 for when a comprehension is allowed.
- Only stdlib + Flask + PyMongo. No new packages without asking (`requirements.txt`).

---

## 1. Avoid Unnecessary Operations

Avoid:
- Repeated calculations with identical inputs.
- Repeated database queries (the same `find_one` twice in one request).
- Repeated function / proc calls inside loops when results can be reused.
- Unnecessary object creation (a new `xxx_proc()` per loop iteration).
- Unnecessary conversions between list, tuple, set, and dictionary.
- Repeated serialization and deserialization.
- Unnecessary copying of dictionaries and lists.
- Computing values that are never used.
- Re-sorting data in Python that MongoDB already returned sorted.
- Nested loops when a dictionary or set lookup can solve the problem.

Bad:
```python
for user in users:
    if user["fk_user_id"] in self.get_active_user_ids():
        self.process(user)
    # end if
# end for
```

Good:
```python
active_user_ids = set(self.get_active_user_ids())

for user in users:
    if user["fk_user_id"] in active_user_ids:
        self.process(user)
    # end if
# end for
```

Prefer O(1) average-time `dict` / `set` lookups over repeated O(n) list searches.

---

## 2. Optimize Loops and Data Processing

- Avoid unnecessary nested loops.
- Avoid repeated `len()` checks when the result is already known and no mutation occurs.
- Move invariant calculations (constants, `config.*` values, compiled regex) outside loops.
- Use dictionary lookups instead of repeatedly searching lists.
- Use `enumerate()` instead of manually maintaining counters.
- Use `zip()` when iterating over related collections.
- Iterate a PyMongo cursor directly instead of `list(cursor)` when the result is used once (exports, totals, building a dict).
- Process large datasets in batches (`limit` + range pagination, `bulk_write` for writes).

House style for building a list is the explicit loop:

```python
slug_list = []
for item in items:
    slug_list.append(item["slug"])
# end for
```

A simple comprehension is allowed when it is ONE expression with at most ONE
simple condition and fits on one line:

```python
slug_list = [item["slug"] for item in items]
```

Anything with more logic (several conditions, function calls, nesting) stays an
explicit loop. The speed difference between the two is negligible compared to
one database round trip.

For large or streaming datasets, iterate the cursor or use a generator.
Do not force generators when a list is needed multiple times.

Counters with `enumerate()` and related lists with `zip()`:

```python
for position, slug in enumerate(slug_list):
    ops.append(UpdateOne({"slug": slug, "is_deleted": False}, {"$set": {"order": position}}))
# end for

for title, body in zip(title_list, body_list):
    self.create_article({"title": title, "body": body})
# end for
```

---

## 3. Use the Right Data Structures

| Requirement | Preferred Structure |
|---|---|
| Fast membership checking | `set` |
| Key-based lookup (join two result lists) | `dict` keyed by `slug` / `pkey` / `fk_*` |
| Ordered collection | `list` |
| Immutable constants | `tuple` (or a module-level `list` like `ALLOWED_STATUS`) |
| FIFO queue | `collections.deque` |
| Counting occurrences | `collections.Counter` |
| Grouping records | `collections.defaultdict(list)` |

Bad:
```python
for article in articles:
    if article["fk_user_id"] in banned_user_list:
        continue
    # end if
    visible.append(article)
# end for
```

Better for repeated lookups:
```python
banned_user_set = set(banned_user_list)

for article in articles:
    if article["fk_user_id"] in banned_user_set:
        continue
    # end if
    visible.append(article)
# end for
```

Grouping records in one pass:

```python
from collections import defaultdict

articles_by_user = defaultdict(list)
for article in articles:
    articles_by_user[article["fk_user_id"]].append(article)
# end for
```

Counting and grouping over a whole collection belongs in MongoDB (`$group`),
not in Python after loading every document.

Do not convert data structures repeatedly without a clear benefit.

---

## 4. Avoid Expensive Python Patterns

### Unnecessary deep copies

```python
new_data = copy.deepcopy(data)
```

Use a shallow copy (`dict(data)`, `list(items)`) or direct access when deep
copying is unnecessary. The `copy.deepcopy` calls inside `slapz102_core`
(`database.new`, `mongo_model`) are framework machinery: leave them as they are.

### Repeated string concatenation in loops

Concatenation (`a + " " + b`) is the house style for small strings. Inside a
loop that builds a large string, collect parts and join once:

Bad:
```python
result = ""
for item in items:
    result = result + str(item)
# end for
```

Good:
```python
parts = []
for item in items:
    parts.append(str(item))
# end for
result = "".join(parts)
```

### Repeated regular expression compilation

Compile once at module level, next to the other constants:

```python
import re

SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")

def _is_valid_slug(slug):
    return SLUG_PATTERN.match(slug) != None
# end def
```

Use normal string methods (`startswith`, `endswith`, `isalnum`, `in`, `split`)
when regex is unnecessary; `_slugify` in `sample_proc.py` is the model.

### Unnecessary exception handling

Do not use exceptions for normal control flow when a simple condition is
clearer and cheaper. Use `dict.get(key, default)` instead of `try: d[key]`.
`try/except` is for real failure points: parsing user numbers (`_to_int`),
external I/O, and the blueprint's catch-all.

### Unnecessary lambda functions

Prefer named module-level functions (`def _sort_key(item):`) when logic is
reused or more than a single field access.

---

## 5. Optimize Function Design

- Keep functions focused on one responsibility (one proc method = one business action).
- Avoid excessively large functions; split by step (clean, guard, act, return).
- Avoid excessive function calls for trivial operations inside hot loops.
- Reuse calculated values instead of recalculating them.
- Pass only the required data (a `slug`, not the whole request).
- Avoid unnecessary global variables; module-level constants are fine.
- Avoid excessive abstraction and wrapper functions; no new utility modules that duplicate `slapz102_stdlib`.
- Use early returns to reduce nested conditions.

Good:
```python
def get_user_display_name(user):
    if user == None:
        return None
    # end if
    return user.get("name") or user.get("username")
# end def
```

Avoid deeply nested conditional structures.
However, do not split simple logic into too many tiny functions.

---

## 6. Optimize Conditional Logic

- Check inexpensive and likely-to-fail conditions first (empty input before a DB call).
- Use short-circuit evaluation with `and` and `or`.
- Store a dictionary value in a local variable instead of repeating `params.get(...)`.
- Avoid unnecessary boolean conversions (`if x == True:` -> `if x:`).
- Prefer clear conditions over complicated one-line expressions.

Example:
```python
if user != None and user.get("status") == "ENABLE" and user.get("email"):
    self.process(user)
# end if
```

Guard order in a proc method: cheap checks first, DB checks last:

```python
title = (params.get("title") or "").strip()
if title == "":
    return {"status": "ERROR", "desc": "Title is required"}
# end if
if len(title) > 200:
    return {"status": "ERROR", "desc": "Title is too long"}
# end if
if self._slug_taken(_slugify(title)):
    return {"status": "ERROR", "desc": "Title already exists"}
# end if
```

---

## 7. Memory Optimization

- Avoid loading large files entirely into memory (uploads in `static/upload/`).
- Use streaming and chunk processing.
- Avoid unnecessary list creation (`list(cursor)` only when the list is really needed).
- Release references to large temporary objects when no longer needed.
- Avoid keeping duplicate copies of large datasets.
- Use generators / cursor iteration for sequential processing.
- Be careful with large dictionaries and nested structures.
- Avoid returning large payloads when only a small subset is needed (projection + limit).

Bad:
```python
with open(path) as file:
    data = file.read()
# end with
```

Better for large files, line by line:

```python
with open(path, encoding="utf-8") as file:
    for line in file:
        self._import_line(line)
    # end for
# end with
```

Do not introduce memory optimizations that make ordinary code harder to
maintain without measurable benefit.

---

## 8. Optimize Flask Request Processing

Map each rule to its SLAPZ layer:

| Rule | Where |
|---|---|
| Parse and sanitize request data ONCE: `params = sanitize.clean_html_dic(request.form.to_dict())`, then pass `params` | view |
| Create ONE proc per request and reuse it | view |
| Validate input before expensive processing (CSRF first, then cheap guards, then DB) | view + proc |
| No repeated or N+1 queries during a single request | proc |
| Retrieve only required fields (projection) and paginate large responses | proc |
| Reuse the shared connection: `mgdDB` class attribute; never create a `MongoClient` | proc |
| Keep routes thin: only delegate + catch exceptions | blueprint |
| No `before_request` / middleware doing DB or heavy work on every request | `server.py` |
| `jsonify` once at the end; do not serialize/deserialize data in between | view |

Long-running work (big imports, mass emails) does not belong in a request.
This framework intentionally has no task queue: process in small batches per
request (e.g. a "process next 500" action) and ask before adding any
background worker.

---

## 9. Caching and Reusing Results

Use caching when:
- The same expensive calculation is performed repeatedly.
- Data is frequently read but changes infrequently (e.g. `db_config` values).
- Database queries are repeated with identical parameters.
- External API responses can safely be reused.

First level (always): reuse within one request. Load once, pass the result
around, never call the same proc read twice.

Second level (read-mostly data): a small per-process cache in the proc module
with a short TTL:

```python
import time

CONFIG_CACHE_SECONDS = 60
_config_cache = {"loaded_at": 0, "values": {}}

class config_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def get_values(self):
        now = time.time()
        if now - _config_cache["loaded_at"] < CONFIG_CACHE_SECONDS:
            return _config_cache["values"]
        # end if
        values = {}
        cursor = self.mgdDB.db_config.find({"is_deleted": False}, {"_id": 0, "name": 1, "value": 1})
        for row in cursor:
            values[row["name"]] = row["value"]
        # end for
        _config_cache["values"] = values
        _config_cache["loaded_at"] = now
        return values
    # end def

    def clear_cache(self):
        _config_cache["loaded_at"] = 0
    # end def
# end class
```

Rules:
- Each server process has its own cache: other processes see changes after the TTL. Keep the TTL short and call `clear_cache()` after every write.
- Define cache expiration appropriately.
- Invalidate the cache when the underlying data changes.
- Avoid caching highly dynamic data (per-user data, counters) without a clear consistency strategy.
- Never cache sensitive information (passwords, tokens, session data).
- There is no Redis in this framework. Do not add Redis (or any cache service) without asking first: it is a new dependency in `requirements.txt`.

Do not introduce caching for simple, inexpensive operations (an indexed `find_one` is already fast).

---

## 10. Avoid Blocking Operations

- Avoid unnecessary synchronous network calls inside requests.
- Avoid sequential external API requests when the result is not needed for the response.
- Reuse connections (the shared `mgdDB` pool).
- Always set timeouts for external requests. With the stdlib: `urllib.request.urlopen(url, timeout=5)`.
- Avoid waiting for unnecessary operations.
- Long-running tasks: batch them (section 8); ask before adding workers.
- The app is synchronous Flask. Do not introduce `async/await` or threads to "speed things up"; async does not make CPU-bound work faster and does not fit the architecture.

---

## 11. Choose Efficient Algorithms

Preferred:
- O(1) average-time `dict` and `set` lookups.
- O(n) single-pass processing where possible.
- O(n log n) sorting only when sorting is required (and prefer MongoDB `sort()` with an index).
- Avoid O(n²) operations when a more efficient approach is practical.

Bad:
```python
matched = []
for user in users:
    for active_id in active_ids:
        if user["fk_user_id"] == active_id:
            matched.append(user)
        # end if
    # end for
# end for
```

Better:
```python
active_id_set = set(active_ids)

matched = []
for user in users:
    if user["fk_user_id"] in active_id_set:
        matched.append(user)
    # end if
# end for
```

Best when the data comes from MongoDB: filter in the query
(`{"fk_user_id": {"$in": active_ids}, "is_deleted": False}`) so the
non-matching documents never leave the database.

Choose algorithms based on expected data size and actual requirements.

---

## 12. Readability Is Mandatory

Performance improvements must not make code harder to understand.

Rules:
- Use descriptive variable names (`user_by_id`, `active_user_ids`, not `d`, `x`).
- Prefer straightforward control flow.
- Avoid deeply nested conditions.
- Avoid complicated comprehensions; use an explicit loop.
- Avoid excessive one-line expressions.
- Avoid clever tricks and obscure syntax (walrus `:=`, `match`, chained ternaries) that the codebase does not use.
- Avoid premature optimization.
- Use comments to explain why, not what.
- Keep functions reasonably small and focused.
- Follow the existing SLAPZ coding style (closing comments, no f-strings).

Bad:
```python
x = [f(y) for y in a if y and g(y) and h(y)]
```

Better:
```python
result = []
for item in items:
    if not item:
        continue
    # end if
    if not self._is_valid(item):
        continue
    # end if
    result.append(self._process_item(item))
# end for
```

A slightly longer implementation is preferable when it improves readability.

---

## 13. Avoid Unnecessary Dependencies

- Prefer the Python standard library (`collections`, `re`, `time`, `datetime`, `json`, `urllib`, `secrets`, `html`).
- Reuse what exists: `sanitize`, `csrf`, `idgen`, `helper.response_msg`, `database.new`.
- Runtime dependencies are only Flask and PyMongo. Do not install packages for trivial operations.
- A truly required package goes in `requirements.txt` with a pinned range and must be mentioned to the user first.
- Consider startup time, memory footprint, and maintenance overhead.

---

## 14. Performance Measurement

Do not assume code is faster just because it looks more optimized.
Measure, and keep measurement code out of commits.

Tools (all stdlib / PyMongo):
- `time.perf_counter()` for execution timing.
- `cProfile` for function-level profiling.
- `timeit` for small code comparisons.
- `tracemalloc` for memory allocation analysis.
- PyMongo `cursor.explain()` for database query analysis (it includes `executionStats`).

Quick timing in a proc method during development:

```python
start = time.perf_counter()
recs = self.list_articles(1, 20)
print("list_articles ms: " + str(round((time.perf_counter() - start) * 1000, 2)))
```

Query check:

```python
plan = self.mgdDB.db_article.find(query, projection).sort("rec_timestamp", -1).limit(20).explain()
stats = plan["executionStats"]
print("examined: " + str(stats["totalDocsExamined"]) + " returned: " + str(stats["nReturned"]))
```

`totalDocsExamined` far above `nReturned` means a missing or wrong index.

Prioritize optimization based on actual bottlenecks. In this framework the
bottleneck is almost always the database: fix queries, indexes, and round
trips before touching Python loops.

---

## 15. Mandatory Code Review Checklist

Before completing Python code, verify:

- [ ] Is there any unnecessary operation?
- [ ] Are there repeated calculations?
- [ ] Are there avoidable nested loops?
- [ ] Can repeated list searches use a set or dictionary?
- [ ] Is there unnecessary object creation or copying?
- [ ] Is memory usage reasonable (projection, limit, cursor iteration)?
- [ ] Are database queries minimized (no N+1, no repeated reads in one request)?
- [ ] Are external calls minimized and do they have timeouts?
- [ ] Can the code process data in batches?
- [ ] Is the algorithm efficient for expected data sizes?
- [ ] Is the code still easy to read?
- [ ] Does it follow the house style (closing comments, no f-strings, `== None`, sys.path header)?
- [ ] Is the logic in the right layer (blueprint / view / proc)?
- [ ] Is existing business logic preserved, and does `python3 -m pytest tests/ -v` pass?

## Final Engineering Principle

Write the fastest practical Python implementation that remains clean,
understandable, maintainable, and reliable, inside the SLAPZ pattern.

Performance optimization must follow this priority:

1. Eliminate unnecessary database and network operations.
2. Choose efficient algorithms and data structures.
3. Reduce unnecessary CPU operations.
4. Reduce memory allocation and data copying.
5. Optimize repeated execution paths.
6. Apply micro-optimizations only when profiling demonstrates a meaningful benefit.

**Never sacrifice readability for negligible performance gains. Never sacrifice correctness for speed.**
