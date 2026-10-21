# SLAPZ Framework (`slapz102`)

A **Flask + MongoDB boilerplate** built on a custom, layered MVC-style pattern.
Clone it, install two dependencies, point it at MongoDB, and start building —
the framework ships with a complete, working **sample module** that shows every
convention you need to follow.

> **Building something new here?** Read [`AGENTS.md`](AGENTS.md) first — it is
> the rulebook for humans *and* AI assistants working on this codebase.

---

## Table of contents

1. [What's inside](#whats-inside)
2. [Requirements](#requirements)
3. [Quick start](#quick-start)
4. [Configuration](#configuration)
5. [Architecture — how a request flows](#architecture--how-a-request-flows)
6. [The sample module (reference implementation)](#the-sample-module-reference-implementation)
7. [Working with `model.py` (the schema registry)](#working-with-modelpy-the-schema-registry)
8. [stdlib & core helpers](#stdlib--core-helpers)
9. [Security built into the framework](#security-built-into-the-framework)
10. [Templates & CSS](#templates--css)
11. [Tests](#tests)
12. [Adding a new feature module](#adding-a-new-feature-module)
13. [Conventions cheat-sheet](#conventions-cheat-sheet)
14. [Quality assessment](#quality-assessment)
15. [Troubleshooting](#troubleshooting)

---

## What's inside

- **Layered architecture**: `blueprint → view → proc → model/database` — routes,
  rendering, and business logic are always separated.
- **Schema-first MongoDB layer** (`slapz102_core/model.py`): every collection is
  declared with its full field list; records are created through a model that
  rejects undeclared fields.
- **Auto-managed record fields**: every record gets `pkey`, `ipkey`,
  `rec_timestamp`, `rec_timestamp_str`, `is_deleted` automatically.
- **Input sanitization** built in (`slapz102_stdlib/sanitize.py`).
- **CSRF protection** built in (`slapz102_stdlib/csrf.py`) — session token on
  every POST form, zero extra dependencies.
- **Secret-key guard** — the app refuses to serve via a WSGI server while the
  sample Flask secret is unchanged.
- **Seed-on-boot sample module**: list / create / detail / soft-delete CRUD
  against MongoDB, wired end to end.
- **Tailwind CSS v4** design system with a small token set
  (Archivo + IBM Plex Mono, monochrome).
- **JSON API response envelope** (`slapz102_core/helper.py`) ready for API work.

## Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.8 (tested on 3.11 & 3.13) | |
| MongoDB | ≥ 4.4, running locally or reachable via URI | default `mongodb://127.0.0.1:27017/` |
| Flask | ≥ 3.0 | from `requirements.txt` |
| PyMongo | ≥ 4.6 | from `requirements.txt` |
| Node.js + npm | any recent | **optional** — only to rebuild the CSS bundle |

## Quick start

```bash
# 1. clone (or copy) the boilerplate
git clone <your-repo-url> my-project && cd my-project

# 2. create your local config (config.py is gitignored)
cp slapz102_core/config_sample.py slapz102_core/config.py

# 3. virtual environment + dependencies
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. make sure MongoDB is running
mongod                            # or: systemctl start mongod

# 5. run the dev server
./start.sh                        # or: python3 server.py

# 6. open the sample app
# http://localhost:5004
```

You should see the **Sample Items** page. Submit the form — the item is
sanitized, written to MongoDB through the model layer, and listed back with its
`pkey` and creation timestamp. That round-trip exercises the whole framework.

## Configuration

**`slapz102_core/config.py` holds the unique values of YOUR project and is
gitignored.** Each project starts from the committed template:

```bash
cp slapz102_core/config_sample.py slapz102_core/config.py
```

Edit `config.py` directly, or override any value with an environment variable
(`os.environ.get(...)` with the config value as default):

| Value | Env override | Sample default | Purpose |
|---|---|---|---|
| `G_FLASK_SECRET` | `FLASK_SECRET_KEY` | `CHANGE-ME-BEFORE-DEPLOY` | Flask session signing — **generate a unique one per project** |
| `mainDB` / `mainDB_string` | `MONGO_DB_NAME` / `MONGO_URI` | `slapz` / `mongodb://127.0.0.1:27017/` | MongoDB database (URI without the db name) |
| `G_PUBLIC_SITE_URL` | `PUBLIC_SITE_URL` | `http://localhost:5004` | Absolute base URL for Open Graph/share links |
| `G_SITE_NAME` | `SITE_NAME` | `SLAPZ Boilerplate` | Brand name used by templates |
| `JKTA_TZ` | `TZ_OFFSET_HOURS` | `7` | Hours added to UTC for `rec_timestamp` fields |
| — | `PORT` | `5004` | Dev server port |

Generate a secret key:

```bash
python3 -c "import os; print(os.urandom(24).hex())"
```

> **Safety guard**: when the app is served by a real WSGI server (imported as a
> module, not run via `python3 server.py` / `./start.sh`), it **refuses to
> start** while `G_FLASK_SECRET` is still the sample value.

Inside the code, always read config through the module — never hardcode:

```python
from slapz102_core import config

config.mainDB           # database name
config.G_SITE_NAME      # brand name
config.G_PUBLIC_SITE_URL
```

## Architecture — how a request flows

```
browser
  │
  ▼
server.py                       imports + registers blueprints (nothing else)
  │
  ▼
slapz102_modules/<feature>/<feature>_blueprint.py    ROUTES — try/except → 500
  │
  ▼
slapz102_modules/view/<feature>/view_<feature>.py    sanitize input, call proc,
  │                                                  render template / redirect
  ▼
slapz102_modules/<feature>/<feature>_proc.py         ALL business logic + DB
  │
  ▼
slapz102_core/database.py + slapz102_core/model.py   connection + schema/records
  │
  ▼
MongoDB
```

### Directory map

```
.
├── server.py                  # entrypoint — blueprint registration only
├── start.sh                   # dev launcher (flask run)
├── requirements.txt           # Flask + PyMongo
├── requirements-dev.txt       # pytest (dev only)
├── package.json               # Node — ONLY for the Tailwind CSS build
├── tests/                     # pytest suite for the sample module
│
├── slapz102_core/             # FRAMEWORK CORE — do not refactor
│   ├── config.py              # YOUR local values (gitignored)
│   ├── config_sample.py       # committed template → copy to config.py
│   ├── database.py            # Mongo connection + record factory (new/load)
│   ├── model.py               # schema registry `db` + `mongo_model` class
│   └── helper.py              # response_msg JSON envelope
│
├── slapz102_modules/          # ALL feature code lives here
│   ├── sample/                # ← the reference module (copy me)
│   │   ├── sample_proc.py     # business logic
│   │   └── sample_blueprint.py# routes
│   └── view/
│       └── sample/
│           └── view_sample.py # render logic
│
├── slapz102_stdlib/           # utilities — check here BEFORE writing a helper
│   ├── sanitize.py            # clean_html_dic / clean_html / clean_rich_html
│   ├── csrf.py                # get_token / validate (all POST forms)
│   └── idgen.py               # _get_api_call_id()
│
├── slapz102_settings/         # reserved extension point (empty, on sys.path)
├── slapz102_storage/          # reserved extension point (empty, on sys.path)
│
├── templates/                 # Jinja2 (base.html + one file per page)
└── static/
    ├── brand/                 # favicon.svg, og-default.jpg (placeholders)
    ├── upload/                # runtime uploads (gitignored)
    └── v2/                    # Tailwind v4: input.css → app.output.css
```

## The sample module (reference implementation)

Four small files implement a complete feature. When you start a new project,
**copy this module, rename it, delete what you don't need.**

**1. `slapz102_modules/sample/sample_blueprint.py`** — routes only:

```python
sample_blueprint = Blueprint("sample_blueprint", __name__)

@sample_blueprint.route("/", methods=["GET"])
def index():
    try:
        return view_sample.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
```

**2. `slapz102_modules/view/sample/view_sample.py`** — request glue:

```python
def html_create():
    if not csrf.validate():
        return redirect(url_for("sample_blueprint.index", error="Invalid session, please try again"))
    # end if
    # every user input passes through the sanitizer before reaching a proc
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = sample_proc()
    result = proc.create_item(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("sample_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("sample_blueprint.index"))
# end def
```

**3. `slapz102_modules/sample/sample_proc.py`** — business logic:

```python
class sample_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def list_items(self):
        recs = list(self.mgdDB.db_sample_item.find(
            {"is_deleted": False},     # soft-delete filter, always
            {"_id": 0}
        ).sort("rec_timestamp", -1))
        return recs
    # end def

    def create_item(self, params):
        title = (params.get("title") or "").strip()
        if title == "":
            return {"status": "ERROR", "desc": "Title is required"}
        # end if
        rec = database.new(self.mgdDB, "db_sample_item")
        rec.put("slug", self._unique_slug(_slugify(title)))
        rec.put("title", title)
        rec.put("body", (params.get("body") or "").strip())
        rec.put("order", 0)
        rec.put("status", "PUBLISHED")
        rec.insert()
        return {"status": "SUCCESS", "desc": "Item created"}
    # end def
```

**4. `templates/index.html`** — extends `base.html`, renders the `data` dict.

Routes exposed by the sample:

| Method | Path | Action |
|---|---|---|
| GET | `/` | list items + create form |
| POST | `/sample/create` | sanitize → create → redirect |
| GET | `/sample/<slug>` | item detail (404 if missing/deleted) |
| POST | `/sample/delete/<slug>` | soft delete (`is_deleted: True`) → redirect |
| GET | `/favicon.ico` | serves `static/brand/favicon.svg` |

## Working with `model.py` (the schema registry)

`slapz102_core/model.py` has two parts: the **`mongo_model` class** and the
**`db` schema dict**. This is the heart of the framework — MongoDB is
schema-less, so the schema lives here instead.

### Registering a collection

Every collection must be declared with an empty default for **every** field
before use:

```python
db = {
    ...
    "db_sample_item": {
        "slug": "",
        "title": "",
        "body": "",
        "order": 0,
        "status": "PUBLISHED"
    }
}
```

### Creating a record — `database.new()` + `put()` + `insert()`

```python
from slapz102_core import database

rec = database.new(self.mgdDB, "db_sample_item")
rec.put("title", "Hello")     # key must exist in the schema...
rec.put("oops", "x")          # ...otherwise: ValueError SETTING_NON_EXISTING_FIELD
rec.insert()                  # writes to MongoDB
```

`database.new()` automatically adds the framework-managed fields:

| Field | Meaning |
|---|---|
| `pkey` | primary key: `<ObjectId>-<random>-<counter>-<ms>` |
| `ipkey` | the plain ObjectId string |
| `rec_timestamp` | creation time in **milliseconds** (UTC + `JKTA_TZ`) |
| `rec_timestamp_str` | human-readable `YYYY-MM-DD HH:MM:SS` |
| `is_deleted` | soft-delete flag (starts `False`) |

The uniqueness counter behind `pkey` is kept in the `db_unique_counter`
collection (atomic `find_one_and_update` + upsert).

### Reading, updating, deleting

```python
# READ — collection handle, always filter soft-deleted rows
self.mgdDB.db_sample_item.find_one(
    {"slug": slug, "is_deleted": False}, {"_id": 0}
)

# UPDATE — partial updates go through the handle
self.mgdDB.db_sample_item.update_one(
    {"slug": slug},
    {"$set": {"is_deleted": True}}       # soft delete
)
```

The `mongo_model` class also exposes `get()`, `update(query)` (writes the whole
record back with `$set`) and `delete(query)` (`delete_many`) — but the
established convention in this codebase is: **create via the model, read/update
via the collection handle, delete = soft delete.**

### Loading an empty record

`database.load(db_handle, "db_sample_item")` returns an empty `mongo_model`
for the table — useful when you only need the field lookup.

## stdlib & core helpers

**`slapz102_stdlib/sanitize.py`** — use for EVERY user input:

```python
from slapz102_stdlib import sanitize

sanitize.clean_html_dic(request.form.to_dict())  # dict of strings (forms/query)
sanitize.clean_html(user_string)                 # single string
sanitize.clean_rich_html(html_from_editor)       # WYSIWYG content — whitelist of
                                                 # safe tags/attrs, strips scripts
```

**`slapz102_stdlib/idgen.py`** — collision-resistant call IDs:

```python
from slapz102_stdlib import idgen
idgen._get_api_call_id()   # "API_CALL_<epoch+hms>_<random>"
```

**`slapz102_core/helper.py`** — JSON API response envelope. If you add API
endpoints (e.g. a blueprint returning JSON), keep this exact shape:

```python
from slapz102_core import helper

resp = helper.response_msg_factory(
    status="SUCCESS",
    desc="Item created",
    data={"slug": "hello"}
)
return jsonify(resp.get())
# {
#   "id": "API_CALL_...", "message_id": "API_CALL_...",
#   "status": "SUCCESS", "message_action": "SUCCESS",
#   "desc": "Item created", "message_desc": "Item created",
#   "status_code": "xxxx",
#   "data": {...}, "message_data": {...}
# }
```

Both key styles (`status`/`desc`/`data` **and** `message_action`/
`message_desc`/`message_data`) are always kept in sync by the helper — never
change these response keys.

## Security built into the framework

- **Input sanitization** — `sanitize.clean_html_dic()` on every user input
  (see above).
- **CSRF protection** — `slapz102_stdlib/csrf.py`, no extra dependencies.
  Every POST form carries the session token, and every POST view validates it:

```html
<!-- in the template, inside every <form method="post"> -->
<input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
```

```python
# at the top of the view function handling the POST
from slapz102_stdlib import csrf

if not csrf.validate():
    return redirect(url_for("sample_blueprint.index", error="Invalid session, please try again"))
# end if
```

- **Session cookie hardening** — `SESSION_COOKIE_HTTPONLY` and
  `SESSION_COOKIE_SAMESITE="Lax"` are set in `server.py`.
- **Secret-key guard** — a WSGI server import refuses to start while
  `G_FLASK_SECRET` is still the sample value.

## Tests

```bash
pip install -r requirements-dev.txt      # pytest (dev only)
python3 -m pytest tests/ -v
```

The suite runs against a scratch database (`slapz_test`) and covers the whole
sample flow: rendering, CSRF rejection, create, XSS sanitization, validation,
detail pages, and soft delete.

## Templates & CSS

- Pages extend `templates/base.html`: blocks `title`, `og_title`,
  `og_description`, `content`; data arrives as one `data` dict.
- **Tailwind v4**, source at `static/v2/input.css`:

```bash
npm install          # once (Node used ONLY for CSS)
npm run dev:css      # watch mode while developing
npm run build:css    # one-off build → static/v2/app.output.css
```

- Edit **`input.css` only** (tokens in the `@theme` block, components in
  `@layer`) — `app.output.css` is generated, never hand-edited.
- Brand assets: replace `static/brand/favicon.svg` and
  `static/brand/og-default.jpg` with your own.

## Adding a new feature module

1. **Schema** — add the collection to `model.py` if needed (`db_<name>`).
2. **Proc** — `slapz102_modules/<feature>/<feature>_proc.py` (copy
   `sample_proc.py`).
3. **Blueprint** — `slapz102_modules/<feature>/<feature>_blueprint.py`
   (copy `sample_blueprint.py`).
4. **View** — `slapz102_modules/view/<feature>/view_<feature>.py`
   (copy `view_sample.py`).
5. **Template** — `templates/<feature>.html` extending `base.html`
   (remember the hidden `csrf_token` input in every POST form).
6. **Register** in `server.py`:

```python
from notes.notes_blueprint import notes_blueprint
app.register_blueprint(notes_blueprint, url_prefix="/")
```

7. **CSS** — add classes/tokens in `input.css`, rebuild with `npm run build:css`.
8. **Verify** — server starts, GET renders, POST sanitizes, data lands in Mongo.

## Conventions cheat-sheet

```python
# 1. sys.path header at the top of EVERY file
import sys
sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

# 2. sanitize every input
params = sanitize.clean_html_dic(request.form.to_dict())

# 3. every POST form carries the CSRF token and every POST view validates it
#    <input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
#    if not csrf.validate(): redirect with error

# 4. closing comments on every block
def anything():
    if x:
        pass
    # end if
# end def

# 5. no f-strings, no relative imports, `== None` comparisons
# 6. DB access only inside procs; blueprint routes only delegate to views
# 7. soft delete only; every query filters {"is_deleted": False}
```

## Quality assessment

Assessed by an AI code review (Claude) after the 2026-10 cleanup and hardening
round — kept here as an honest snapshot of where the framework stands.

**Overall: 8 / 10** as a personal/team boilerplate · 6.5 / 10 as a public framework

| Category | Score | Notes |
|---|---|---|
| Architecture & layering | 9/10 | blueprint → view → proc separation, enforced consistently; package imports and cwd-independent paths |
| Data layer design | 7/10 | schema registry, auto fields, soft delete; `mongo_model.update()`/`delete()` remain thin vs. the handle-update convention |
| Security | 8/10 | CSRF on all forms, sanitization everywhere, session hardening, secret guard; no auth sample yet |
| Developer experience | 8.5/10 | two pip deps, one-command run, working sample module, full docs |
| Maintainability & testing | 7/10 | pytest suite covers the sample flow; import-time DB handle and `print()` logging remain |
| Documentation | 9/10 | README + AGENTS.md cover setup, patterns, and AI rules |

**Known path to 9/10** (kept honest, in priority order):

1. Auth reference module (login/session against `db_user`)
2. Logger instead of `print(traceback...)` in blueprints
3. Resolve or document the `mongo_model.update()`/`delete()` API
4. CI workflow running the test suite + security headers

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ServerSelectionTimeoutError` on first request | MongoDB isn't running — start `mongod`, or set `MONGO_URI` |
| Page renders unstyled | `static/v2/app.output.css` missing — run `npm install && npm run build:css` |
| `ValueError: SETTING_NON_EXISTING_FIELD` | You called `rec.put()` with a key not declared in `model.py` — add it to the schema first |
| `RuntimeError: G_FLASK_SECRET is still the sample value` | Generate a secret (`python3 -c "import os; print(os.urandom(24).hex())"`) and set it in `slapz102_core/config.py` |
| Form submit redirects with "Invalid session" | The CSRF token is missing/stale — make sure the form includes the hidden `csrf_token` input |
| Port already in use | `PORT=5005 python3 server.py` |
| Changes to `input.css` not visible | You edited the generated file, or didn't rebuild — edit `input.css`, run `npm run build:css`, hard-refresh |
