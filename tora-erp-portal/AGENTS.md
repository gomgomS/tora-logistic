# AGENTS.md — Rules for AI Coding Assistants

SLAPZ (`slapz102`) is a Flask + MongoDB boilerplate built on a custom MVC-style
layered pattern. This document is the single source of truth for how code must
be written here. **Follow the existing architecture and conventions exactly —
do not invent new patterns, layers, or utilities.**

The golden rule: **when building anything new, copy `slapz102_modules/sample/`
and adapt it.** The sample module is the canonical reference implementation.

---

## 1. Architecture — the request flow (NEVER change the layering)

```
browser
  │
  ▼
server.py                      registers blueprints (no business logic here)
  │
  ▼
slapz102_modules/<feature>/<feature>_blueprint.py     ROUTES only
  │                                                    try/except -> 500
  ▼
slapz102_modules/view/<feature>/view_<feature>.py     REQUEST/RESPONSE glue:
  │                                                    sanitize input, call proc,
  ▼                                                    render template / redirect
slapz102_modules/<feature>/<feature>_proc.py          BUSINESS LOGIC + DB access
  │
  ▼
slapz102_core/database.py  +  slapz102_core/model.py  framework core
  │
  ▼
MongoDB (via pymongo)
```

| Layer | File | May do | Must NOT do |
|---|---|---|---|
| Entrypoint | `server.py` | import + register blueprints, `app.run` | business logic, DB access |
| Blueprint | `<feature>_blueprint.py` | declare routes, delegate to view, catch exceptions | DB access, `render_template` |
| View | `view_<feature>.py` | read request, sanitize, call proc, render/redirect | business logic, direct DB queries |
| Proc | `<feature>_proc.py` | ALL business logic and DB access | importing Flask `request`/`session` at module level, defining routes |
| Core | `slapz102_core/*` | framework machinery | feature-specific logic |

## 2. File naming (MANDATORY)

```
slapz102_modules/<feature>/<feature>_proc.py          # business logic
slapz102_modules/<feature>/<feature>_blueprint.py     # routes
slapz102_modules/view/<feature>/view_<feature>.py     # render logic
templates/<feature>.html                              # Jinja2 templates
```

- One folder per feature under `slapz102_modules/`, one matching folder under
  `slapz102_modules/view/`.
- Views for a feature live ONLY in `view/<feature>/`, never next to the proc.
- Never rename the framework folders: `slapz102_core`, `slapz102_modules`,
  `slapz102_settings`, `slapz102_stdlib`, `slapz102_storage`.

## 3. Every Python file starts with the sys.path header (MANDATORY)

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")
```

- Imports between modules use these paths, e.g.
  `from sample.sample_proc import sample_proc` and
  `from view.sample import view_sample`.
- **Relative imports are forbidden** (`from ..x import y` never works here).

## 4. Code style (match the existing code exactly)

- **Closing comments are mandatory** on every block:

```python
if x:
    pass
# end if

for i in items:
    pass
# end for

def method():
    pass
# end def

class MyClass:
    pass
# end class
```

(`try/except` blocks close with `# end try`.)

- No f-strings — build strings by concatenation, like the rest of the codebase.
- Compare to `None` with `== None` / `!= None`, as the existing code does.
- Keep lines simple and explicit; match the surrounding density of comments.
- Proc classes follow this exact shape:

```python
class sample_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def
```

## 5. Database rules (MANDATORY — this is a schema-first framework)

1. **Register the collection first** in `slapz102_core/model.py` inside the
   `db` dict, with an empty default for every field. Collection names start
   with `db_`. Do NOT declare the framework-managed fields
   (`pkey`, `ipkey`, `rec_timestamp`, `rec_timestamp_str`, `is_deleted`) —
   `database.new()` adds them automatically.
2. **Create records only through the model**:

```python
rec = database.new(self.mgdDB, "db_sample_item")
rec.put("title", title)        # unknown keys raise ValueError — by design
rec.insert()
```

3. **Read via the collection handle**: `self.mgdDB.db_sample_item.find(...)`,
   `find_one(...)`, `.sort(...)`. Always project `{"_id": 0}` in find queries
   for templates.
4. **Updates go through the handle**, not the model:
   `update_one(query, {"$set": {...}})`.
5. **Soft delete only** — set `is_deleted: True`; every query filters
   `{"is_deleted": False}`. Never physically remove documents.
6. **Never drop or rename collections**, and never remove fields from an
   existing schema in `model.py` — additions only (backward compatible).
7. PyMongo 4 API only (`insert_one`, `update_one`, `delete_many`,
   `find_one_and_update`). The legacy `remove()`/`update()` collection methods
   do not exist in PyMongo 4.

## 6. Input handling (MANDATORY)

Every value that comes from a user must pass through the sanitizer before it
reaches a proc:

```python
params = sanitize.clean_html_dic(request.form.to_dict())
```

- Import as `from slapz102_stdlib import sanitize`.
- For query strings: `sanitize.clean_html_dic(request.args.to_dict())`.
- For rich HTML (WYSIWYG) content use `sanitize.clean_rich_html(value)`.
- Never call `html.escape` directly from a view or proc — use the stdlib.

## 6b. CSRF (MANDATORY on every POST form)

- Templates: every `<form method="post">` contains
  `<input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">`
  (the view passes `csrf_token` via the data dict).
- Views: the first thing a POST handler does is validate:

```python
from slapz102_stdlib import csrf

if not csrf.validate():
    return redirect(url_for("sample_blueprint.index", error="Invalid session, please try again"))
# end if
```

## 7. Error handling (MANDATORY)

Blueprint routes wrap their call:

```python
try:
    return view_sample.html_index()
except Exception as e:
    print(traceback.format_exc())
    return "An error occurred", 500
# end try
```

Do not swallow exceptions silently and do not leak tracebacks to the user.

## 8. Configuration

- `slapz102_core/config.py` holds the project's unique values and is
  **gitignored**; `slapz102_core/config_sample.py` is the committed template.
  Never commit a real `config.py`, and never move unique values elsewhere.
- Values can also be overridden by environment variables (`FLASK_SECRET_KEY`,
  `MONGO_URI`, `MONGO_DB_NAME`, `PUBLIC_SITE_URL`, `SITE_NAME`,
  `TZ_OFFSET_HOURS`, `PORT`).
- Access config as `from slapz102_core import config` → `config.mainDB`,
  `config.G_SITE_NAME`, ...
- **Never hardcode** URLs, credentials, DB names, or secrets in a module.
  If a new setting is needed, add an env-backed constant to both
  `config.py` and `config_sample.py`.

## 9. Frontend rules

- Templates extend `templates/base.html` (blocks: `title`, `og_title`,
  `og_description`, `content`). Data is passed as a single `data` dict.
- Styling is Tailwind CSS v4: edit `static/v2/input.css` (tokens + components),
  then rebuild with `npm run build:css` (or `npm run dev:css` to watch).
- **Never edit `static/v2/app.output.css`** — it is generated.
- Brand colors/design tokens live in the `@theme` block of `input.css`
  (`primary`, `light`, `mute`, `line`, `danger` + Archivo / IBM Plex Mono).
- Do not introduce other CSS frameworks, bundlers, or JS build steps. Node is
  used ONLY for the Tailwind build.

## 10. Dependencies and tests

- Python deps: only Flask (>=3) and PyMongo (>=4). If a new package is truly
  required, add it to `requirements.txt` with a pinned range and say so in
  the PR/commit description. Dev-only tools (pytest) go in
  `requirements-dev.txt`.
- `tests/` holds pytest tests that run against the scratch database
  `slapz_test`. Never break the suite — run `python3 -m pytest tests/`
  before considering work finished.
- Do not add task queues, ORMs, migration tools, or "modernization" layers.
  This framework is intentionally minimal.

## 11. When adding a new feature module — checklist

1. Add the collection schema to `model.py` (`db_<name>`), if needed.
2. Create `slapz102_modules/<feature>/` with `<feature>_proc.py` and
   `<feature>_blueprint.py`.
3. Create `slapz102_modules/view/<feature>/view_<feature>.py`.
4. Create `templates/<feature>.html` extending `base.html`.
5. Register the blueprint in `server.py` (import + `app.register_blueprint`).
6. If new CSS classes are needed: tokens/components in `input.css`, then
   rebuild the output CSS.
7. Add/extend tests in `tests/` for the new flow, then run
   `python3 -m pytest tests/ -v` (all tests must pass).
8. Verify: server starts, the new route renders, POST inputs are sanitized,
   CSRF validates, and records appear in MongoDB.

## 12. Absolutely do NOT

- Do not refactor `slapz102_core/` (config, database, model, helper) or
  `slapz102_stdlib/` — extend by adding, not by rewriting.
- Do not rename existing classes, methods, fields, or response keys.
- Do not create utility modules that duplicate `slapz102_stdlib`
  (`sanitize`, `idgen`).
- Do not use relative imports, f-strings, or type annotations in existing
  files that don't already have them.
- Do not commit `.env` files, credentials, `slapz102_core/config.py`, logs,
  or `static/upload/` content.
- Do not remove the closing comments (`# end ...`) — they are part of the
  house style.
- Do not switch the app to Application factories, Blueprints-with-prefix
  reorganization, class-based views, or any other restructuring. The pattern
  is the product.
