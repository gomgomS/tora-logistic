# Pagination — server-side only

Every list page is paginated by the **backend**. MongoDB returns only the rows
of the requested page; the browser never receives the full collection and
never slices it in JavaScript.

Reference implementation: Kontak (`contacts_proc.page_contacts`,
`view_contacts.html_index`, `templates/contacts.html`).

## Building blocks

| Piece | File | Job |
|---|---|---|
| Page math | `slapz102_stdlib/paginate.py` | parse `page` / `per_page`, clamp, compute `offset`, range, page-number window |
| Query | `<feature>_proc.py` | `count_documents` + `find(...).sort(...).skip(offset).limit(per_page)` |
| Request | `view_<feature>.py` | `paginate.read_params(params)`, pass filters as `data["page_args"]` |
| Controls | `templates/_pagination.html` | `pager_compact` (control panel), `pager_bar` (below the list) |

`paginate.py` is pure (no Flask, no DB). Never duplicate its math in a proc or
template.

## Step by step

### 1. Proc: one count + one page query

```python
from slapz102_stdlib import paginate

def page_vehicles(self, ownership, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
    query = self._list_query(ownership, q)
    projection = {"plate_number": 1, "vehicle_type": 1, "ownership": 1, "vendor_name": 1}
    total = self.mgdDB.db_vehicle.count_documents(query)
    pager = paginate.build(total, page, per_page)
    recs = self.mgdDB.db_vehicle.find(query, projection).sort(
        [("plate_number", 1), ("_id", 1)]
    ).skip(pager["offset"]).limit(pager["per_page"])
    out = []
    for rec in recs:
        out.append(self._vehicle_public(rec))
    # end for
    pager["vehicles"] = out
    return pager
# end def
```

Rules:

- **Same `query` for count and find.** Build it once in a `_list_query()`
  helper so filters can never drift between the total and the rows.
- **Stable sort with an `_id` tiebreaker** (`[("name", 1), ("_id", 1)]`).
  Without it, rows with equal sort values can repeat or disappear across pages.
- **Projection** lists only the columns the page can show.
- **Clamp before querying.** `paginate.build()` moves `page=99` to the last
  page, so an out-of-range page still shows data instead of an empty table.
- Keep the old unpaged `list_*()` method if other code (APIs, exports) uses it.

### 2. View: read params, keep filters

```python
from slapz102_stdlib import paginate

params = sanitize.clean_html_dic(request.args.to_dict())
page, per_page = paginate.read_params(params)
pager = fleet_proc().page_vehicles(data["ownership"], data["q"], page, per_page)
data["vehicles"] = pager["vehicles"]
data["pager"] = pager
data["page_args"] = {"ownership": data["ownership"], "q": data["q"]}
```

`read_params` accepts only `paginate.PAGE_SIZES` (20 / 40 / 80 / 200), so a
request can never ask for an unbounded page.

### 3. Template: shared controls

```html
{% from "_pagination.html" import pager_compact, pager_bar %}

<div class="app-cp-right">
    {{ pager_compact(data.pager, "fleet_blueprint.index", data.page_args) }}
</div>
...
</table>
{{ pager_bar(data.pager, "fleet_blueprint.index", data.page_args) }}
```

- Links are plain GET URLs built from `page_args` + `page` + `per_page`.
  Empty filters and default values are left out of the URL.
- The search form carries `per_page` as a hidden input when it is not the
  default, so searching keeps the chosen page size.
- Changing a filter or search resets to page 1 (omit `page` from those links).

### 4. Tests

- Unit-test any new math in `tests/test_paginate.py` style (pure functions).
- Request test: `?page=99&per_page=999999` must return 200 with clamped
  values.

## Performance

- Add a compound index for the list's filter + sort: equality fields first,
  then the sort fields (`is_deleted, category, name, _id`). Propose it; don't
  add index setup code without asking.
- `count_documents` runs once per page load and uses the same index.
- `.skip()` cost grows with the offset. Numbered pages with `skip` are fine
  for master data lists (contacts, fleet, users, routes): small collections,
  users rarely jump past a few pages.
- For large or fast-growing collections (shipments, tracking logs), or an
  infinite "load more" list, use **range (keyset) paging** on the sort key
  instead of `skip`: `query["rec_timestamp"] = {"$lt": last_seen}` with the
  same sort + `limit`. See "Load more" in
  [../examples/mongodb-query.md](../examples/mongodb-query.md).
- Never load all rows and paginate in Python or JavaScript.

## Checklist

```
- [ ] _list_query() shared by count_documents and find
- [ ] paginate.build() used; per_page from read_params whitelist
- [ ] sort ends with ("_id", 1)
- [ ] explicit projection
- [ ] page_args passed; pager_compact + pager_bar rendered
- [ ] index proposed for filter + sort
- [ ] tests: clamp + whitelist + one page of results
```
