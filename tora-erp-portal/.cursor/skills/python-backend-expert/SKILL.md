---
name: python-backend-expert
description: >-
  House rules for the TORA ERP portal, built on the SLAPZ (slapz102) Flask +
  MongoDB framework: blueprint/view/proc layering, schema-first models,
  sanitize + CSRF, Flask-Login, closing-comment code style, and pytest. Use
  for any Python, Flask, Jinja2, MongoDB/PyMongo, or Tailwind work in this
  repo, including new feature modules, routes, API endpoints, collections,
  queries, templates, and tests.
---

# Python Backend Expert — SLAPZ (slapz102)

The TORA ERP portal runs on SLAPZ, a Flask + MongoDB boilerplate with a
custom layered MVC pattern. **Follow the existing architecture and conventions
exactly. Do not invent new patterns, layers, or utilities.**

Golden rule: **when building anything new, copy `slapz102_modules/sample/`
and adapt it.** It is the canonical reference. For authenticated ERP screens,
`slapz102_modules/contacts/` is the reference for the same pattern with
Flask-Login.

## Request flow (NEVER change the layering)

```
browser
  -> server.py                                     registers blueprints only
  -> slapz102_modules/<feature>/<feature>_blueprint.py   ROUTES, try/except -> 500
  -> slapz102_modules/view/<feature>/view_<feature>.py   sanitize, CSRF, auth,
                                                         call proc, render/redirect
  -> slapz102_modules/<feature>/<feature>_proc.py        BUSINESS LOGIC + DB access
  -> slapz102_core/database.py + slapz102_core/model.py  framework core
  -> MongoDB (PyMongo 4)
```

| Layer | May do | Must NOT do |
|---|---|---|
| `server.py` | import + register blueprints, Flask-Login setup, `app.run` | business logic, DB access |
| `<feature>_blueprint.py` | declare routes, delegate to view, catch exceptions | DB access, `render_template` |
| `view_<feature>.py` | read request, sanitize, validate CSRF, `@login_required`, call proc, render/redirect/`jsonify` | business logic, direct DB queries |
| `<feature>_proc.py` | ALL business logic and DB access | importing Flask `request`/`session`, defining routes |
| `slapz102_core/*` | framework machinery | feature-specific logic |

## File naming (MANDATORY)

```
slapz102_modules/<feature>/<feature>_proc.py
slapz102_modules/<feature>/<feature>_blueprint.py
slapz102_modules/view/<feature>/view_<feature>.py
templates/<feature>.html
```

- Views live ONLY in `slapz102_modules/view/<feature>/`, never next to the proc.
- Never rename the framework folders: `slapz102_core`, `slapz102_modules`,
  `slapz102_settings`, `slapz102_stdlib`, `slapz102_storage`.

## Every Python file starts with the sys.path header (MANDATORY)

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")
```

Import through these paths (`from sample.sample_proc import sample_proc`,
`from view.sample import view_sample`). **Relative imports are forbidden.**

## Code style (match the existing code exactly)

- **Closing comments on every block**: `# end if`, `# end for`, `# end while`,
  `# end def`, `# end class`, `# end try`, `# end with`.
- No f-strings; build strings by concatenation.
- Compare to `None` with `== None` / `!= None`.
- No type annotations in files that don't already have them.
- Proc methods return result dicts: `{"status": "SUCCESS" | "ERROR", "desc": "..."}`.
- User-facing messages in ERP modules are Indonesian (for example
  `"Terjadi kesalahan"`, `"Sesi tidak valid, coba lagi"`); the `sample`
  module stays English. Match the module you are editing.

## Non-negotiables

1. **Schema first**: register every collection in `slapz102_core/model.py`
   before use; create records only via `database.new()` + `put()` + `insert()`.
2. **Soft delete only**: `is_deleted: True`; every query filters
   `{"is_deleted": False}`.
3. **Sanitize all user input**: `sanitize.clean_html_dic(request.form.to_dict())`
   or `request.args.to_dict()` before it reaches a proc.
4. **CSRF on every POST**: the first line of a POST view is `csrf.validate()`;
   every `<form method="post">` carries `{{ data.csrf_token }}`.
5. **Auth on ERP views**: every ERP view function has `@login_required`
   (or `@access_required(area, action)` once the module has an access area)
   and passes `current_user` in `data`.
6. **Blueprint try/except**: log `traceback.format_exc()`, return a generic
   500; never leak tracebacks.
7. **No hardcoded config**: read from `slapz102_core/config.py`; new settings
   get an env-backed constant in both `config.py` and `config_sample.py`.

## Query and logic style (readable AND fast)

- **Reads**: clean inputs, build `query` one `if` at a time starting from
  `{"is_deleted": False}`, then ONE `find` with projection + sort + `.limit()`,
  then one loop to shape the output. Fixed names: `query`, `projection`,
  `update`, `recs`, `rec`, `out`.
- **Logic**: clean, then guard clauses that return the ERROR dict, then
  collect changes into one `update` dict, then one write. Use constants
  instead of magic strings, and `(value, err)` helpers.
- **Performance**: no queries inside loops (`$in` / `update_many`), project
  away unused fields (`tracking_logs` on lists), existence checks fetch only
  `_id`, group counts use one `$group`, guarded updates use `matched_count`,
  `set` for membership, and every new filter/sort is backed by an index.
  Propose the index; don't add setup code without asking.
- **Pagination is server-side only**: `slapz102_stdlib/paginate.py` for page
  math, one `count_documents` + one `find(...).skip().limit()` in the proc
  with an `_id` tiebreaker in the sort, and `templates/_pagination.html` for
  the controls. Never send all rows to the browser.
- **Default list table** (reference: `templates/contacts.html`):
  `<table class="app-list" data-table-key="<feature>">`, every data column
  `<th>` has `data-key` or `data-col` plus a default `data-width` (px), and
  the last `<th class="app-list-optional">` is the filler.
  `static/v2/app-list.js` (loaded by `app_base.html`) makes the columns
  resizable and saves the widths per browser; call `AppList.refresh(table)`
  after hiding or showing columns.
- **Record forms** (reference: `templates/contact_form.html`): split layout,
  form pane left (`app-split` > `app-form-pane` > `app-form-sheet`) and the
  shared activity log right (`_record_log.html`). Every record module writes
  CREATE / CHANGE entries through `record_log_proc`; never build a
  per-module log collection.

Details and rationale:
- Flask layering, auth, CSRF, config, frontend, deps, tests, logic style:
  [references/flask-guidelines.md](references/flask-guidelines.md)
- Schema registry, model API, queries, updates, counters, references,
  query style, performance rules, indexes:
  [references/mongodb-patterns.md](references/mongodb-patterns.md)
- Server-side pagination (helper, proc, view, template, tests):
  [references/pagination.md](references/pagination.md)
- Activity log beside record forms (Log catatan, create/change tracking) for
  any module: [references/record-log.md](references/record-log.md)
- Hak akses per area (Tidak ada akses / Hanya lihat / ... / Akses penuh),
  `@access_required`, hiding actions, user-management guards:
  [references/access-control.md](references/access-control.md)

## New feature module checklist

```
- [ ] 1. Add the collection schema `db_<name>` to slapz102_core/model.py (if needed)
- [ ] 2. Create slapz102_modules/<feature>/<feature>_proc.py
- [ ] 3. Create slapz102_modules/<feature>/<feature>_blueprint.py
- [ ] 4. Create slapz102_modules/view/<feature>/view_<feature>.py
- [ ] 5. Create templates/<feature>.html (ERP pages extend erp_base.html)
- [ ] 6. Register the blueprint in server.py (import + app.register_blueprint)
- [ ] 7. New CSS: edit static/v2/input.css, then `npm run build:css`
- [ ] 8. Add tests in tests/, run `python3 -m pytest tests/ -v` (all must pass)
- [ ] 9. Verify: server starts, route renders, inputs sanitized, CSRF
         validates, login enforced, records appear in MongoDB
```

Worked examples:
- Full blueprint + view + proc + template + test:
  [examples/flask-api.md](examples/flask-api.md)
- Common query and update recipes, plus readable-and-fast before/after pairs:
  [examples/mongodb-query.md](examples/mongodb-query.md)

## Direct data changes

When the user asks to inject, seed, import, or bulk-fix data, follow the
`db-data-injection` skill: give a mongosh script for the user to run, with
relationship checks and cascading updates. Never write to the database
yourself.

## Absolutely do NOT

- Refactor `slapz102_core/` or `slapz102_stdlib/`; extend by adding only.
- Rename existing classes, methods, fields, routes, or response keys.
- Create utilities that duplicate `slapz102_stdlib` (`sanitize`, `csrf`, `idgen`, `paginate`).
- Use relative imports, f-strings, or remove `# end ...` comments.
- Drop/rename collections or remove fields from an existing schema.
- Commit `.env`, credentials, `slapz102_core/config.py`, logs, or
  `static/upload/` content.
- Edit `static/v2/app.output.css` (generated).
- Add ORMs, task queues, migration tools, application factories, class-based
  views, other CSS frameworks, or JS bundlers. The pattern is the product.
