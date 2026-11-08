# Collection relationships — tora_logistics

Source of truth: `slapz102_core/model.py` and each module's `*_proc.py`.
Re-check them before writing a script; add new collections here when they
appear.

References are stored as **`str(_id)`** of the target. "Denormalized" means a
copy of a value from another collection that must be updated when the source
changes.

## Map

| Collection | Natural key (find by) | Points at | Denormalized copies it holds | Who points at me | Log model |
|---|---|---|---|---|---|
| `db_user` | `username` | — | — | `db_contact.salesperson_id`, `db_invoice.salesperson_id`, `db_record_log.author_id`, shipment `tracking_logs[].updated_by` | `user` |
| `db_contact` | `name` (+ `category`) | `salesperson_id` → db_user | — | `db_driver.contact_id`, `db_shipment.sender_id` / `receiver_id`, `db_manifest.client_id`, `db_invoice.partner_id` (+ `partner_name` copy) | `contact` |
| `db_vehicle` | `plate_number` | — | — | `db_route.vehicle_id`, `db_manifest.vehicle_id`, `db_delivery.vehicle_id` | — |
| `db_driver` | `license_number` | `contact_id` → db_contact (category `DRIVER`) | — | `db_route.driver_id`, `db_manifest.driver_id`, `db_delivery.driver_id` | — |
| `db_hub` | `name` | — | — | `db_route.origin_hub_id` / `destination_hub_id` / `hub_ids[]` (+ `origin_name` / `destination_name` / `hub_names[]` copies), `db_manifest.hub_names[]`, `db_delivery.hub_name`, shipment `current_location` text | — |
| `db_route` | `name` | hubs, `vehicle_id`, `driver_id` | `origin_name`, `destination_name`, `hub_names[]` (hub names) | `db_manifest.route_id` | — |
| `db_shipment` | `tracking_code` (AWB) | `sender_id`, `receiver_id` → db_contact | `active_manifest_code`, `active_delivery_code`, `tracking_logs[]` (embedded) | `db_manifest.shipment_ids[]`, `db_delivery.shipment_ids[]` | — |
| `db_manifest` | `manifest_code` (MAN) | `vehicle_id`, `driver_id`, `client_id`, `route_id`, `shipment_ids[]` | `hub_names[]`, `origin`, `destination` (names) | shipment `active_manifest_code` | — |
| `db_delivery` | `delivery_code` (ANT) | `vehicle_id`, `driver_id`, `shipment_ids[]` | `hub_name` | shipment `active_delivery_code` | — |
| `db_invoice` | `seq` (URL `/accounting/invoices/4`) or `number` (e.g. `INV/2026/00004`) | `partner_id` → db_contact, `salesperson_id` → db_user, `lines[].tax` → `db_tax.code` | `partner_name` (contact name) | — | `invoice` |
| `db_tax` | `code` | — | — | `db_invoice.lines[].tax` | — |
| `db_config` | `name` | — | — | `accounting_sequences` drives invoice numbers | — |
| `db_code_counter` | `counter_key` | — | — | every generated code (see below) | — |
| `db_record_log` | `model` + `record_id` | `record_id` → the logged record, `author_id` → db_user | `author_name` | — | — |
| `db_unique_counter` | (single doc) | — | — | used by `database.new()` for `pkey`; scripts may skip it | — |
| `db_sample_item` | `slug` | — | — | — | — |

## Generated codes and their counters

| Code | Format | `db_code_counter.counter_key` | Produced by |
|---|---|---|---|
| AWB (shipment) | `AWB-YYYYMMDD-0001` | `AWB-YYYYMMDD` | `shipments_proc._next_code` |
| Manifest | `MAN-YYYYMMDD-0001` | `MAN-YYYYMMDD` | `manifests_proc` |
| Delivery (antar) | `ANT-YYYYMMDD-0001` | `ANT-YYYYMMDD` | `manifests_proc` |
| Invoice | prefix from `db_config` `accounting_sequences.data.out_invoice` (default `INV/{TAHUN}/`, 5 digits) + seq | `SEQ:` + rendered prefix, e.g. `SEQ:INV/2026/` | `accounting_proc.next_number` |
| Invoice URL number (`seq`) | integer 1, 2, 3 ... | `SEQID:invoice` | `accounting_proc._next_seq` |
| New tax code | `tax<N>` | `TAX` | `accounting_proc.create_tax` |

Before taking a number: `updateOne({counter_key}, {$max: {seq: <highest number already used>}}, {upsert: true})`,
then `findOneAndUpdate({counter_key}, {$inc: {seq: 1}}, {upsert: true, returnDocument: "after"})`.

Prefix tokens: `{TAHUN}` → 2026, `{THN}` → 26, `{BULAN}` → 11 (from the
document date).

## Enums (use exactly)

| Field | Values |
|---|---|
| `db_contact.category` | `CLIENT`, `RECEIVER`, `DRIVER`, `VENDOR` |
| `db_contact` payment terms | `Langsung`, `7 Hari`, `15 Hari`, `30 Hari`, `45 Hari`, `60 Hari` |
| `db_contact.fiscal_position` | `PKP`, `Non-PKP`, `Bebas Pajak` |
| `db_user.role` / `status` | `superadmin`, `admin` / `ENABLE`, `DISABLE` |
| `db_user.permissions` levels | `none`, `read`, `create`, `update`, `full` per area (`users`, `contacts`, `accounting`) |
| `db_vehicle.ownership`, `db_driver.type` | `INTERNAL`, `VENDOR` |
| `db_shipment.service_type` | `LTL`, `FTL` |
| `db_shipment.status_utama` | `REGISTERED`, `MANIFESTED`, `IN_TRANSIT`, `ARRIVED_HUB`, `OUT_FOR_DELIVERY`, `DELIVERED` |
| `db_manifest.status` | `PLANNED`, `IN_TRANSIT`, `ARRIVED`, `COMPLETED` |
| `db_delivery.status` | `OPEN`, `CLOSED` |
| `db_invoice.state` | `DRAFT`, `POSTED`, `CANCEL`; `move_type` `out_invoice` |
| `db_invoice.lines[].account` | `41000010`, `41000020`, `41000030` |
| `db_tax.tax_use` / `base` / `scope` | `sale`, `purchase` / `full`, `dpp_11_12` / `""`, `goods`, `service` |
| `db_record_log.kind` | `CREATE`, `CHANGE`, `NOTE`, `EVENT` |

## Computed values (compute in the script like the proc)

- **Invoice line**: `subtotal = round2(quantity * price_unit)`;
  `tax_amount = round2(subtotal * rate)` with
  `rate = amount / 100 * (base == "dpp_11_12" ? 11/12 : 1)` from `db_tax`.
- **Invoice totals**: `amount_untaxed = Σ subtotal`, `amount_tax = Σ tax_amount`,
  `amount_total = untaxed + tax`, `amount_residual = amount_total`.
- **Invoice payments**: `payments: [{date, amount, method, memo, author_name}]`;
  `amount_residual = amount_total - Σ amount`; `payment_state` is
  `not_paid` / `partial` / `paid`. Only `POSTED` invoices take payments;
  never let `amount_residual` go below 0.
- **Invoice due date**: `invoice_date + N days` from `payment_term`
  (`Langsung` = 0).
- **Invoice `partner_name`**: the contact's `name` at the time of writing.
- **Shipment initial log**: `tracking_logs: [{milestone_status: "ORDER_REGISTERED",
  location: "<origin> — Gudang Asal", notes: "Order terdaftar / barang diterima di gudang asal",
  updated_by: "SYSTEM", timestamp: STAMP}]`, `current_location = origin_city`.

## Cascade checklist per change type

| Change | Also do |
|---|---|
| Insert contact / user / invoice | `db_record_log` CREATE entry |
| Insert invoice | `seq` from `SEQID:invoice`, number from the prefix counter, totals, `partner_name`, tax codes exist & active, `payments: []`, `payment_state: "not_paid"` |
| Register a payment | only on `POSTED`; `$push` into `payments`, `$inc` `amount_residual` by −amount with filter `amount_residual >= amount`, set `payment_state`, EVENT log |
| Insert shipment | AWB from counter, sender/receiver exist, initial `tracking_logs` |
| Insert driver | contact exists with category `DRIVER` (create it first if missing) |
| Insert route | hubs + vehicle + driver exist; copy hub names |
| Rename contact | `db_invoice.partner_name` where `partner_id` matches and `state` is `DRAFT` (keep POSTED as issued); CHANGE log |
| Rename hub | `db_route.origin_name` / `destination_name` / `hub_names[]`, open `db_manifest.hub_names[]`, open `db_delivery.hub_name` |
| Soft delete contact | block if referenced by live shipments, drivers, open manifests, or non-cancelled invoices — list them instead |
| Soft delete vehicle / driver | block if on a `PLANNED` / `IN_TRANSIT` manifest, open delivery, or route |
| Soft delete hub | block if on a route |
| Soft delete user | never the last superadmin; keep references (history) |
| Change tax rate | do not touch existing invoice lines (history); new rate applies to new lines |
| Change invoice numbers / prefix | use `db_config` `accounting_sequences`; never renumber POSTED invoices |

## Suggested indexes (propose, do not create)

`db_contact {is_deleted, category, name}`, `db_shipment {tracking_code}` unique,
`db_invoice {number}` unique, `db_record_log {model, record_id, rec_timestamp}`,
`db_code_counter {counter_key}` unique, `db_tax {code}` unique.
