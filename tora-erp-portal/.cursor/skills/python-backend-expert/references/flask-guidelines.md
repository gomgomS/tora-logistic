# Flask Guidelines — SLAPZ (slapz102)

## Contents

1. Entrypoint (`server.py`)
2. Blueprint layer
3. View layer
4. Proc layer
5. Input sanitizing
6. CSRF
7. Authentication (Flask-Login)
8. Error handling
9. Configuration
10. Templates and frontend
11. Dependencies
12. Tests
13. Logic style (procs)

## 1. Entrypoint (`server.py`)

`server.py` only creates the app, wires Flask-Login, and registers blueprints.
Adding a feature means two lines here: one import, one registration.

```python
from shipments.shipments_blueprint import shipments_blueprint

app.register_blueprint(shipments_blueprint, url_prefix="/")
```

- ERP modules register with `url_prefix="/"` and declare full paths in their
  routes (`/contacts`, `/api/contacts`).
- `sample` stays registered under `/sample` as the reference implementation;
  never remove it.
- The Flask-Login `user_loader` delegates to `auth_proc().get_login_user()`.
  Do not move auth logic into `server.py`.

## 2. Blueprint layer — `<feature>_blueprint.py`

Does three things only: declares the route + method, delegates to a `view_*`
function, and catches exceptions.

- Blueprint name is `<feature>_blueprint`, and the variable has the same name:
  `contacts_blueprint = Blueprint("contacts_blueprint", __name__)`.
- One route function per endpoint; the body is always the try/except shape
  shown in section 8.
- HTML routes return a plain-text 500; JSON routes (`/api/...`) return a JSON
  body with a 500 status so the frontend can parse it.
- Imports: `sys`, `traceback`, `from flask import Blueprint`, and the view
  module (`from view.<feature> import view_<feature>`). No proc imports.

## 3. View layer — `view/<feature>/view_<feature>.py`

Request/response glue. A view function:

1. Is decorated with `@login_required` (ERP screens).
2. On POST, validates CSRF first.
3. Sanitizes input with `sanitize.clean_html_dic(...)`.
4. Instantiates the proc and calls it.
5. Builds a single `data` dict and calls `render_template(..., data=data)`, or
   redirects with `error=` / `success=` query params, or returns `jsonify(...)`.

Each view module has a `_base_data()` helper that returns the shared page
data (`site_name`, `csrf_token`, `og_image`, `og_url`, and for ERP pages
`sidebar_counts`). Copy it from an existing ERP view; do not invent a
global context processor.

Flash-style feedback goes through query params, not `flask.flash`:

```python
return redirect(url_for("contacts_blueprint.index", error=result.get("desc", "")))
```

and the view reads it back with
`data["form_error"] = (request.args.get("error") or "").strip()`.

Redirects to a user-supplied `next` URL must only accept same-site relative
paths (starts with `/`, does not start with `//`).

## 4. Proc layer — `<feature>/<feature>_proc.py`

All business logic and DB access. Class shape is fixed:

```python
class contacts_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def
# end class
```

- The class name is lowercase `<feature>_proc`.
- Methods take plain Python values or dicts (already sanitized params); they
  never touch `flask.request` or `flask.session`.
- Validation lives here and returns
  `{"status": "ERROR", "desc": "<message>"}`; success returns
  `{"status": "SUCCESS", "desc": "<message>", ...extra keys}`.
- Module-level constants (for example `CATEGORIES`, status names) live at the
  top of the proc file, and views import them from there.
- A proc may call another proc (for example `shipments_proc` using
  `contacts_proc().get_contacts_map(...)`); it must not call views.

## 5. Input sanitizing

```python
from slapz102_stdlib import sanitize

params = sanitize.clean_html_dic(request.form.to_dict())
params = sanitize.clean_html_dic(request.args.to_dict())
body = sanitize.clean_rich_html(raw_html)   # WYSIWYG content only
```

- Every user value goes through the sanitizer before it reaches a proc.
- Never call `html.escape` directly from a view or proc.
- Single values: `sanitize.clean_html(value)`.

## 6. CSRF (MANDATORY on every POST)

Template, inside every `<form method="post">`:

```html
<input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
```

View, as the first statement of every POST handler:

```python
from slapz102_stdlib import csrf

if not csrf.validate():
    return redirect(url_for("contacts_blueprint.index", error="Sesi tidak valid, coba lagi"))
# end if
```

JSON POST endpoints return `jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400`
instead of redirecting. `csrf.validate()` reads `request.form["csrf_token"]`,
so AJAX callers posting form data send it as a `csrf_token` field. For JSON
bodies or custom headers, extract the token yourself and call
`csrf.validate_token(sent)`.

## 7. Authentication (Flask-Login)

```python
from flask_login import login_required, current_user

@login_required
def html_index():
    data = _base_data()
    data["current_user"] = current_user
    ...
# end def
```

- Put `@login_required` on the **view** function, not on the blueprint route.
- Users live in `db_user`; `password` stores a werkzeug hash and `role` is
  `"superadmin"` or `"admin"`. Hashing and login checks live in `auth_proc`;
  reuse it instead of re-implementing.
- Public pages (tracking, login, sample) do not use `@login_required`.

## 8. Error handling

HTML route:

```python
@contacts_blueprint.route("/contacts", methods=["GET"])
def index():
    try:
        return view_contacts.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def
```

JSON route:

```python
except Exception as e:
    print(traceback.format_exc())
    return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
# end try
```

Never swallow exceptions silently and never send tracebacks to the client.
Expected failures (validation, not found) are returned as result dicts from
the proc, not raised.

## 9. Configuration

- `slapz102_core/config.py` holds the unique values and is **gitignored**;
  `slapz102_core/config_sample.py` is the committed template.
- Environment overrides: `FLASK_SECRET_KEY`, `MONGO_URI`, `MONGO_DB_NAME`,
  `PUBLIC_SITE_URL`, `SITE_NAME`, `TZ_OFFSET_HOURS`, `PORT`.
- Access as `from slapz102_core import config`, then `config.mainDB`,
  `config.G_SITE_NAME`, `config.G_PUBLIC_SITE_URL`, `config.G_HOME_PATH`.
- Never hardcode URLs, credentials, DB names, API keys, or secrets in a
  module. New setting = env-backed constant in both `config.py` and
  `config_sample.py`.
- `server.py` refuses to start outside development while the secret is still
  a sample value; do not weaken that check.

## 10. Templates and frontend

- Public pages extend `templates/base.html` (blocks: `title`, `og_title`,
  `og_description`, `content`).
- Authenticated ERP pages extend `templates/erp_base.html` (blocks: `title`,
  `topbar_title`, `erp_content`).
- Shared partials: `_ui.html` (macros), `_icons.html`, `_ai_chat.html`.
  Reuse their macros before writing new markup.
- Data is passed as a single `data` dict; templates read `data.<key>`.
- Styling is Tailwind CSS v4: edit `static/v2/input.css` (tokens in `@theme`,
  components below), then `npm run build:css` (or `npm run dev:css`).
- **Never edit `static/v2/app.output.css`**; it is generated.
- Brand tokens: `primary`, `light`, `mute`, `line`, `danger`, with Archivo /
  IBM Plex Mono fonts.
- No other CSS frameworks, bundlers, or JS build steps. Node is used ONLY for
  the Tailwind build.

## 11. Dependencies

Runtime (`requirements.txt`): Flask (>=3), Flask-Login (>=0.6.3), PyMongo
(>=4). Werkzeug, Jinja2, and bson come in transitively.

- A truly required new package goes into `requirements.txt` with a pinned
  range, and the commit/PR description says why.
- Dev-only tools (pytest) go into `requirements-dev.txt`.
- No ORMs, task queues, migration tools, or "modernization" layers.

## 12. Tests

- `tests/` holds pytest tests (`test_sample.py`, `test_logistics.py`).
- Tests set `os.environ["MONGO_DB_NAME"] = "slapz_test"` **before** importing
  `config`, and the fixture drops that scratch database, so local data is
  never touched.
- Use `server.app.test_client()`; extract the CSRF token from a rendered page
  before posting.
- Run `python3 -m pytest tests/ -v` before considering work finished. Never
  leave the suite broken.

## 13. Logic style (procs)

Business logic reads as a straight line: clean, check, act, return. The
shape below is how `shipments_proc`, `contacts_proc`, and `manifests_proc`
are written; new code follows it.

```python
def assign_driver(self, manifest_code, params, updated_by):
    driver_id = (params.get("driver_id") or "").strip()
    if driver_id == "":
        return {"status": "ERROR", "desc": "Sopir wajib dipilih"}
    # end if
    if updated_by == "" or updated_by == None:
        updated_by = "SYSTEM"
    # end if
    manifest = self.get_by_code(manifest_code)
    if manifest == None:
        return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
    # end if
    if manifest.get("status") != STATUS_PLANNED:
        return {"status": "ERROR", "desc": "Sopir hanya bisa diganti saat manifest masih direncanakan"}
    # end if
    update = {"driver_id": driver_id, "last_update": shipments_proc().now_str()}
    self.mgdDB.db_manifest.update_one(
        {"_id": ObjectId(manifest["id"])},
        {"$set": update}
    )
    return {"status": "SUCCESS", "desc": "Sopir diperbarui"}
# end def
```

**Readability rules**

1. **Clean first.** Every input on its own line at the top:
   `x = (params.get("x") or "").strip()`, plus `.upper()` for enums.
2. **Guard clauses, not nesting.** One rule per `if`, returning the ERROR dict
   immediately. The happy path stays at the lowest indentation.
3. **Defaults are explicit**: `if updated_by == "" or updated_by == None:`.
4. **Constants, not magic strings.** Statuses, categories, and limits are
   UPPERCASE module constants (`STATUS_PLANNED`, `SERVICE_TYPES`).
5. **Collect, then write once.** Build one `update` / `set_fields` dict (use
   `if/elif` to choose values), then make a single write.
6. **Helpers that can fail return `(value, err)`**; the caller does
   `if err != None: return err`. See `_order_fields` and `_place_fields`.
7. **Pure logic goes in module-level `_helper()` functions** (no DB, easy to
   test, like `_place_key`, `_city_from_regency`). DB work stays in proc methods.
8. **Split long procs with section bars** (`# ---- Reads ----`,
   `# ---- Writes ----`) and comment the business *reason* above tricky blocks.
9. **Short methods.** When a method passes about 40 lines or mixes two jobs,
   extract a `_private` method with a name that says what it decides.

**Performance rules (logic)**

1. **Cheap checks before DB checks.** Validate empty fields and whitelists
   before any query; reject bad input without touching MongoDB.
2. **Read each document once.** Keep the result in a variable and pass it
   along; never call `get_*()` twice for the same id in one request.
3. **Look up related documents in one batch** (`get_contacts_map(ids)`), not
   one `get_contact()` per id. Two ids is already a batch.
4. **No DB calls inside loops.** Loop to collect ids, query once with `$in`,
   loop again to map results with a dict.
5. **`set` for membership, dict for lookup.** `if code in seen_codes` on a
   `set` is instant; on a list it rescans every time.
6. **Let MongoDB filter.** Put conditions in `query` instead of fetching
   everything and skipping rows in Python. Keep Python filtering only for
   rules MongoDB cannot express cleanly (for example `_at_destination_hub`).
7. **Create a proc once per function**, before any loop: `cproc = contacts_proc()`.
8. **Compute fixed values once at module level** (constant lists, compiled
   regexes), not inside every call.
9. **Atomic over read-modify-write.** Counters use `$inc`, arrays use `$push`,
   state changes use a guarded filter. See "Performance rules" in
   [mongodb-patterns.md](mongodb-patterns.md).
