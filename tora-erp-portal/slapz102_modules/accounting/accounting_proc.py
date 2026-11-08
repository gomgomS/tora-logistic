import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import datetime
import re

import pymongo

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config
from slapz102_stdlib import paginate

from contacts.contacts_proc import PAYMENT_TERMS, PAYMENT_METHODS, FISCAL_POSITIONS
from record_log.record_log_proc import record_log_proc

LOG_MODEL = "invoice"

# ---------------------------------------------------------------------------
# ACCOUNTING MODULE — business logic layer.
#
# The Akuntansi app: dashboard journal cards, navbar menus, and documents.
# Built so far: Faktur Pelanggan (db_invoice). Other document pages
# (tagihan, pembayaran, entri jurnal, ...) are "segera hadir" until built.
# ---------------------------------------------------------------------------

# Document pages: slug -> menu label, page title, the menu it belongs to.
# Pelanggan / Vendor master lists reuse the Kontak list (see MENUS).
PAGES = {
    "invoices": {"label": "Faktur", "title": "Faktur", "menu": "Pelanggan",
                 "desc": "Faktur penjualan untuk klien atas order LTL / FTL."},
    "credit-notes": {"label": "Nota Kredit", "title": "Nota Kredit", "menu": "Pelanggan",
                     "desc": "Pengurangan tagihan klien, misalnya klaim kerusakan atau retur."},
    "customer-payments": {"label": "Pembayaran", "title": "Pembayaran Pelanggan", "menu": "Pelanggan",
                          "desc": "Pencatatan uang masuk dari klien dan pelunasan faktur."},
    "sale-products": {"label": "Produk", "title": "Produk Penjualan", "menu": "Pelanggan",
                      "desc": "Layanan dan produk yang dijual ke klien (tarif LTL, charter FTL, ...)."},
    "bills": {"label": "Tagihan", "title": "Tagihan", "menu": "Vendor",
              "desc": "Tagihan dari vendor: sewa armada, BBM, tol, dan biaya lain."},
    "refunds": {"label": "Pengembalian", "title": "Pengembalian", "menu": "Vendor",
                "desc": "Pengembalian dana dari vendor atas tagihan yang sudah dibayar."},
    "vendor-payments": {"label": "Pembayaran", "title": "Pembayaran Vendor", "menu": "Vendor",
                        "desc": "Pencatatan uang keluar ke vendor dan pelunasan tagihan."},
    "purchase-products": {"label": "Produk", "title": "Produk Pembelian", "menu": "Vendor",
                          "desc": "Barang dan jasa yang dibeli dari vendor."},
    "journal-entries": {"label": "Entri Jurnal", "title": "Entri Jurnal", "menu": "Akuntansi",
                        "desc": "Semua entri jurnal: penjualan, pembelian, bank, kas, dan lain-lain."}
}

def _page_entry(slug):
    return {"label": PAGES[slug]["label"], "endpoint": "accounting_blueprint.page",
            "args": {"slug": slug}, "key": slug, "area": None, "divider": False}
# end def


# Navbar dropdowns, in order. Each entry: label, endpoint + args, key (marks
# the active page), area (extra access area needed to show it), divider.
# (Not named "items": in Jinja menu.items would be dict.items.)
MENUS = [
    {"label": "Pelanggan", "entries": [
        {"label": "Faktur", "endpoint": "accounting_blueprint.invoices", "args": {},
         "key": "invoices", "area": None, "divider": False},
        _page_entry("credit-notes"),
        _page_entry("customer-payments"),
        _page_entry("sale-products"),
        {"label": "Pelanggan", "endpoint": "contacts_blueprint.index", "args": {"category": "CLIENT"},
         "key": "", "area": "contacts", "divider": True}
    ]},
    {"label": "Vendor", "entries": [
        _page_entry("bills"),
        _page_entry("refunds"),
        _page_entry("vendor-payments"),
        _page_entry("purchase-products"),
        {"label": "Vendor", "endpoint": "contacts_blueprint.index", "args": {"category": "VENDOR"},
         "key": "", "area": "contacts", "divider": True}
    ]},
    {"label": "Akuntansi", "entries": [
        _page_entry("journal-entries")
    ]},
    {"label": "Konfigurasi", "entries": [
        {"label": "Pengaturan", "endpoint": "accounting_blueprint.settings", "args": {},
         "key": "settings", "area": None, "divider": False},
        {"label": "Pajak", "endpoint": "accounting_blueprint.taxes", "args": {},
         "key": "taxes", "area": None, "divider": False}
    ]}
]

# Dashboard journal cards. Targets are page slugs, or an endpoint name
# (contains a ".") for pages with their own route.
JOURNALS = [
    {"name": "Faktur Pelanggan", "code": "INV", "metric": "Faktur belum dibayar",
     "primary": ("Faktur Baru", "accounting_blueprint.invoice_new"),
     "links": [("Lihat Faktur", "invoices")]},
    {"name": "Tagihan Vendor", "code": "BILL", "metric": "Tagihan yang harus dibayar",
     "primary": ("Tagihan Baru", "bills"),
     "links": [("Lihat Tagihan", "bills")]},
    {"name": "Bank", "code": "BNK1", "metric": "Saldo di buku besar",
     "primary": ("Buat", "journal-entries"),
     "links": [("Mutasi", "journal-entries"), ("Rekonsiliasi", "journal-entries")]},
    {"name": "Kas", "code": "CSH1", "metric": "Saldo di buku besar",
     "primary": ("Transaksi Baru", "journal-entries"),
     "links": [("Daftar Kas", "journal-entries")]}
]


def rupiah(amount):
    # 1234567.5 -> "Rp 1.234.567,50"
    try:
        value = float(amount or 0)
    except Exception:
        value = 0.0
    # end try
    sign = "-" if value < 0 else ""
    whole = int(abs(value))
    cents = int(round((abs(value) - whole) * 100))
    if cents == 100:
        whole = whole + 1
        cents = 0
    # end if
    digits = "{:,}".format(whole).replace(",", ".")
    return sign + "Rp " + digits + "," + str(cents).zfill(2)
# end def


# ---------------------------------------------------------------------------
# Faktur Pelanggan
# ---------------------------------------------------------------------------

STATE_DRAFT = "DRAFT"
STATE_POSTED = "POSTED"
STATE_CANCEL = "CANCEL"
STATE_LABELS = {STATE_DRAFT: "Draft", STATE_POSTED: "Terekam", STATE_CANCEL: "Batal"}

PAY_NOT_PAID = "not_paid"
PAY_PARTIAL = "partial"
PAY_PAID = "paid"
PAYMENT_STATE_LABELS = {PAY_NOT_PAID: "Belum Dibayar", PAY_PARTIAL: "Dibayar Sebagian", PAY_PAID: "Lunas"}

SEQ_ID_KEY = "SEQID:invoice"

# Chart of accounts used by invoices (code + name shown as one label).
REVENUE_ACCOUNTS = [
    {"key": "41000010", "label": "41000010 Penjualan"},
    {"key": "41000020", "label": "41000020 Pendapatan Jasa Angkutan"},
    {"key": "41000030", "label": "41000030 Pendapatan Lain-lain"}
]
REVENUE_ACCOUNT_LABELS = {}
for _acc in REVENUE_ACCOUNTS:
    REVENUE_ACCOUNT_LABELS[_acc["key"]] = _acc["label"]
# end for
ACCOUNT_RECEIVABLE = "11210010 Piutang Dagang"
ACCOUNT_TAX_OUT = "21221010 PPN Keluaran"

# ---------------------------------------------------------------------------
# Pajak (Konfigurasi > Pajak), stored in db_tax. Applied on top of the line
# amount (price excludes tax). PPN 12% for non-luxury goods is charged on
# DPP Nilai Lain 11/12, so its effective rate is 11%.
# ---------------------------------------------------------------------------

TAX_USES = {"sale": "Penjualan", "purchase": "Pembelian"}
TAX_SCOPES = {"": "—", "goods": "Barang", "service": "Layanan"}
TAX_BASES = [
    {"key": "full", "label": "100% dari harga", "factor": 1.0},
    {"key": "dpp_11_12", "label": "DPP Nilai Lain 11/12", "factor": 11.0 / 12.0}
]
TAX_BASE_FACTORS = {}
for _base in TAX_BASES:
    TAX_BASE_FACTORS[_base["key"]] = _base["factor"]
# end for
DEFAULT_SALE_TAX = "ppn12_dpp"

# Created once when db_tax is empty (codes stay stable for invoice lines).
SEED_TAXES = [
    {"code": "ppn12_dpp", "name": "12% (Non-Luxury Good)", "description": "Barang / jasa selain barang mewah (DPP 11/12)",
     "tax_use": "sale", "scope": "", "amount": 12, "base": "dpp_11_12", "invoice_label": "12%"},
    {"code": "ppn12_lux", "name": "12%", "description": "Barang mewah",
     "tax_use": "sale", "scope": "goods", "amount": 12, "base": "full", "invoice_label": "12%"},
    {"code": "ppn11", "name": "11%", "description": "PPN tarif lama",
     "tax_use": "sale", "scope": "", "amount": 11, "base": "full", "invoice_label": "11%"},
    {"code": "ppn0_export", "name": "0% EKSPOR", "description": "Ekspor",
     "tax_use": "sale", "scope": "", "amount": 0, "base": "full", "invoice_label": "0%"},
    {"code": "ppn0_exempt", "name": "0% DIBEBASKAN", "description": "PPN dibebaskan",
     "tax_use": "sale", "scope": "", "amount": 0, "base": "full", "invoice_label": "0%"},
    {"code": "ppn12_dpp_in", "name": "12% (Non-Luxury Good)", "description": "PPN Masukan selain barang mewah (DPP 11/12)",
     "tax_use": "purchase", "scope": "", "amount": 12, "base": "dpp_11_12", "invoice_label": "12%"},
    {"code": "ppn11_in", "name": "11%", "description": "PPN Masukan tarif lama",
     "tax_use": "purchase", "scope": "", "amount": 11, "base": "full", "invoice_label": "11%"},
    {"code": "ppn0_exempt_in", "name": "0% DIBEBASKAN", "description": "PPN Masukan dibebaskan",
     "tax_use": "purchase", "scope": "", "amount": 0, "base": "full", "invoice_label": "0%"}
]


def tax_rate(tax):
    # Effective rate as a fraction: 12% on DPP 11/12 -> 0.11
    return round((tax.get("amount") or 0) / 100.0 * TAX_BASE_FACTORS.get(tax.get("base", "full"), 1.0), 6)
# end def


# ---------------------------------------------------------------------------
# Nomor dokumen (Konfigurasi > Pengaturan), stored in db_config. Tokens in a
# prefix: {TAHUN} = 2026, {THN} = 26, {BULAN} = 11.
# ---------------------------------------------------------------------------

SEQUENCES = [
    {"key": "out_invoice", "label": "Faktur Pelanggan", "prefix": "INV/{TAHUN}/", "padding": 5},
    {"key": "out_refund", "label": "Nota Kredit", "prefix": "RINV/{TAHUN}/", "padding": 5},
    {"key": "in_invoice", "label": "Tagihan Vendor", "prefix": "BILL/{TAHUN}/{BULAN}/", "padding": 4}
]
SEQUENCE_CONFIG = "accounting_sequences"
PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9/_.\-{}]{1,30}$")
PREFIX_TOKENS = ["{TAHUN}", "{THN}", "{BULAN}"]


NUMBER_PATTERN = re.compile(r"^(.*?)(\d+)$")


def split_number(number):
    # "INV/2026/00004" -> ("INV/2026/", "00004")
    match = NUMBER_PATTERN.match(number or "")
    if match == None:
        return number or "", ""
    # end if
    return match.group(1), match.group(2)
# end def


def render_prefix(prefix, day):
    return prefix.replace("{TAHUN}", day.strftime("%Y")).replace("{THN}", day.strftime("%y")).replace("{BULAN}", day.strftime("%m"))
# end def

EFAKTUR_CODES = [
    {"key": "01", "label": "01 Kepada pihak yang bukan pemungut PPN"},
    {"key": "02", "label": "02 Kepada pemungut bendaharawan"},
    {"key": "03", "label": "03 Kepada pemungut selain bendaharawan"},
    {"key": "04", "label": "04 DPP Nilai Lain"},
    {"key": "07", "label": "07 Penyerahan yang PPN-nya tidak dipungut"},
    {"key": "08", "label": "08 Penyerahan yang PPN-nya dibebaskan"}
]
EFAKTUR_KEYS = [c["key"] for c in EFAKTUR_CODES]

INVOICE_TEXT_FIELDS = ["customer_ref", "payment_ref", "notes"]
MAX_LINES = 200
NOTES_MAX = 5000

MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

INVOICE_LOG_LABELS = {
    "number": "Nomor",
    "partner_name": "Pelanggan",
    "invoice_date": "Tanggal Faktur",
    "payment_term": "Termin Pembayaran",
    "due_date": "Batas Waktu",
    "customer_ref": "Referensi Pelanggan",
    "amount_untaxed": "Jumlah Sebelum Pajak",
    "amount_total": "Total"
}


def _today():
    return database._get_current_datetime(hours=config.JKTA_TZ).date()
# end def


def today_iso():
    return _today().strftime("%Y-%m-%d")
# end def


def _parse_date(value):
    try:
        return datetime.datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None
    # end try
# end def


def _to_number(value):
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None
    # end try
# end def


def _term_days(term):
    # "30 Hari" -> 30, "Langsung" -> 0, "" -> None (no term)
    term = (term or "").strip()
    if term == "":
        return None
    # end if
    if term == "Langsung":
        return 0
    # end if
    try:
        return int(term.split(" ")[0])
    except Exception:
        return None
    # end try
# end def


def short_date(value, today=None):
    # "2026-11-06" -> "6 Nov" (year added when it is not this year)
    day = _parse_date(value)
    if day == None:
        return ""
    # end if
    if today == None:
        today = _today()
    # end if
    text = str(day.day) + " " + MONTHS_SHORT[day.month - 1]
    if day.year != today.year:
        text = text + " " + str(day.year)
    # end if
    return text
# end def


def due_label(value, today=None):
    # Relative due date for open invoices: ("Dalam 4 minggu", "") or
    # ("Lewat 3 hari", "late").
    day = _parse_date(value)
    if day == None:
        return "", ""
    # end if
    if today == None:
        today = _today()
    # end if
    diff = (day - today).days
    if diff == 0:
        return "Hari ini", "soon"
    # end if
    if diff == 1:
        return "Besok", "soon"
    # end if
    if diff < 0:
        return "Lewat " + str(-diff) + " hari", "late"
    # end if
    if diff >= 14 and diff % 7 == 0:
        return "Dalam " + str(diff // 7) + " minggu", ""
    # end if
    return "Dalam " + str(diff) + " hari", ""
# end def


class accounting_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def page(self, slug):
        return PAGES.get(slug)
    # end def

    def dashboard_journals(self):
        unpaid = self.unpaid_invoices()
        out = []
        for journal in JOURNALS:
            card = dict(journal)
            card["amount"] = rupiah(0)
            if journal["code"] == "INV":
                card["amount"] = rupiah(unpaid["amount"])
                card["count"] = unpaid["count"]
            # end if
            out.append(card)
        # end for
        return out
    # end def

    # ------------------------------------------------------------------
    # Konfigurasi > Pajak
    # ------------------------------------------------------------------

    def ensure_default_taxes(self):
        if self.mgdDB.db_tax.count_documents({}, limit=1) > 0:
            return
        # end if
        seq = 0
        for seed in SEED_TAXES:
            seq = seq + 10
            if self.mgdDB.db_tax.find_one({"code": seed["code"]}, {"_id": 1}) != None:
                continue
            # end if
            rec = database.new(self.mgdDB, "db_tax")
            for key in seed:
                rec.put(key, seed[key])
            # end for
            rec.put("active", True)
            rec.put("sequence", seq)
            rec.insert()
        # end for
    # end def

    def _tax_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        doc["tax_use_label"] = TAX_USES.get(doc.get("tax_use", ""), "")
        doc["scope_label"] = TAX_SCOPES.get(doc.get("scope", ""), "")
        doc["rate"] = tax_rate(doc)
        doc["option_label"] = doc.get("name", "")
        if doc.get("description"):
            doc["option_label"] = doc["option_label"] + " — " + doc["description"]
        # end if
        return doc
    # end def

    def sale_taxes(self, include_codes=None):
        # Active sales taxes for the invoice line dropdown, plus any inactive
        # code already used on the invoice so old lines still display.
        self.ensure_default_taxes()
        query = {"is_deleted": False, "tax_use": "sale", "active": True}
        if include_codes:
            query = {"is_deleted": False, "tax_use": "sale", "$or": [{"active": True}, {"code": {"$in": list(include_codes)}}]}
        # end if
        projection = {"code": 1, "name": 1, "description": 1, "amount": 1, "base": 1, "invoice_label": 1, "active": 1, "tax_use": 1, "scope": 1}
        out = []
        for doc in self.mgdDB.db_tax.find(query, projection).sort([("sequence", 1), ("_id", 1)]).limit(200):
            out.append(self._tax_public(doc))
        # end for
        return out
    # end def

    def tax_map(self, codes):
        # {code: tax} for the codes used on an invoice (one $in query).
        codes = [c for c in set(codes) if c]
        if len(codes) == 0:
            return {}
        # end if
        out = {}
        for doc in self.mgdDB.db_tax.find({"code": {"$in": codes}, "is_deleted": False}):
            out[doc["code"]] = self._tax_public(doc)
        # end for
        return out
    # end def

    def _tax_query(self, tax_use, q):
        query = {"is_deleted": False}
        if tax_use in TAX_USES:
            query["tax_use"] = tax_use
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
                {"invoice_label": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def page_taxes(self, tax_use, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        self.ensure_default_taxes()
        query = self._tax_query(tax_use, q)
        total = self.mgdDB.db_tax.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_tax.find(query).sort(
            [("sequence", 1), ("_id", 1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._tax_public(rec))
        # end for
        pager["taxes"] = out
        return pager
    # end def

    def get_tax(self, code):
        doc = self.mgdDB.db_tax.find_one({"code": (code or "").strip(), "is_deleted": False})
        if doc == None:
            return None
        # end if
        return self._tax_public(doc)
    # end def

    def _tax_fields(self, params):
        name = (params.get("name") or "").strip()
        if name == "":
            return None, {"status": "ERROR", "desc": "Nama pajak wajib diisi"}
        # end if
        tax_use = (params.get("tax_use") or "").strip()
        if tax_use not in TAX_USES:
            return None, {"status": "ERROR", "desc": "Tipe pajak harus Penjualan atau Pembelian"}
        # end if
        scope = (params.get("scope") or "").strip()
        if scope not in TAX_SCOPES:
            return None, {"status": "ERROR", "desc": "Lingkup pajak tidak valid"}
        # end if
        base = (params.get("base") or "full").strip()
        if base not in TAX_BASE_FACTORS:
            return None, {"status": "ERROR", "desc": "Dasar pengenaan pajak tidak valid"}
        # end if
        amount = _to_number(params.get("amount") or "0")
        if amount == None or amount < 0 or amount > 100:
            return None, {"status": "ERROR", "desc": "Persentase pajak harus antara 0 dan 100"}
        # end if
        fields = {
            "name": name[:80],
            "description": (params.get("description") or "").strip()[:200],
            "tax_use": tax_use,
            "scope": scope,
            "amount": round(amount, 4),
            "base": base,
            "invoice_label": (params.get("invoice_label") or "").strip()[:40] or (str(round(amount, 4)).rstrip("0").rstrip(".") + "%"),
            "active": params.get("active") == "1"
        }
        return fields, None
    # end def

    def create_tax(self, params):
        fields, err = self._tax_fields(params)
        if err != None:
            return err
        # end if
        seq = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": "TAX"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )["seq"]
        code = "tax" + str(seq)
        last = self.mgdDB.db_tax.find_one({"is_deleted": False}, {"sequence": 1}, sort=[("sequence", -1)])
        rec = database.new(self.mgdDB, "db_tax")
        rec.put("code", code)
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.put("sequence", ((last or {}).get("sequence") or 0) + 10)
        rec.insert()
        return {"status": "SUCCESS", "desc": "Pajak dibuat", "code": code}
    # end def

    def update_tax(self, code, params):
        tax = self.get_tax(code)
        if tax == None:
            return {"status": "ERROR", "desc": "Pajak tidak ditemukan"}
        # end if
        fields, err = self._tax_fields(params)
        if err != None:
            return err
        # end if
        self.mgdDB.db_tax.update_one({"code": tax["code"], "is_deleted": False}, {"$set": fields})
        return {"status": "SUCCESS", "desc": "Pajak disimpan"}
    # end def

    def toggle_tax(self, code):
        tax = self.get_tax(code)
        if tax == None:
            return {"status": "ERROR", "desc": "Pajak tidak ditemukan"}
        # end if
        active = not tax.get("active", True)
        self.mgdDB.db_tax.update_one({"code": tax["code"], "is_deleted": False}, {"$set": {"active": active}})
        desc = "Pajak " + tax["name"] + (" diaktifkan" if active else " dinonaktifkan")
        return {"status": "SUCCESS", "desc": desc, "active": active}
    # end def

    # ------------------------------------------------------------------
    # Konfigurasi > Pengaturan (nomor dokumen)
    # ------------------------------------------------------------------

    def get_sequences(self):
        # Settings page rows: saved prefix / digits plus the next number.
        today = _today()
        out = self.get_sequences_raw()
        for row in out:
            row["preview"] = self.preview_number(row["key"], today, row)
        # end for
        return out
    # end def

    def _sequence(self, key):
        for row in self.get_sequences_raw():
            if row["key"] == key:
                return row
            # end if
        # end for
        return None
    # end def

    def get_sequences_raw(self):
        doc = self.mgdDB.db_config.find_one({"name": SEQUENCE_CONFIG, "is_deleted": False}, {"data": 1})
        saved = (doc or {}).get("data") or {}
        out = []
        for seq in SEQUENCES:
            row = dict(seq)
            stored = saved.get(seq["key"]) or {}
            row["prefix"] = stored.get("prefix") or seq["prefix"]
            row["padding"] = stored.get("padding") or seq["padding"]
            out.append(row)
        # end for
        return out
    # end def

    def save_sequences(self, params):
        data = {}
        for seq in SEQUENCES:
            prefix = (params.get("prefix_" + seq["key"]) or "").strip()
            padding = _to_number(params.get("padding_" + seq["key"]) or "")
            if prefix == "" or not PREFIX_PATTERN.match(prefix):
                return {"status": "ERROR", "desc": "Prefix " + seq["label"] + " hanya boleh huruf, angka, / - _ . dan token {TAHUN} {THN} {BULAN} (maks. 30 karakter)"}
            # end if
            leftover = prefix
            for token in PREFIX_TOKENS:
                leftover = leftover.replace(token, "")
            # end for
            if "{" in leftover or "}" in leftover:
                return {"status": "ERROR", "desc": "Prefix " + seq["label"] + " berisi token yang tidak dikenal"}
            # end if
            if padding == None or int(padding) != padding or padding < 3 or padding > 8:
                return {"status": "ERROR", "desc": "Jumlah digit " + seq["label"] + " harus 3 sampai 8"}
            # end if
            data[seq["key"]] = {"prefix": prefix, "padding": int(padding)}
        # end for
        existing = self.mgdDB.db_config.find_one({"name": SEQUENCE_CONFIG, "is_deleted": False}, {"_id": 1})
        if existing == None:
            rec = database.new(self.mgdDB, "db_config")
            rec.put("name", SEQUENCE_CONFIG)
            rec.put("config_type", "ACCOUNTING")
            rec.put("desc", "Prefix dan jumlah digit nomor dokumen akuntansi")
            rec.put("data", data)
            rec.insert()
        else:
            self.mgdDB.db_config.update_one({"_id": existing["_id"]}, {"$set": {"data": data}})
        # end if
        return {"status": "SUCCESS", "desc": "Pengaturan nomor dokumen disimpan"}
    # end def

    def _highest_seq(self, prefix):
        # Highest sequence already used with this exact prefix (so a new or
        # renamed counter never re-issues an existing number).
        pattern = "^" + re.escape(prefix) + "[0-9]+$"
        highest = 0
        for doc in self.mgdDB.db_invoice.find({"number": {"$regex": pattern}}, {"number": 1}):
            try:
                highest = max(highest, int(doc["number"][len(prefix):]))
            except Exception:
                pass
            # end try
        # end for
        return highest
    # end def

    def preview_number(self, key, day=None, row=None):
        if day == None:
            day = _today()
        # end if
        if row == None:
            row = self._sequence(key)
        # end if
        prefix = render_prefix(row["prefix"], day)
        counter = self.mgdDB.db_code_counter.find_one({"counter_key": "SEQ:" + prefix}, {"seq": 1})
        current = counter["seq"] if counter != None else self._highest_seq(prefix)
        return prefix + str(current + 1).zfill(row["padding"])
    # end def

    def next_number(self, key, day):
        # Atomic: concurrent creates never get the same number.
        row = self._sequence(key)
        prefix = render_prefix(row["prefix"], day)
        counter_key = "SEQ:" + prefix
        if self.mgdDB.db_code_counter.find_one({"counter_key": counter_key}, {"_id": 1}) == None:
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": counter_key},
                {"$max": {"seq": self._highest_seq(prefix)}},
                upsert=True
            )
        # end if
        for attempt in range(5):
            rec = self.mgdDB.db_code_counter.find_one_and_update(
                {"counter_key": counter_key},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=pymongo.ReturnDocument.AFTER
            )
            number = prefix + str(rec["seq"]).zfill(row["padding"])
            if self.mgdDB.db_invoice.find_one({"number": number}, {"_id": 1}) == None:
                return number
            # end if
        # end for
        return number
    # end def

    # ------------------------------------------------------------------
    # Faktur: reads
    # ------------------------------------------------------------------

    def unpaid_invoices(self):
        pipeline = [
            {"$match": {
                "is_deleted": False, "move_type": "out_invoice",
                "state": STATE_POSTED, "amount_residual": {"$gt": 0}
            }},
            {"$group": {"_id": None, "amount": {"$sum": "$amount_residual"}, "count": {"$sum": 1}}}
        ]
        for row in self.mgdDB.db_invoice.aggregate(pipeline):
            return {"amount": row["amount"], "count": row["count"]}
        # end for
        return {"amount": 0, "count": 0}
    # end def

    def _invoice_query(self, state, q):
        query = {"is_deleted": False, "move_type": "out_invoice"}
        state = (state or "").strip().upper()
        if state in STATE_LABELS:
            query["state"] = state
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"number": {"$regex": pattern, "$options": "i"}},
                {"partner_name": {"$regex": pattern, "$options": "i"}},
                {"customer_ref": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def _invoice_public(self, doc, today):
        doc["id"] = str(doc.pop("_id"))
        state = doc.get("state", STATE_DRAFT)
        doc["state_label"] = STATE_LABELS.get(state, state)
        doc["state_class"] = state.lower()
        pay_state = doc.get("payment_state") or PAY_NOT_PAID
        if state == STATE_POSTED and pay_state != PAY_NOT_PAID:
            doc["state_label"] = PAYMENT_STATE_LABELS[pay_state]
            doc["state_class"] = pay_state
        # end if
        doc["number_display"] = doc.get("number") or "/"
        doc["number_prefix"], doc["number_digits"] = split_number(doc.get("number", ""))
        doc["date_short"] = short_date(doc.get("invoice_date", ""), today)
        label, cls = "", ""
        if state != STATE_CANCEL and (doc.get("amount_residual") or 0) > 0:
            label, cls = due_label(doc.get("due_date", ""), today)
        # end if
        doc["due_text"] = label
        doc["due_class"] = cls
        doc["untaxed_fmt"] = rupiah(doc.get("amount_untaxed", 0))
        doc["tax_fmt"] = rupiah(doc.get("amount_tax", 0))
        doc["total_fmt"] = rupiah(doc.get("amount_total", 0))
        doc["residual_fmt"] = rupiah(doc.get("amount_residual", 0))
        return doc
    # end def

    def page_invoices(self, state, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        query = self._invoice_query(state, q)
        projection = {
            "seq": 1, "number": 1, "state": 1, "partner_id": 1, "partner_name": 1,
            "invoice_date": 1, "due_date": 1, "customer_ref": 1, "posted_at": 1,
            "amount_untaxed": 1, "amount_tax": 1, "amount_total": 1, "amount_residual": 1,
            "payment_state": 1
        }
        total = self.mgdDB.db_invoice.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_invoice.find(query, projection).sort(
            [("invoice_date", -1), ("rec_timestamp", -1), ("_id", -1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        today = _today()
        out = []
        for rec in recs:
            out.append(self._invoice_public(rec, today))
        # end for
        sums = {"untaxed": 0, "total": 0, "residual": 0}
        if total > 0:
            pipeline = [
                {"$match": query},
                {"$group": {
                    "_id": None,
                    "untaxed": {"$sum": "$amount_untaxed"},
                    "total": {"$sum": "$amount_total"},
                    "residual": {"$sum": "$amount_residual"}
                }}
            ]
            for row in self.mgdDB.db_invoice.aggregate(pipeline):
                sums = row
            # end for
        # end if
        pager["invoices"] = out
        pager["sum_untaxed"] = rupiah(sums["untaxed"])
        pager["sum_total"] = rupiah(sums["total"])
        pager["sum_residual"] = rupiah(sums["residual"])
        return pager
    # end def

    def _next_seq(self):
        # Running URL number 1, 2, 3 ... (atomic). Seeded from the highest
        # seq already stored so it never collides with existing invoices.
        if self.mgdDB.db_code_counter.find_one({"counter_key": SEQ_ID_KEY}, {"_id": 1}) == None:
            top = self.mgdDB.db_invoice.find_one({"seq": {"$gt": 0}}, {"seq": 1}, sort=[("seq", -1)])
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": SEQ_ID_KEY},
                {"$max": {"seq": (top or {}).get("seq") or 0}},
                upsert=True
            )
        # end if
        rec = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": SEQ_ID_KEY},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )
        return rec["seq"]
    # end def

    def _ensure_identity(self, doc):
        # Older invoices may miss seq (and very old drafts the number):
        # give them one the first time they are opened. Returns the seq.
        update = {}
        if not doc.get("seq"):
            update["seq"] = self._next_seq()
        # end if
        if (doc.get("number") or "") == "":
            day = _parse_date(doc.get("invoice_date")) or _today()
            update["number"] = self.next_number("out_invoice", day)
        # end if
        if len(update) > 0:
            query = {"_id": doc["_id"]}
            if "seq" in update:
                # missing or 0 only: a parallel request may have set it already
                query["seq"] = {"$in": [0, None]}
            # end if
            self.mgdDB.db_invoice.update_one(query, {"$set": update})
            fresh = self.mgdDB.db_invoice.find_one({"_id": doc["_id"]}, {"seq": 1})
            return fresh.get("seq")
        # end if
        return doc["seq"]
    # end def

    def resolve_ref(self, ref):
        # Old URLs (/invoices/INV/2026/00004 or /invoices/<internal id>)
        # -> the running seq for the new URL, or None.
        ref = (ref or "").strip()
        if ref == "":
            return None
        # end if
        projection = {"_id": 1, "seq": 1, "number": 1, "invoice_date": 1}
        base_query = {"is_deleted": False, "move_type": "out_invoice"}
        doc = self.mgdDB.db_invoice.find_one(dict(base_query, number=ref), projection)
        if doc == None and ObjectId.is_valid(ref):
            doc = self.mgdDB.db_invoice.find_one(dict(base_query, _id=ObjectId(ref)), projection)
        # end if
        if doc == None:
            return None
        # end if
        return self._ensure_identity(doc)
    # end def

    def partner_card(self, partner_id):
        # Customer block for the printed invoice (one projected read).
        try:
            oid = ObjectId(partner_id)
        except Exception:
            return {}
        # end try
        doc = self.mgdDB.db_contact.find_one(
            {"_id": oid},
            {"name": 1, "company_name": 1, "address": 1, "street2": 1, "city": 1,
             "province": 1, "postal_code": 1, "country": 1, "email": 1, "phone": 1, "tax_id": 1}
        )
        if doc == None:
            return {}
        # end if
        doc.pop("_id", None)
        return doc
    # end def

    def partner_email(self, partner_id):
        return self.partner_card(partner_id).get("email", "")
    # end def

    def get_invoice_by_seq(self, seq):
        doc = self.mgdDB.db_invoice.find_one(
            {"seq": seq, "is_deleted": False, "move_type": "out_invoice"}, {"_id": 1}
        )
        if doc == None:
            return None
        # end if
        return self.get_invoice(str(doc["_id"]))
    # end def

    def get_invoice(self, invoice_id):
        try:
            oid = ObjectId(invoice_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_invoice.find_one({"_id": oid, "is_deleted": False, "move_type": "out_invoice"})
        if doc == None:
            return None
        # end if
        inv = self._invoice_public(doc, _today())
        taxes = self.tax_map([line.get("tax", "") for line in inv.get("lines", [])])
        for line in inv.get("lines", []):
            line["account_label"] = REVENUE_ACCOUNT_LABELS.get(line.get("account", ""), line.get("account", ""))
            line["tax_label"] = (taxes.get(line.get("tax", "")) or {}).get("name", "")
            line["subtotal_fmt"] = rupiah(line.get("subtotal", 0))
            line["price_fmt"] = rupiah(line.get("price_unit", 0))
        # end for
        for pay in inv.get("payments", []):
            pay["amount_fmt"] = rupiah(pay.get("amount", 0))
            pay["date_short"] = short_date(pay.get("date", ""))
        # end for
        inv["paid_fmt"] = rupiah(round((inv.get("amount_total") or 0) - (inv.get("amount_residual") or 0), 2))
        inv["residual"] = inv.get("amount_residual") or 0
        return inv
    # end def

    def journal_items(self, inv):
        # Item Jurnal tab: revenue per line (credit), PPN Keluaran per tax
        # (credit) and the receivable (debit). Built from the saved lines.
        rows = []
        taxes = {}
        for line in inv.get("lines", []):
            rows.append({
                "account": REVENUE_ACCOUNT_LABELS.get(line.get("account", ""), line.get("account", "")),
                "label": line.get("product", ""),
                "debit": 0, "credit": line.get("subtotal", 0)
            })
            if line.get("tax_amount", 0) > 0:
                key = line.get("tax", "")
                taxes[key] = round(taxes.get(key, 0) + line["tax_amount"], 2)
            # end if
        # end for
        tax_info = self.tax_map(list(taxes.keys()))
        for key in taxes:
            label = (tax_info.get(key) or {}).get("name", key)
            rows.append({"account": ACCOUNT_TAX_OUT, "label": label, "debit": 0, "credit": taxes[key]})
        # end for
        total = inv.get("amount_total", 0)
        if total > 0:
            rows.append({
                "account": ACCOUNT_RECEIVABLE,
                "label": inv.get("customer_ref") or inv.get("number") or "Faktur",
                "debit": total, "credit": 0
            })
        # end if
        debit = 0
        credit = 0
        for row in rows:
            debit = debit + row["debit"]
            credit = credit + row["credit"]
            row["debit_fmt"] = rupiah(row["debit"])
            row["credit_fmt"] = rupiah(row["credit"])
        # end for
        return {"rows": rows, "debit_fmt": rupiah(debit), "credit_fmt": rupiah(credit)}
    # end def

    # ------------------------------------------------------------------
    # Faktur: writes
    # ------------------------------------------------------------------

    def _compute_lines(self, raw_lines, keep_codes=None):
        # raw_lines: [{product, account, quantity, price_unit, tax}] as text.
        # Returns (lines, totals, err); every amount is recomputed here.
        # Allowed taxes: active sales taxes, plus codes already on the
        # invoice (keep_codes) so a later-deactivated tax does not block it.
        allowed = {}
        for tax in self.sale_taxes(keep_codes):
            allowed[tax["code"]] = tax["rate"]
        # end for
        allowed[""] = 0.0
        lines = []
        untaxed = 0.0
        tax_total = 0.0
        for raw in raw_lines:
            product = (raw.get("product") or "").strip()
            qty_text = (raw.get("quantity") or "").strip()
            price_text = (raw.get("price_unit") or "").strip()
            if product == "" and qty_text == "" and price_text == "":
                continue
            # end if
            if product == "":
                return None, None, {"status": "ERROR", "desc": "Setiap baris faktur wajib punya nama produk / layanan"}
            # end if
            quantity = _to_number(qty_text or "1")
            price = _to_number(price_text or "0")
            if quantity == None or quantity <= 0:
                return None, None, {"status": "ERROR", "desc": "Kuantitas baris \"" + product + "\" harus lebih dari 0"}
            # end if
            if price == None or price < 0:
                return None, None, {"status": "ERROR", "desc": "Harga baris \"" + product + "\" tidak valid"}
            # end if
            account = (raw.get("account") or REVENUE_ACCOUNTS[0]["key"]).strip()
            if account not in REVENUE_ACCOUNT_LABELS:
                return None, None, {"status": "ERROR", "desc": "Akun baris \"" + product + "\" tidak valid"}
            # end if
            tax = (raw.get("tax") or "").strip()
            if tax not in allowed:
                return None, None, {"status": "ERROR", "desc": "Pajak baris \"" + product + "\" tidak valid atau tidak aktif"}
            # end if
            subtotal = round(quantity * price, 2)
            tax_amount = round(subtotal * allowed[tax], 2)
            lines.append({
                "product": product[:300],
                "account": account,
                "quantity": quantity,
                "price_unit": price,
                "tax": tax,
                "subtotal": subtotal,
                "tax_amount": tax_amount
            })
            untaxed = untaxed + subtotal
            tax_total = tax_total + tax_amount
        # end for
        if len(lines) > MAX_LINES:
            return None, None, {"status": "ERROR", "desc": "Maksimal " + str(MAX_LINES) + " baris per faktur"}
        # end if
        untaxed = round(untaxed, 2)
        tax_total = round(tax_total, 2)
        totals = {
            "amount_untaxed": untaxed,
            "amount_tax": tax_total,
            "amount_total": round(untaxed + tax_total, 2)
        }
        return lines, totals, None
    # end def

    def _invoice_fields(self, params, raw_lines, keep_codes=None):
        partner_id = (params.get("partner_id") or "").strip()
        partner_name = ""
        if partner_id != "":
            try:
                oid = ObjectId(partner_id)
            except Exception:
                return None, {"status": "ERROR", "desc": "Pelanggan tidak valid"}
            # end try
            partner = self.mgdDB.db_contact.find_one({"_id": oid, "is_deleted": False}, {"name": 1})
            if partner == None:
                return None, {"status": "ERROR", "desc": "Pelanggan tidak ditemukan"}
            # end if
            partner_name = partner.get("name", "")
        # end if
        invoice_date = _parse_date(params.get("invoice_date"))
        if invoice_date == None:
            invoice_date = _today()
        # end if
        payment_term = (params.get("payment_term") or "").strip()
        if payment_term != "" and payment_term not in PAYMENT_TERMS:
            return None, {"status": "ERROR", "desc": "Termin pembayaran tidak valid"}
        # end if
        days = _term_days(payment_term)
        if days != None:
            due_date = invoice_date + datetime.timedelta(days=days)
        else:
            due_date = _parse_date(params.get("due_date")) or invoice_date
        # end if
        if due_date < invoice_date:
            return None, {"status": "ERROR", "desc": "Batas waktu tidak boleh sebelum tanggal faktur"}
        # end if
        delivery = _parse_date(params.get("delivery_date"))
        efaktur = (params.get("efaktur_code") or "").strip()
        if efaktur != "" and efaktur not in EFAKTUR_KEYS:
            return None, {"status": "ERROR", "desc": "Kode transaksi e-Faktur tidak valid"}
        # end if
        fiscal = (params.get("fiscal_position") or "").strip()
        if fiscal != "" and fiscal not in FISCAL_POSITIONS:
            return None, {"status": "ERROR", "desc": "Posisi fiskal tidak valid"}
        # end if
        salesperson_id = (params.get("salesperson_id") or "").strip()
        if salesperson_id != "":
            try:
                found = self.mgdDB.db_user.find_one({"_id": ObjectId(salesperson_id), "is_deleted": False}, {"_id": 1})
            except Exception:
                found = None
            # end try
            if found == None:
                return None, {"status": "ERROR", "desc": "Penjual tidak ditemukan"}
            # end if
        # end if
        lines, totals, err = self._compute_lines(raw_lines, keep_codes)
        if err != None:
            return None, err
        # end if
        fields = {
            "partner_id": partner_id,
            "partner_name": partner_name,
            "invoice_date": invoice_date.strftime("%Y-%m-%d"),
            "payment_term": payment_term,
            "due_date": due_date.strftime("%Y-%m-%d"),
            "delivery_date": delivery.strftime("%Y-%m-%d") if delivery != None else "",
            "efaktur_code": efaktur,
            "fiscal_position": fiscal,
            "salesperson_id": salesperson_id,
            "lines": lines
        }
        for key in INVOICE_TEXT_FIELDS:
            fields[key] = (params.get(key) or "").strip()
        # end for
        if len(fields["notes"]) > NOTES_MAX:
            return None, {"status": "ERROR", "desc": "Syarat dan ketentuan maksimal " + str(NOTES_MAX) + " karakter"}
        # end if
        for key in totals:
            fields[key] = totals[key]
        # end for
        fields["amount_residual"] = totals["amount_total"]
        return fields, None
    # end def

    def _log_values(self, inv):
        out = {}
        for key in INVOICE_LOG_LABELS:
            out[key] = inv.get(key, "")
        # end for
        out["invoice_date"] = short_date(out["invoice_date"])
        out["due_date"] = short_date(out["due_date"])
        out["amount_untaxed"] = rupiah(inv.get("amount_untaxed", 0))
        out["amount_total"] = rupiah(inv.get("amount_total", 0))
        return out
    # end def

    def create_invoice(self, params, raw_lines, actor=None):
        fields, err = self._invoice_fields(params, raw_lines)
        if err != None:
            return err
        # end if
        number = self.next_number("out_invoice", _parse_date(fields["invoice_date"]) or _today())
        rec = database.new(self.mgdDB, "db_invoice")
        rec.put("move_type", "out_invoice")
        rec.put("state", STATE_DRAFT)
        rec.put("number", number)
        seq = self._next_seq()
        rec.put("seq", seq)
        rec.put("payments", [])
        rec.put("payment_state", PAY_NOT_PAID)
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        saved = rec.get()
        invoice_id = str(saved.get("_id", ""))
        record_log_proc().log_create(LOG_MODEL, invoice_id, actor, "Faktur " + number + " dibuat")
        return {"status": "SUCCESS", "desc": "Faktur " + number + " disimpan", "id": invoice_id, "number": number, "seq": seq}
    # end def

    def number_taken(self, number, exclude_id=""):
        # Another live invoice already uses this number -> its seq, else None.
        query = {"number": number, "is_deleted": False}
        if exclude_id != "":
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        # end if
        doc = self.mgdDB.db_invoice.find_one(query, {"seq": 1})
        if doc == None:
            return None
        # end if
        return doc.get("seq") or 0
    # end def

    def check_number(self, inv, digits):
        # Live check for the number field on a Draft: what the number
        # would become and whether another invoice already has it.
        number, err = self._compose_number(inv, digits)
        if err != None:
            return {"status": "ERROR", "desc": err["desc"], "exists": False}
        # end if
        seq = None
        if number != inv["number"]:
            seq = self.number_taken(number, inv["id"])
        # end if
        return {"status": "SUCCESS", "number": number, "exists": seq != None, "seq": seq}
    # end def

    def _compose_number(self, inv, digits):
        # INV/2026/00004 + "7" -> INV/2026/00007. Only the trailing number
        # can change; the prefix stays as issued. Short input is zero-padded
        # to the current width.
        prefix, current = split_number(inv.get("number", ""))
        digits = (digits or "").strip()
        if digits == "" or digits == current:
            return inv.get("number", ""), None
        # end if
        if not digits.isdigit() or len(digits) > 10:
            return None, {"status": "ERROR", "desc": "Nomor urut faktur hanya boleh angka (maks. 10 digit)"}
        # end if
        if int(digits) == 0:
            return None, {"status": "ERROR", "desc": "Nomor urut faktur harus lebih dari 0"}
        # end if
        return prefix + digits.zfill(len(current)), None
    # end def

    def _edited_number(self, inv, digits):
        number, err = self._compose_number(inv, digits)
        if err != None:
            return None, err
        # end if
        if number != inv.get("number", "") and self.number_taken(number, inv["id"]) != None:
            return None, {"status": "ERROR", "desc": "Nomor " + number + " sudah dipakai faktur lain. Pilih nomor lain."}
        # end if
        return number, None
    # end def

    def update_invoice(self, invoice_id, params, raw_lines, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Faktur tidak ditemukan"}
        # end if
        if inv.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya faktur Draft yang bisa diubah. Reset ke Draft terlebih dulu."}
        # end if
        keep_codes = [line.get("tax", "") for line in inv.get("lines", [])]
        fields, err = self._invoice_fields(params, raw_lines, keep_codes)
        if err != None:
            return err
        # end if
        number, err = self._edited_number(inv, params.get("number_seq"))
        if err != None:
            return err
        # end if
        fields["number"] = number
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(inv["id"]), "state": STATE_DRAFT, "is_deleted": False},
            {"$set": fields}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Faktur sudah tidak Draft, muat ulang halaman"}
        # end if
        record_log_proc().log_changes(LOG_MODEL, inv["id"], self._log_values(inv), self._log_values(fields), INVOICE_LOG_LABELS, actor)
        return {"status": "SUCCESS", "desc": "Faktur disimpan"}
    # end def

    def confirm_invoice(self, invoice_id, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Faktur tidak ditemukan"}
        # end if
        if inv.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya faktur Draft yang bisa dikonfirmasi"}
        # end if
        if inv.get("partner_id", "") == "":
            return {"status": "ERROR", "desc": "Pilih pelanggan sebelum konfirmasi"}
        # end if
        if len(inv.get("lines", [])) == 0 or inv.get("amount_total", 0) <= 0:
            return {"status": "ERROR", "desc": "Faktur harus punya minimal satu baris dengan total lebih dari 0"}
        # end if
        number = inv.get("number") or self.next_number("out_invoice", _parse_date(inv.get("invoice_date")) or _today())
        now = database._get_current_datetime(hours=config.JKTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(inv["id"]), "state": STATE_DRAFT, "is_deleted": False},
            {"$set": {"state": STATE_POSTED, "number": number, "posted_at": now}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Faktur sudah dikonfirmasi"}
        # end if
        log = record_log_proc()
        log.log_event(LOG_MODEL, inv["id"], "Faktur telah divalidasi", actor)
        log.log_changes(
            LOG_MODEL, inv["id"],
            {"number": inv.get("number", ""), "state": STATE_LABELS[STATE_DRAFT]},
            {"number": number, "state": STATE_LABELS[STATE_POSTED]},
            {"number": "Nomor", "state": "Status"}, actor
        )
        return {"status": "SUCCESS", "desc": "Faktur " + number + " dikonfirmasi"}
    # end def

    def _set_state(self, invoice_id, from_states, to_state, actor, event):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Faktur tidak ditemukan"}
        # end if
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(inv["id"]), "state": {"$in": from_states}, "is_deleted": False},
            {"$set": {"state": to_state}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Status faktur tidak bisa diubah dari " + inv["state_label"]}
        # end if
        record_log_proc().log_changes(
            LOG_MODEL, inv["id"],
            {"state": inv["state_label"]}, {"state": STATE_LABELS[to_state]},
            {"state": "Status"}, actor
        )
        return {"status": "SUCCESS", "desc": event}
    # end def

    def reset_invoice(self, invoice_id, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv != None and len(inv.get("payments", [])) > 0:
            return {"status": "ERROR", "desc": "Faktur yang sudah ada pembayarannya tidak bisa dikembalikan ke Draft"}
        # end if
        return self._set_state(invoice_id, [STATE_POSTED, STATE_CANCEL], STATE_DRAFT, actor, "Faktur dikembalikan ke Draft")
    # end def

    def register_payment(self, invoice_id, params, actor=None):
        # Bayar: record money received against a Terekam invoice. The
        # residual is decreased with a guarded $inc, so two clicks can never
        # pay more than what is open.
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Faktur tidak ditemukan"}
        # end if
        if inv.get("state") != STATE_POSTED:
            return {"status": "ERROR", "desc": "Hanya faktur Terekam yang bisa dibayar"}
        # end if
        residual = round(inv.get("amount_residual") or 0, 2)
        if residual <= 0:
            return {"status": "ERROR", "desc": "Faktur ini sudah lunas"}
        # end if
        amount = _to_number(params.get("amount") or "")
        if amount == None or amount <= 0:
            return {"status": "ERROR", "desc": "Jumlah pembayaran harus lebih dari 0"}
        # end if
        amount = round(amount, 2)
        if amount > residual:
            return {"status": "ERROR", "desc": "Jumlah pembayaran melebihi sisa tagihan " + rupiah(residual)}
        # end if
        pay_date = _parse_date(params.get("date")) or _today()
        method = (params.get("method") or "").strip()
        if method not in PAYMENT_METHODS:
            return {"status": "ERROR", "desc": "Metode pembayaran tidak valid"}
        # end if
        author_name = "Sistem"
        if actor != None:
            author_name = actor.get("name") or "Sistem"
        # end if
        payment = {
            "date": pay_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "method": method,
            "memo": (params.get("memo") or "").strip()[:200],
            "author_name": author_name
        }
        result = self.mgdDB.db_invoice.update_one(
            {
                "_id": ObjectId(inv["id"]), "is_deleted": False, "state": STATE_POSTED,
                "amount_residual": {"$gte": amount}
            },
            {"$inc": {"amount_residual": -amount}, "$push": {"payments": payment}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Sisa tagihan sudah berubah, muat ulang halaman"}
        # end if
        left = round(residual - amount, 2)
        pay_state = PAY_PAID if left <= 0 else PAY_PARTIAL
        update = {"payment_state": pay_state}
        if left <= 0:
            update["amount_residual"] = 0
        # end if
        self.mgdDB.db_invoice.update_one({"_id": ObjectId(inv["id"])}, {"$set": update})
        body = "Pembayaran " + rupiah(amount) + " diterima (" + method + ")"
        if payment["memo"] != "":
            body = body + " — " + payment["memo"]
        # end if
        log = record_log_proc()
        log.log_event(LOG_MODEL, inv["id"], body, actor)
        log.log_changes(
            LOG_MODEL, inv["id"],
            {"residual": rupiah(residual), "pay": PAYMENT_STATE_LABELS.get(inv.get("payment_state") or PAY_NOT_PAID)},
            {"residual": rupiah(max(left, 0)), "pay": PAYMENT_STATE_LABELS[pay_state]},
            {"residual": "Jumlah Belum Dibayar", "pay": "Status Pembayaran"}, actor
        )
        desc = "Pembayaran " + rupiah(amount) + " dicatat"
        if pay_state == PAY_PAID:
            desc = desc + " — faktur lunas"
        # end if
        return {"status": "SUCCESS", "desc": desc}
    # end def

    def cancel_invoice(self, invoice_id, actor=None):
        return self._set_state(invoice_id, [STATE_DRAFT], STATE_CANCEL, actor, "Faktur dibatalkan")
    # end def

    def delete_invoices(self, invoice_ids):
        # Only drafts / cancelled invoices that were never confirmed can be
        # deleted; anything that was ever Terekam stays for the audit trail.
        oids = []
        for iid in invoice_ids:
            try:
                oids.append(ObjectId(iid))
            except Exception:
                pass
            # end try
        # end for
        if len(oids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu faktur"}
        # end if
        result = self.mgdDB.db_invoice.update_many(
            {
                "_id": {"$in": oids}, "is_deleted": False, "posted_at": "",
                "state": {"$in": [STATE_DRAFT, STATE_CANCEL]}
            },
            {"$set": {"is_deleted": True}}
        )
        skipped = len(oids) - result.modified_count
        desc = str(result.modified_count) + " faktur dihapus"
        if skipped > 0:
            desc = desc + "; " + str(skipped) + " faktur yang pernah dikonfirmasi tidak bisa dihapus (batalkan saja)"
        # end if
        return {"status": "SUCCESS", "desc": desc}
    # end def
# end class
