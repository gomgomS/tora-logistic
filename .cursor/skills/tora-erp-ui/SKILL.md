---
name: tora-erp-ui
description: >-
  Default look of tora-erp-portal pages: list pages (control panel, search
  facets, wide resizable table, server pager) and record detail pages
  (status bar, form sheet, tabs, relation pickers, log pane). Use when
  creating or changing any template, list, form, or detail page in
  tora-erp-portal/templates. Pair with tora-erp-backend.
---

# TORA ERP portal — page standards

**Copy the closest reference template and adapt it; never invent a layout.**
Reference HTML in `../RND ODOO/TEMPLETE PLAIN HTMLJS/` gives layout only —
rebuild it with the app classes below, never paste its CSS or name.

| Need | Copy |
|---|---|
| List page | `templates/accounting_payments.html` (simple), `accounting_invoices.html` (totals, optional columns) |
| Document with lines + workflow | `templates/accounting_invoice_form.html` |
| Document without lines | `templates/accounting_payment_form.html` |
| Master data with tabs | `templates/contact_form.html` |
| Small config record | `templates/accounting_account_form.html` |
| Same page inside another app | `contacts.html` + `view_contacts.KONTAK_SHELL` / `view_accounting._contact_shell` (`{% extends data.ct.base %}`) |

## Shell

App templates extend the app base (`accounting_base.html`, or
`app_base.html` with blocks `app_name`, `app_home`, `app_icon`,
`app_icon_class`, `app_menu`). The view passes `data.page` (`menu` = active
navbar menu) and `data.slug` (= `MENUS` entry `key`) so the menu highlights.

## List page

- `app_control`: `.app-cp` → left: `Baru` (`app-btn-primary`, only with
  `can(area,'create')`), `.app-cp-title`, bulk-delete `.app-cp-selection`;
  middle: GET search form `.app-search` with `.app-search-facet` chips +
  filter dropdown; right: `pager_compact(...)`.
- Table: `<table class="app-list" data-table-key="x" data-select-bar="...">`;
  every `<th>` has `data-key` (fixed) or `data-col` (optional) and
  `data-width`; last `<th class="app-list-optional">` holds the column
  menu; rows `data-href`; optional columns from a `columns` list in the
  template; `<tfoot class="app-list-foot">` for sums; `pager_bar(...)` below.
- Empty state: `empty_state(...)` from `_ui.html`. Status: `app-badge
  app-badge-state-<class>`.
- `static/v2/app-list.js` (loaded by the base) does resize, column menu,
  select bar, row links, tabs — data attributes only, no page JS.

## Detail page (always this order)

```
app_shell_class = app-shell-fixed
app_control: [Baru] List / Current  [save ☁ form="<id>"] [discard ✕]
.app-split
  .app-form-pane
    .inv-statusbar   buttons left, .inv-pills right   (records with states)
    form.app-form-sheet (+ inv-editable when editable)
      .inv-banner / .inv-banner-info                   (optional)
      .inv-title      small label + <h1> / .app-input-xl
      .app-sheet-grid two .app-group columns (label | field)
      .app-tabs + .app-tab-panel                       (tabs OUTSIDE disabled fieldsets)
  {{ record_log(model, id or "", data.log_groups, data.csrf_token,
                request.full_path, data.current_user.username) }}   ← always
```

- Read-only = `<fieldset class="app-fieldset" disabled>`; split fieldsets
  around the tabs. Drafts show **Simpan** + the dirty marker
  (`[data-dirty-flag]`, script in `accounting_payment_form.html`).
- After save, redirect back to the record with `success=` / `error=`.
- State buttons post small hidden forms (`form="payStateReset"`).

## Relation fields → always the picker

```jinja
{% from "_combobox.html" import combobox, combobox_source %}
{{ combobox("line_account", value, label, "accountOptions", placeholder="Cari akun ...") }}
{{ combobox_source("accountOptions", data.account_options) }}   {# once, outside <template> rows #}
{{ combobox("partner_id", id, name, url=url_for('contacts_blueprint.api_search', category='CLIENT')) }}
```

- Options built in the view: `[{"value", "label", "description"}]`; only
  active records; current label passed separately for inactive ones.
- `url=` for big collections (endpoint gets `q=`, returns `{results: [...]}`).
- `window.appCombo.set(box, value, label)` to set one from page code;
  the hidden input fires `change`.
- The proc still validates the value.

## CSS

Classes live in `static/v2/input.css`; after editing run
`npm run build:css`. Never edit `app.output.css`. Reuse existing `app-*` /
`inv-*` classes before adding new ones.

## Checklist (new page)

- [ ] Copied the reference template; Indonesian labels
- [ ] Buttons hidden by `data.current_user.can(...)`
- [ ] Relation fields use `combobox`
- [ ] Detail page: status bar (if states), log pane, redirect back to record
- [ ] New GET path added to `test_all_pages_render`
