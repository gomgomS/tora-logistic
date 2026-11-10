---
name: tora-erp-backend
description: >-
  House rules for Python / Flask / MongoDB code in tora-erp-portal (SLAPZ
  slapz102): blueprint → view → proc layering, file header and closing
  comments, schema-first models, sanitize + CSRF, access levels, record log,
  server-side pagination, document numbers, URL naming, tests. Use when
  writing or changing any .py file, route, proc, collection, or test in
  tora-erp-portal/. Pair with tora-erp-ui (templates) and tora-erp-db-script
  (data the user runs).
---

# TORA ERP portal — backend rules

All paths below are inside `tora-erp-portal/`. **Copy the closest existing
module and adapt it; never invent a new pattern, layer, or utility.**

| Need | Copy |
|---|---|
| Document module (list, form, workflow, numbers, log) | `slapz102_modules/accounting/payments_proc.py` + `view/accounting/view_payments.py` |
| Bigger document with lines, taxes, journal | `accounting/accounting_proc.py` (Faktur / Nota Kredit, `MOVE_TYPES`) |
| Master data + log | `contacts/contacts_proc.py` + `view/contacts/view_contacts.py` |
| Config record (code key, Aktif switch) | `accounting_proc` Bagan Akun / Pajak sections |
| Tests | `tests/test_logistics.py` (`_seed`, `_login_as`, `_create_user`, `_invoice_payload`) |

## Layers (never change)

`<feature>_blueprint.py` routes only, each wrapped in `try/except` →
`print(traceback.format_exc())`, return `"Terjadi kesalahan", 500`.
`view/<feature>/view_<feature>.py` reads request, `sanitize.clean_html_dic(...)`,
`csrf.validate()` first on every POST, access guard, calls proc,
render / redirect / `jsonify`. `<feature>_proc.py` holds ALL business logic
and DB access, returns `{"status": "SUCCESS" | "ERROR", "desc": "..."}`.
No DB queries in views; no Flask `request` in procs. Views never import
another module's private `_helpers` — expose a public function instead.

## Every Python file

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")
```

- Closing comment on every block: `# end if/for/while/def/class/try/with`.
- No f-strings (concatenate), `== None` / `!= None`, no type annotations,
  no relative imports.
- User-facing text in Indonesian. Never mention the reference product the
  layouts come from.

## Data rules

- Register every collection in `slapz102_core/model.py` first (defaults for
  every field; additions only). Create via `database.new(db, "db_x")` +
  `put()` + `insert()`; read the id with `rec.get()["_id"]`.
- Soft delete only (`is_deleted: True`); every query starts from
  `{"is_deleted": False}`.
- Query style: build `query` one `if` at a time → ONE `find(query,
  projection).sort(...).limit()` → one loop into `out`. Guard clauses return
  the ERROR dict; collect one `update` dict; one write.
- Performance: no queries in loops (`$in`, `update_many`), projections on
  lists, existence checks fetch `_id` only, totals via one `$group`,
  state changes as guarded updates (`{"_id": .., "state": "DRAFT"}` +
  check `matched_count`), money via guarded `$inc` (`amount_residual >= x`).
- Counters: `db_code_counter` with `$max` seed then `find_one_and_update
  $inc` (see `accounting_proc.next_number`, `payments_proc._next_seq`).
- Never write to the real database yourself (scripts → tora-erp-db-script).

## Documents

- URL uses an integer `seq` (`/accounting/client-invoices/4`); masters use
  their stable code (`/accounting/accounts/41000010`).
- Number = prefix from Konfigurasi › Pengaturan (`accounting_proc.SEQUENCES`,
  with `collection`) + counter; new types get a row there.
- States: `DRAFT` editable with "create"; confirm / cancel / reset / pay need
  "update"; anything ever confirmed is never deleted (`posted_at` set).
- Helpers: `rupiah()`, `short_date()`, `today_iso()` from `accounting_proc`.

## URL naming

Path = navbar menu + page: Pelanggan → `client-*` (`client-invoices`,
`client-credit-notes`, `client-payments`), Vendor → `vendor-*`
(`vendor-bills`, ...). Endpoint names stay short; templates only use
`url_for`. Renaming a live path keeps a 301 (`view_accounting.LEGACY_SLUGS`).

## Access

`@access_required(area, action)` on every view (areas `users`, `contacts`,
`accounting`; actions `read` / `create` / `update` / `delete`; levels in
`auth_proc.ACCESS_SECTIONS`, labels in plain Indonesian, never "CRUD").
Templates hide buttons with `data.current_user.can(...)`; the server check
stays the real guard. Superadmin always has full access. User management
guards (never weaken): only a Superadmin touches Superadmin accounts; an
admin grants at most their own level; nobody changes their own role /
levels / status; own password change needs the current one; the current
account and the last Superadmin are never deleted or demoted.

## Record log (every detail page)

- Register the model in `record_log_proc.LOG_MODELS` (`collection`, `area`).
- Proc: `log_create` on create; `log_changes(model, id, old, new, LABELS,
  actor)` on update; `log_event` for actions (konfirmasi, bayar, aktif, sandi).
  `actor = actor_from_user(current_user)` from the view.
- `LABELS` cover **every field the form saves**, as people read them (names
  not ids, labels not codes, `short_date`, `rupiah`, "Ya"/"Tidak").
- Lines: per changed field per row (`"Produk (Baris 1)"`); only added /
  removed rows get one summary entry (`accounting_proc._log_pair`).
- After save, redirect back to the record with `success=` / `error=`.

## Pagination

Proc: one `count_documents(query)` + `paginate.build(total, page, per_page)`
+ `find(query, projection).sort([..., ("_id", -1)]).skip().limit()`, same
`query` for both. View: `paginate.read_params(params)`, `data["page_args"]`.
Never send all rows to the browser.

## Done means

- [ ] Collection in `model.py`; blueprint registered in `server.py`
- [ ] Guards + CSRF + sanitize on every view; Indonesian messages
- [ ] Log model registered; every saved field in the labels
- [ ] Tests added in `tests/test_logistics.py`; new GET pages in
      `test_all_pages_render`
- [ ] Do not install packages, run the suite, or start the server unless the
      user asks — the user checks the result

## Never

Refactor `slapz102_core/` or `slapz102_stdlib/`; rename existing routes,
fields, or response keys without a redirect; duplicate stdlib helpers
(`sanitize`, `csrf`, `paginate`, `idgen`); edit `static/v2/app.output.css`;
commit `.env` / `config.py`; add ORMs, queues, app factories, class views,
other CSS frameworks, or bundlers.
