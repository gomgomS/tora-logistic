# Record log — activity panel beside a record form

One shared module (`slapz102_modules/record_log/`) gives every record a log:

| Kind | Written by | Shows |
|---|---|---|
| `CREATE` | owning module on create | "Membuat record baru" |
| `CHANGE` | owning module on update | one line per changed field: old → new (label) |
| `NOTE` | user clicks **Log catatan** | the note text |

All entries live in one collection, `db_record_log`, keyed by
`model` (registry key) + `record_id` (`str(_id)`). Reference integration:
contacts (`contacts_proc.create_contact` / `update_contact`,
`templates/contact_form.html`).

## Adding the log to a new module (for example accounting invoices)

1. **Register the model** in `record_log_proc.LOG_MODELS`:

```python
LOG_MODELS = {
    "contact": {"collection": "db_contact", "area": "contacts"},
    "user": {"collection": "db_user", "area": "users"},
    "invoice": {"collection": "db_invoice", "area": "invoices"}
}
```

   The note route only accepts registered models, checks the record exists
   and is not soft-deleted, and requires `read` access on `area`
   (see [access-control.md](access-control.md)).
   For one-line events without values (for example "Kata sandi diubah") use
   `record_log_proc().log_event(model, record_id, body, actor)`.

2. **Proc: write CREATE / CHANGE entries.** Accept an optional `actor`
   (`{"id", "name"}`, `None` = Sistem) so APIs and background code still work:

```python
from record_log.record_log_proc import record_log_proc

LOG_MODEL = "invoice"
LOG_LABELS = {"number": "Nomor", "partner_name": "Pelanggan", "status": "Status"}

def create_invoice(self, params, actor=None):
    ...
    rec.insert()
    saved = rec.get()
    record_log_proc().log_create(LOG_MODEL, str(saved["_id"]), actor)
# end def

def update_invoice(self, invoice_id, params, actor=None):
    invoice = self.get_invoice(invoice_id)
    ...
    self.mgdDB.db_invoice.update_one({"_id": ObjectId(invoice["id"])}, {"$set": fields})
    old, new = self._log_display(invoice, fields)
    record_log_proc().log_changes(LOG_MODEL, invoice["id"], old, new, LOG_LABELS, actor)
# end def
```

   - `LOG_LABELS` decides which fields are tracked and their order.
   - Pass **display values**: enum labels instead of codes, names instead of
     ids. Resolve ids with one `$in` query, only when they changed (see
     `contacts_proc._log_display`).
   - Nothing is written when no tracked field changed. Values are cut at 120
     characters.

3. **View: pass the actor and the log.**

```python
from record_log.record_log_proc import record_log_proc
from view.record_log.view_record_log import actor_from_user

result = invoices_proc().update_invoice(invoice_id, params, actor_from_user(current_user))
...
data["log_groups"] = record_log_proc().list_groups("invoice", invoice["id"])
```

   After saving, redirect back to the record (not the list) so the new entry
   is visible.

4. **Template: split layout + log pane.**

```html
{% from "_record_log.html" import record_log %}
{% block app_shell_class %}app-shell-fixed{% endblock %}
...
<div class="app-split">
    <div class="app-form-pane">
        <form class="app-form-sheet" ...> ... </form>
    </div>
    {{ record_log("invoice", invoice_id_or_empty, data.log_groups, data.csrf_token,
                  request.full_path, data.current_user.username) }}
</div>
```

   Pass `""` as record id for a new, unsaved record: the pane shows
   "Membuat record baru..." and **Log catatan** is disabled.

5. **Tests:** CREATE entry after create, CHANGE entry with the expected
   labels after update, note via `X-Requested-With: fetch` returns JSON, no
   CSRF → 400, unknown model → 400.

## How notes are posted

- `POST /log/<model>/<record_id>/note` (`record_log_blueprint.add_note`).
- `static/v2/record-log.js` (loaded by `app_base.html`) sends it with
  `fetch` + header `X-Requested-With: fetch`, so unsaved edits in the form are
  kept. The response carries the rendered entry (`_record_log_entry.html`),
  inserted under "Hari Ini". Ctrl+Enter submits.
- Without JavaScript the form posts normally and redirects to `next`.
- Body is sanitized, max 5000 characters; CSRF required.

## Performance

- `list_groups` is one query: filter `model + record_id + is_deleted`, sort
  `rec_timestamp -1, _id -1`, projection, `limit(200)`.
- Propose the index `[("model", 1), ("record_id", 1), ("rec_timestamp", -1)]`
  (ask before adding index setup code).
- Never query the log inside a list-page loop.
