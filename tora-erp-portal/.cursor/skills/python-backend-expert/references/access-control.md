# Access control (Hak Akses)

Defined in `slapz102_modules/auth/auth_proc.py`; managed in
**Pengaturan › Pengguna › (user) › tab Hak Akses**.

## Model

- **Superadmin**: always full access everywhere; per-area levels are ignored.
- **Admin**: one level per **area**, stored on the user as
  `db_user.permissions = {"contacts": "read", "users": "none", ...}`.
  A missing area falls back to the area's `default`.

Levels (shown to users in plain Indonesian, never as "CRUD"):

| Key | Label | Actions |
|---|---|---|
| `none` | Tidak ada akses | — |
| `read` | Hanya lihat | read |
| `create` | Lihat & tambah | read, create |
| `update` | Lihat, tambah & ubah | read, create, update |
| `full` | Akses penuh (lihat, tambah, ubah & hapus) | read, create, update, delete |

Action words in messages: read = *melihat*, create = *menambah*,
update = *mengubah*, delete = *menghapus* (`ACTION_VERBS`).

## Adding an area (for example Operasional)

1. Add it to `ACCESS_SECTIONS` (section title, area key, label, help, default):

```python
{"title": "Operasional", "areas": [
    {"key": "shipments", "label": "Order", "default": "full",
     "help": "Order LTL / FTL dan nomor AWB"}
]}
```

   The user form renders a dropdown for it automatically; the default keeps
   existing admins working.

2. Guard every view with the matching action (replaces `@login_required`):

```python
from auth.auth_proc import access_required

@access_required("shipments", "read")      # list, detail, search
def html_index(): ...

@access_required("shipments", "create")    # new form + create POST
@access_required("shipments", "update")    # update POST
@access_required("shipments", "delete")    # delete / bulk delete POST
```

   A denied request redirects to the home screen with
   "Anda tidak punya akses untuk <aksi> <area>".

3. Hide what the user cannot do (the server check stays the real guard):

```html
{% if data.current_user.can('shipments', 'create') %}<a ...>Baru</a>{% endif %}
```

   - No `delete`: drop the checkbox column and the bulk form.
   - Read-only record: wrap fields in
     `<fieldset class="app-fieldset" disabled>` and hide the save icon.
     Keep the tab buttons **outside** the fieldset (a disabled fieldset
     disables its buttons too).
   - Launcher tiles and menu links check `can(area, 'read')`.

4. If the module has a record log, set `"area"` in
   `record_log_proc.LOG_MODELS`; adding notes requires `read` on it.

5. Tests: log in as an admin with a lower level (see `_login_as` /
   `_create_user` in `tests/test_logistics.py`) and assert redirects and that
   nothing was written.

## Guards in user management (do not weaken)

- Only a Superadmin can create, edit, or delete a Superadmin account, or grant
  the Superadmin role.
- An admin can grant each area at most their own level.
- Nobody can change their own role, access levels, or status.
- Changing your own password requires the current password.
- The current account and the last Superadmin are never deleted or demoted.
