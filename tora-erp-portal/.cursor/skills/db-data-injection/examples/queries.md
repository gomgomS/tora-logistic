# Worked mongosh scripts

Copy the **helpers** block into every script. Each script is split into
Cek (read only) → Eksekusi → Verifikasi → Batalkan.

## Helpers (put at the top of every script)

```js
db = db.getSiblingDB("tora_logistics");     // database name = MONGO_DB_NAME in config

const NOW = Date.now() + 7 * 3600 * 1000;   // Jakarta wall clock, as database.new() stores it
const STAMP = new Date(NOW).toISOString().slice(0, 19).replace("T", " ");

function base(id) {
  return { _id: id, ipkey: id.toString(), pkey: id.toString() + "-0000-0-" + NOW,
           rec_timestamp: NOW, rec_timestamp_str: STAMP, is_deleted: false };
}
function mustOne(coll, query, label) {
  const found = db[coll].find(Object.assign({ is_deleted: false }, query)).limit(2).toArray();
  if (found.length !== 1) throw new Error(label + ": " + found.length + " data cocok, harus tepat 1");
  return found[0];
}
function esc(text) {                         // same as the app's sanitize.clean_html
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                     .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}
function round2(n) { return Math.round(n * 100) / 100; }
function logEntry(model, recordId, kind, body, changes) {
  const id = new ObjectId();
  db.db_record_log.insertOne(Object.assign(base(id), {
    model: model, record_id: recordId.toString(), kind: kind, body: body,
    changes: changes || [], author_id: "SYSTEM", author_name: "Sistem"
  }));
}
function nextCode(counterKey, highestUsed) {  // atomic, never re-issues a number
  db.db_code_counter.updateOne({ counter_key: counterKey }, { $max: { seq: highestUsed } }, { upsert: true });
  return db.db_code_counter.findOneAndUpdate(
    { counter_key: counterKey }, { $inc: { seq: 1 } }, { upsert: true, returnDocument: "after" }
  ).seq;
}
```

## 1. Insert contacts (idempotent, with history)

```js
// ===== Cek =====
const rows = [
  { name: "PT Danau Toba Sejahtera", category: "CLIENT", city: "Medan", phone: "061-555-0101", sale_payment_term: "30 Hari" },
  { name: "CV Balige Makmur", category: "RECEIVER", city: "Balige", phone: "0632-21234" }
];
rows.forEach(r => print(r.name, "->", db.db_contact.countDocuments({ name: esc(r.name), is_deleted: false }) ? "SUDAH ADA (dilewati)" : "akan dibuat"));

// ===== Eksekusi =====
const created = [];
rows.forEach(r => {
  if (db.db_contact.countDocuments({ name: esc(r.name), is_deleted: false })) return;
  const id = new ObjectId();
  db.db_contact.insertOne(Object.assign(base(id), {
    name: esc(r.name), company_name: "", phone: r.phone || "", email: "", address: "", city: r.city || "",
    category: r.category, street2: "", province: "", postal_code: "", country: "Indonesia",
    tax_id: "", job_title: "", website: "", tags: "", salesperson_id: "",
    sale_payment_term: r.sale_payment_term || "", sale_payment_method: "",
    purchase_payment_term: "", purchase_payment_method: "", fiscal_position: "",
    reference: "", industry: "", notes: ""
  }));
  logEntry("contact", id, "CREATE", "Membuat record baru");
  created.push(id);
});
print("Dibuat:", created.length);

// ===== Verifikasi =====
db.db_contact.find({ _id: { $in: created } }, { name: 1, category: 1, city: 1 });

// ===== Batalkan =====
// db.db_contact.updateMany({ _id: { $in: created } }, { $set: { is_deleted: true } });
```

## 2. Insert an invoice (number from the sequence, totals computed)

```js
// ===== Cek =====
const partner = mustOne("db_contact", { name: esc("PT Danau Toba Sejahtera") }, "Pelanggan");
const invoiceDate = "2026-11-08";
const term = "30 Hari";
const lines = [
  { product: "Jasa Trucking Medan - Balige (FTL)", account: "41000020", quantity: 1, price_unit: 8500000, tax: "ppn12_dpp" },
  { product: "Biaya bongkar muat", account: "41000010", quantity: 2, price_unit: 250000, tax: "" }
];
const taxCodes = [...new Set(lines.map(l => l.tax).filter(Boolean))];
const taxes = {};
db.db_tax.find({ code: { $in: taxCodes }, tax_use: "sale", active: true, is_deleted: false })
  .forEach(t => { taxes[t.code] = t.amount / 100 * (t.base === "dpp_11_12" ? 11 / 12 : 1); });
taxCodes.forEach(c => { if (!(c in taxes)) throw new Error("Pajak " + c + " tidak ada / tidak aktif"); });

// ===== Eksekusi =====
const cfg = db.db_config.findOne({ name: "accounting_sequences", is_deleted: false });
const seqCfg = (cfg && cfg.data && cfg.data.out_invoice) || { prefix: "INV/{TAHUN}/", padding: 5 };
const prefix = seqCfg.prefix.replace("{TAHUN}", invoiceDate.slice(0, 4))
                            .replace("{THN}", invoiceDate.slice(2, 4))
                            .replace("{BULAN}", invoiceDate.slice(5, 7));
const used = db.db_invoice.find({ number: { $regex: "^" + prefix.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&") + "[0-9]+$" } }, { number: 1 })
  .toArray().map(d => parseInt(d.number.slice(prefix.length), 10)).reduce((a, b) => Math.max(a, b), 0);
const number = prefix + String(nextCode("SEQ:" + prefix, used)).padStart(seqCfg.padding, "0");

let untaxed = 0, taxTotal = 0;
const stored = lines.map(l => {
  const subtotal = round2(l.quantity * l.price_unit);
  const tax_amount = round2(subtotal * (l.tax ? taxes[l.tax] : 0));
  untaxed += subtotal; taxTotal += tax_amount;
  return { product: esc(l.product), account: l.account, quantity: l.quantity, price_unit: l.price_unit,
           tax: l.tax, subtotal: subtotal, tax_amount: tax_amount };
});
untaxed = round2(untaxed); taxTotal = round2(taxTotal);
const days = term === "Langsung" ? 0 : parseInt(term, 10);
const due = new Date(invoiceDate + "T00:00:00Z"); due.setUTCDate(due.getUTCDate() + days);

const topSeq = db.db_invoice.find({ seq: { $gt: 0 } }, { seq: 1 }).sort({ seq: -1 }).limit(1).toArray();
const seq = nextCode("SEQID:invoice", topSeq.length ? topSeq[0].seq : 0);   // URL /accounting/invoices/<seq>

const invId = new ObjectId();
db.db_invoice.insertOne(Object.assign(base(invId), {
  move_type: "out_invoice", seq: seq, number: number, state: "DRAFT",
  payments: [], payment_state: "not_paid",
  partner_id: partner._id.toString(), partner_name: partner.name,
  invoice_date: invoiceDate, payment_term: term, due_date: due.toISOString().slice(0, 10),
  customer_ref: "", payment_ref: "", salesperson_id: "", delivery_date: "",
  efaktur_code: "", fiscal_position: "", notes: "", lines: stored,
  amount_untaxed: untaxed, amount_tax: taxTotal, amount_total: round2(untaxed + taxTotal),
  amount_residual: round2(untaxed + taxTotal), posted_at: ""
}));
logEntry("invoice", invId, "CREATE", "Faktur " + number + " dibuat");
print("Faktur dibuat:", number, "→ /accounting/invoices/" + seq, "total", round2(untaxed + taxTotal));

// ===== Verifikasi =====
db.db_invoice.findOne({ _id: invId }, { number: 1, partner_name: 1, amount_total: 1, due_date: 1 });

// ===== Batalkan (hanya selama belum dikonfirmasi) =====
// db.db_invoice.updateOne({ _id: invId, posted_at: "" }, { $set: { is_deleted: true } });
```

## 3. Rename a contact and propagate

```js
// ===== Cek =====
const oldName = esc("CV Balige Makmur");
const newName = esc("CV Balige Makmur Jaya");
const c = mustOne("db_contact", { name: oldName }, "Kontak");
print("Faktur Draft yang ikut berubah:", db.db_invoice.countDocuments({ partner_id: c._id.toString(), state: "DRAFT", is_deleted: false }));
print("Faktur Terekam/Batal (tetap nama lama):", db.db_invoice.countDocuments({ partner_id: c._id.toString(), state: { $ne: "DRAFT" }, is_deleted: false }));

// ===== Eksekusi =====
db.db_contact.updateOne({ _id: c._id }, { $set: { name: newName } });
db.db_invoice.updateMany({ partner_id: c._id.toString(), state: "DRAFT", is_deleted: false }, { $set: { partner_name: newName } });
logEntry("contact", c._id, "CHANGE", "", [{ label: "Nama", old: oldName, new: newName }]);

// ===== Verifikasi =====
db.db_contact.findOne({ _id: c._id }, { name: 1 });

// ===== Batalkan =====
// db.db_contact.updateOne({ _id: c._id }, { $set: { name: oldName } });
// db.db_invoice.updateMany({ partner_id: c._id.toString(), state: "DRAFT" }, { $set: { partner_name: oldName } });
```

## 4. Soft delete a contact only if nothing uses it

```js
// ===== Cek =====
const target = mustOne("db_contact", { name: esc("CV Balige Makmur Jaya") }, "Kontak");
const ref = target._id.toString();
const usage = {
  shipments: db.db_shipment.countDocuments({ is_deleted: false, $or: [{ sender_id: ref }, { receiver_id: ref }] }),
  drivers: db.db_driver.countDocuments({ is_deleted: false, contact_id: ref }),
  manifests: db.db_manifest.countDocuments({ is_deleted: false, client_id: ref, status: { $in: ["PLANNED", "IN_TRANSIT", "ARRIVED"] } }),
  invoices: db.db_invoice.countDocuments({ is_deleted: false, partner_id: ref, state: { $ne: "CANCEL" } })
};
printjson(usage);

// ===== Eksekusi (berhenti kalau masih dipakai) =====
if (Object.values(usage).some(n => n > 0)) throw new Error("Kontak masih dipakai, tidak dihapus");
db.db_contact.updateOne({ _id: target._id }, { $set: { is_deleted: true } });
logEntry("contact", target._id, "EVENT", "Kontak diarsipkan lewat query");

// ===== Batalkan =====
// db.db_contact.updateOne({ _id: target._id }, { $set: { is_deleted: false } });
```

## 5. Insert a shipment with an AWB code

```js
// ===== Cek =====
const sender = mustOne("db_contact", { name: esc("PT Danau Toba Sejahtera") }, "Pengirim");
const receiver = mustOne("db_contact", { name: esc("CV Balige Makmur Jaya") }, "Penerima");
const today = STAMP.slice(0, 10).replace(/-/g, "");               // YYYYMMDD (Jakarta)

// ===== Eksekusi =====
const awbKey = "AWB-" + today;
const usedAwb = db.db_shipment.find({ tracking_code: { $regex: "^" + awbKey + "-[0-9]+$" } }, { tracking_code: 1 })
  .toArray().map(d => parseInt(d.tracking_code.split("-")[2], 10)).reduce((a, b) => Math.max(a, b), 0);
const awb = awbKey + "-" + String(nextCode(awbKey, usedAwb)).padStart(4, "0");
const shipId = new ObjectId();
db.db_shipment.insertOne(Object.assign(base(shipId), {
  tracking_code: awb, po_number: "", service_type: "LTL",
  sender_id: sender._id.toString(), receiver_id: receiver._id.toString(),
  origin_city: "Medan", origin_province: "", origin_regency: "", origin_district: "",
  origin_village: "", origin_postal_code: "", origin_address: "",
  destination_city: "Balige", destination_province: "", destination_regency: "",
  destination_district: "", destination_village: "", destination_postal_code: "", destination_address: "",
  status_utama: "REGISTERED", current_location: "Medan",
  active_manifest_code: "", active_delivery_code: "",
  tracking_logs: [{ milestone_status: "ORDER_REGISTERED", location: "Medan — Gudang Asal",
                    notes: "Order terdaftar / barang diterima di gudang asal", updated_by: "SYSTEM", timestamp: STAMP }]
}));
print("Order dibuat:", awb);

// ===== Batalkan =====
// db.db_shipment.updateOne({ _id: shipId, status_utama: "REGISTERED" }, { $set: { is_deleted: true } });
```

## Answer shape (what the user sees)

1. One paragraph: what the script changes, and in which collections
   (including the related ones adjusted automatically).
2. The script in one code block.
3. "Cara menjalankan": open mongosh / MongoDB Compass › Mongosh on
   `tora_logistics`, run **Cek** first, read the output, then run
   **Eksekusi** and **Verifikasi**. Keep the **Batalkan** lines for undo.
4. Anything the script cannot do (for example password hashes) and how to do
   it instead.
