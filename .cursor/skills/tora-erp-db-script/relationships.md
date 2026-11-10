# tora_logistics — collections, links, counters

Source of truth: `tora-erp-portal/slapz102_core/model.py` + each `*_proc.py`.
References are `str(_id)`. "Copies" must be refreshed when the source changes.

## Collections

| Collection | Find by | Points at | Copies | Pointed at by | Log model |
|---|---|---|---|---|---|
| `db_user` | `username` | — | — | contact/invoice `salesperson_id`, log `author_id` | `user` |
| `db_contact` | `name` (+ `category`) | `salesperson_id` | — | driver `contact_id`, shipment `sender_id`/`receiver_id`, manifest `client_id`, invoice/payment `partner_id` | `contact` |
| `db_vehicle` | `plate_number` | — | — | route / manifest / delivery `vehicle_id` | — |
| `db_driver` | `license_number` | `contact_id` (category `DRIVER`) | — | route / manifest / delivery `driver_id` | — |
| `db_hub` | `name` | — | — | route hub ids, manifest `hub_names[]`, delivery `hub_name` | — |
| `db_route` | `name` | hubs, vehicle, driver | `origin_name`, `destination_name`, `hub_names[]` | manifest `route_id` | — |
| `db_shipment` | `tracking_code` (AWB) | sender, receiver | `active_manifest_code`, `active_delivery_code`, `tracking_logs[]` | manifest / delivery `shipment_ids[]` | — |
| `db_manifest` | `manifest_code` (MAN) | vehicle, driver, client, route, shipments | hub names, origin, destination | — | — |
| `db_delivery` | `delivery_code` (ANT) | vehicle, driver, shipments | `hub_name` | — | — |
| `db_invoice` | `number` / `seq` + `move_type` | `partner_id`, `salesperson_id`, `lines[].tax` → tax code, `lines[].account` → account code, `reversed_entry_id` (nota kredit → faktur) | `partner_name`, `reversed_entry_number` | payment `invoice_id` | `invoice` / `credit_note` |
| `db_payment` | `number` / `seq` | `partner_id`, `invoice_id` | `partner_name`, `invoice_number` | invoice `payments[].payment_id` | `payment` |
| `db_account` | `code` (fixed once used) | — | — | invoice `lines[].account` | `account` |
| `db_tax` | `code` | — | — | invoice `lines[].tax` | `tax` |
| `db_config` | `name` | — | — | `accounting_sequences` = number prefixes | — |
| `db_code_counter` | `counter_key` | — | — | every generated number | — |
| `db_record_log` | `model` + `record_id` | the record, `author_id` | `author_name` | — | — |

## Numbers

| What | Default prefix (key in `accounting_sequences.data`) | Counter | Collection checked |
|---|---|---|---|
| Faktur | `INV/{TAHUN}/`, 5 digits (`out_invoice`) | `SEQ:INV/2026/` | `db_invoice` |
| Nota Kredit | `RINV/{TAHUN}/`, 5 (`out_refund`) | `SEQ:RINV/2026/` | `db_invoice` |
| Pembayaran | `PAY`, 5 (`customer_payment`) | `SEQ:PAY` | `db_payment` |
| URL seq | integer | `SEQID:invoice` / `SEQID:credit_note` / `SEQID:payment` | per type |
| AWB / MAN / ANT | `AWB-YYYYMMDD-0001` … | `AWB-YYYYMMDD` … | own collection |
| New tax code | `tax<N>` | `TAX` | `db_tax` |

## Enums

| Field | Values |
|---|---|
| contact `category` | `CLIENT`, `RECEIVER`, `DRIVER`, `VENDOR` |
| payment terms | `Langsung`, `7 Hari`, `15 Hari`, `30 Hari`, `45 Hari`, `60 Hari` |
| payment methods | `Transfer Bank`, `Tunai`, `Giro`, `Cek`, `Kartu Kredit` |
| fiscal position | `PKP`, `Non-PKP`, `Bebas Pajak` |
| user `role` / `status` / permission level | `superadmin`, `admin` / `ENABLE`, `DISABLE` / `none`…`full` per `users`, `contacts`, `accounting` |
| invoice `state` / `move_type` / `payment_state` | `DRAFT`, `POSTED`, `CANCEL` / `out_invoice`, `out_refund` / `not_paid`, `partial`, `paid` |
| payment `state` / `payment_type` / `journal` | `DRAFT`, `PAID`, `CANCEL` / `inbound` (Terima), `outbound` (Kirim) / `BNK1`, `CSH1` |
| account `account_type` | `asset_*`, `liability_*`, `equity`, `equity_unaffected`, `income`, `income_other`, `expense*` (lines: all except `asset_receivable`, `liability_payable`) |
| tax `tax_use` / `base` | `sale`, `purchase` / `full`, `dpp_11_12` (rate × 11/12) |
| shipment `status_utama` | `REGISTERED`, `MANIFESTED`, `IN_TRANSIT`, `ARRIVED_HUB`, `OUT_FOR_DELIVERY`, `DELIVERED` |
| log `kind` | `CREATE`, `CHANGE` (`changes: [{label, old, new}]`), `NOTE`, `EVENT` |

## Computed values

- Line: `subtotal = round2(qty * price)`, `tax_amount = round2(subtotal * amount/100 * (base=="dpp_11_12" ? 11/12 : 1))`.
- Invoice: `amount_untaxed = Σ subtotal`, `amount_tax = Σ tax_amount`,
  `amount_total = untaxed + tax`, `amount_residual = total` (new),
  `payments: []`, `payment_state: "not_paid"`, `due_date = date + term days`.
- Settle (payment / nota kredit Tambah): document `POSTED`, same partner,
  `applied = min(amount, residual)`; `$inc amount_residual -applied` with
  filter `amount_residual >= applied`; `$push payments {date, amount,
  method, memo, author_name, payment_id?, payment_number?, payment_seq?}`;
  `payment_state` partial / paid; EVENT + CHANGE log on both sides.

## Cascade checklist

| Change | Also do |
|---|---|
| Any insert of a logged model | CREATE log entry |
| Confirm a draft invoice | `state: POSTED`, `posted_at`; EVENT "Faktur telah divalidasi" + CHANGE Status |
| Payment Lunas | payment `state: PAID`, `posted_at`, `applied`; settle the document (above) |
| Reset payment | pull its `payments[]` entry, `$inc residual +applied`, recompute `payment_state`; payment `DRAFT`, `applied: 0` |
| Rename contact | `partner_name` on DRAFT invoices / payments (keep issued ones) |
| Rename hub | route `*_name` / `hub_names[]`, open manifests / deliveries |
| Soft delete contact / vehicle / driver / hub | block if referenced by live records — list them instead |
| Change tax rate / prefix | never rewrite issued documents |
