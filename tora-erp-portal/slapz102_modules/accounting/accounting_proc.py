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

LOG_MODEL = "invoice"          # Faktur; Nota Kredit logs as "credit_note"

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
    "client-invoices": {"label": "Faktur", "title": "Faktur", "menu": "Pelanggan",
                 "desc": "Faktur penjualan untuk klien atas order LTL / FTL."},
    "client-credit-notes": {"label": "Nota Kredit", "title": "Nota Kredit", "menu": "Pelanggan",
                     "desc": "Pengurangan tagihan klien, misalnya klaim kerusakan atau retur."},
    "client-payments": {"label": "Pembayaran", "title": "Pembayaran Pelanggan", "menu": "Pelanggan",
                          "desc": "Pencatatan uang masuk dari klien dan pelunasan faktur."},
    "client-products": {"label": "Produk", "title": "Produk Penjualan", "menu": "Pelanggan",
                      "desc": "Layanan dan produk yang dijual ke klien (tarif LTL, charter FTL, ...)."},
    "vendor-bills": {"label": "Tagihan", "title": "Tagihan", "menu": "Vendor",
              "desc": "Tagihan dari vendor: sewa armada, BBM, tol, dan biaya lain."},
    "vendor-refunds": {"label": "Pengembalian", "title": "Pengembalian", "menu": "Vendor",
                "desc": "Pengembalian dana dari vendor atas tagihan yang sudah dibayar."},
    "vendor-payments": {"label": "Pembayaran", "title": "Pembayaran Vendor", "menu": "Vendor",
                        "desc": "Pencatatan uang keluar ke vendor dan pelunasan tagihan."},
    "vendor-products": {"label": "Produk", "title": "Produk Pembelian", "menu": "Vendor",
                          "desc": "Barang dan jasa yang dibeli dari vendor."},
    "journal-entries": {"label": "Entri Jurnal", "title": "Entri Jurnal", "menu": "Akuntansi",
                        "desc": "Semua entri jurnal: penjualan, pembelian, bank, kas, dan lain-lain."},
    "journal-items": {"label": "Item Jurnal", "title": "Item Jurnal", "menu": "Kontrol",
                      "desc": "Baris debit / kredit per akun dari semua entri jurnal yang Terekam."},
    "audit-trail": {"label": "Log Catatan", "title": "Log Catatan", "menu": "Kontrol",
                    "desc": "Riwayat perubahan dan catatan semua dokumen akuntansi."}
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
         "key": "client-invoices", "area": None, "divider": False},
        {"label": "Nota Kredit", "endpoint": "accounting_blueprint.credit_notes", "args": {},
         "key": "client-credit-notes", "area": None, "divider": False},
        {"label": "Pembayaran", "endpoint": "accounting_blueprint.customer_payments", "args": {},
         "key": "client-payments", "area": None, "divider": False},
        {"label": "Produk", "endpoint": "accounting_blueprint.client_products", "args": {},
         "key": "client-products", "area": None, "divider": False},
        {"label": "Pelanggan", "endpoint": "accounting_blueprint.contacts", "args": {"category": "CLIENT"},
         "key": "contact.CLIENT", "area": "contacts", "divider": True}
    ]},
    {"label": "Vendor", "entries": [
        {"label": "Tagihan", "endpoint": "accounting_blueprint.bills", "args": {},
         "key": "vendor-bills", "area": None, "divider": False},
        {"label": "Pengembalian", "endpoint": "accounting_blueprint.vendor_refunds", "args": {},
         "key": "vendor-refunds", "area": None, "divider": False},
        {"label": "Pembayaran", "endpoint": "accounting_blueprint.vendor_payments", "args": {},
         "key": "vendor-payments", "area": None, "divider": False},
        {"label": "Produk", "endpoint": "accounting_blueprint.vendor_products", "args": {},
         "key": "vendor-products", "area": None, "divider": False},
        {"label": "Vendor", "endpoint": "accounting_blueprint.contacts", "args": {"category": "VENDOR"},
         "key": "contact.VENDOR", "area": "contacts", "divider": True}
    ]},
    {"label": "Akuntansi", "entries": [
        {"label": "Entri Jurnal", "endpoint": "accounting_blueprint.journal_entries", "args": {},
         "key": "journal-entries", "area": None, "divider": False}
    ]},
    {"label": "Kontrol", "entries": [
        {"label": "Item Jurnal", "endpoint": "accounting_blueprint.journal_items", "args": {},
         "key": "journal-items", "area": None, "divider": False},
        {"label": "Log Catatan", "endpoint": "accounting_blueprint.audit_trail", "args": {},
         "key": "audit-trail", "area": None, "divider": False}
    ]},
    {"label": "Konfigurasi", "entries": [
        {"label": "Pengaturan", "endpoint": "accounting_blueprint.settings", "args": {},
         "key": "settings", "area": None, "divider": False},
        {"label": "Bagan Akun", "endpoint": "accounting_blueprint.accounts", "args": {},
         "key": "accounts", "area": None, "divider": False},
        {"label": "Pajak", "endpoint": "accounting_blueprint.taxes", "args": {},
         "key": "taxes", "area": None, "divider": False}
    ]}
]

# Dashboard journal cards. Targets are page slugs, or an endpoint name
# (contains a ".") for pages with their own route.
JOURNALS = [
    {"name": "Faktur Pelanggan", "code": "INV", "metric": "Faktur belum dibayar",
     "primary": ("Faktur Baru", "accounting_blueprint.invoice_new"),
     "links": [("Lihat Faktur", "client-invoices")]},
    {"name": "Tagihan Vendor", "code": "BILL", "metric": "Tagihan yang harus dibayar",
     "primary": ("Tagihan Baru", "accounting_blueprint.bill_new"),
     "links": [("Lihat Tagihan", "vendor-bills")]},
    {"name": "Bank", "code": "BNK1", "metric": "Saldo di buku besar",
     "primary": ("Buat", "journal-entries"),
     "links": [("Mutasi", "journal-entries"), ("Rekonsiliasi", "journal-entries")]},
    {"name": "Kas", "code": "CSH1", "metric": "Saldo di buku besar",
     "primary": ("Transaksi Baru", "journal-entries"),
     "links": [("Daftar Kas", "journal-entries")]}
]


def rupiah(amount):
    # 1234567.5 -> "Rp 1.234.567,50"; -2000000 -> "Rp -2.000.000,00"
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
    return "Rp " + sign + digits + "," + str(cents).zfill(2)
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

# Accounts the journal posts to by itself (seeded in Bagan Akun).
ACCOUNT_RECEIVABLE = "11210010"   # Piutang Dagang
ACCOUNT_TAX_OUT = "21221010"      # PPN Keluaran
ACCOUNT_PAYABLE = "21100010"      # Hutang Usaha
ACCOUNT_TAX_IN = "11210030"       # PPN Masukan
DEFAULT_SALE_TAX = "ppn12_dpp"
DEFAULT_PURCHASE_TAX = "ppn12_dpp_in"

# Every invoice-like document lives in db_invoice, told apart by move_type.
# One form, list, print and set of procs serve all four; this table holds
# everything that differs: names, partner side, tax use, accounts, journal
# direction, the document a refund reverses, the payment direction, and the
# list sign (refunds show negative). Each type has its own URL counter and
# numbering sequence (SEQUENCES key = move_type).
#   swap       journal is the mirror of a faktur (revenue credit, receivable debit)
#   origin     refunds: the type they correct;  reverse: invoices: their refund type
MOVE_INVOICE = "out_invoice"
MOVE_REFUND = "out_refund"
MOVE_BILL = "in_invoice"
MOVE_BILL_REFUND = "in_refund"
#   journal / entry_sign   Entri Jurnal list: journal name and the sign of the
#              total there (money in +, money out -), like the reference.
_CUSTOMER = {
    "journal": "sale", "journal_label": "Penjualan",
    "partner_type": "customer", "partner_label": "Pelanggan", "partner_category": "CLIENT",
    "partner_placeholder": "Cari klien ...", "menu": "Pelanggan", "is_purchase": False,
    "tax_use": "sale", "account_group": "income", "date_label": "Tanggal Faktur",
    "ref_label": "Referensi Pelanggan", "counterpart": ACCOUNT_RECEIVABLE,
    "counterpart_label": "Akun Piutang", "tax_account": ACCOUNT_TAX_OUT
}
_SUPPLIER = {
    "journal": "purchase", "journal_label": "Pembelian",
    "partner_type": "supplier", "partner_label": "Vendor", "partner_category": "VENDOR",
    "partner_placeholder": "Cari vendor ...", "menu": "Vendor", "is_purchase": True,
    "tax_use": "purchase", "account_group": "expense", "date_label": "Tanggal Tagihan",
    "ref_label": "Referensi Tagihan", "counterpart": ACCOUNT_PAYABLE,
    "counterpart_label": "Akun Hutang", "tax_account": ACCOUNT_TAX_IN
}
MOVE_TYPES = {
    MOVE_INVOICE: dict(_CUSTOMER, **{
        "move_type": MOVE_INVOICE, "label": "Faktur", "title": "Faktur Pelanggan",
        "ep": "invoice", "list_ep": "invoices", "slug": "client-invoices",
        "log_model": "invoice", "seq_key": "SEQID:invoice", "sign": 1, "entry_sign": 1,
        "is_refund": False, "swap": False, "origin": "", "reverse": MOVE_REFUND,
        "payment_type": "inbound", "default_tax": DEFAULT_SALE_TAX, "outstanding_label": "",
        "empty_title": "Belum ada faktur", "empty_desc": "Buat faktur pelanggan pertama untuk order Anda."
    }),
    MOVE_REFUND: dict(_CUSTOMER, **{
        "move_type": MOVE_REFUND, "label": "Nota Kredit", "title": "Nota Kredit Pelanggan",
        "ep": "credit_note", "list_ep": "credit_notes", "slug": "client-credit-notes",
        "log_model": "credit_note", "seq_key": "SEQID:credit_note", "sign": -1, "entry_sign": -1,
        "is_refund": True, "swap": True, "origin": MOVE_INVOICE, "reverse": "",
        "payment_type": "outbound", "default_tax": "", "outstanding_label": "Debet belum lunas",
        "empty_title": "Belum ada nota kredit", "empty_desc": "Buat nota kredit untuk klaim, retur, atau koreksi faktur pelanggan."
    }),
    MOVE_BILL: dict(_SUPPLIER, **{
        "move_type": MOVE_BILL, "label": "Tagihan", "title": "Tagihan Vendor",
        "ep": "bill", "list_ep": "bills", "slug": "vendor-bills",
        "log_model": "bill", "seq_key": "SEQID:bill", "sign": 1, "entry_sign": -1,
        "is_refund": False, "swap": True, "origin": "", "reverse": MOVE_BILL_REFUND,
        "payment_type": "outbound", "default_tax": DEFAULT_PURCHASE_TAX, "outstanding_label": "",
        "empty_title": "Belum ada tagihan", "empty_desc": "Catat tagihan vendor: sewa armada, BBM, tol, sparepart, dan biaya lain."
    }),
    MOVE_BILL_REFUND: dict(_SUPPLIER, **{
        "move_type": MOVE_BILL_REFUND, "label": "Pengembalian", "title": "Pengembalian Vendor",
        "ep": "vendor_refund", "list_ep": "vendor_refunds", "slug": "vendor-refunds",
        "log_model": "vendor_refund", "seq_key": "SEQID:vendor_refund", "sign": -1, "entry_sign": 1,
        "is_refund": True, "swap": False, "origin": MOVE_BILL, "reverse": "",
        "payment_type": "inbound", "default_tax": "", "outstanding_label": "Kredit belum lunas",
        "empty_title": "Belum ada pengembalian", "empty_desc": "Catat pengembalian dana atau potongan dari vendor atas tagihan."
    })
}


# Counterpart names for templates: the refund button on a faktur / tagihan
# and the "<origin> asal" link on a refund.
for _key in MOVE_TYPES:
    _entry = MOVE_TYPES[_key]
    _entry["reverse_ep"] = MOVE_TYPES[_entry["reverse"]]["ep"] if _entry["reverse"] else ""
    _entry["reverse_label"] = MOVE_TYPES[_entry["reverse"]]["label"] if _entry["reverse"] else ""
    _entry["origin_ep"] = MOVE_TYPES[_entry["origin"]]["ep"] if _entry["origin"] else ""
    _entry["origin_label"] = MOVE_TYPES[_entry["origin"]]["label"] if _entry["origin"] else ""
# end for


# URL slug -> move_type (Entri Jurnal links: /accounting/journal-entries/vendor-bills/1).
MOVE_BY_SLUG = {}
for _key in MOVE_TYPES:
    MOVE_BY_SLUG[MOVE_TYPES[_key]["slug"]] = _key
# end for
JOURNAL_FILTERS = {"sale": "Penjualan", "purchase": "Pembelian"}


# Side-panel tree on Bagan Akun / Item Jurnal: "1" > "11", "12", ...
CODE_PREFIX_PATTERN = re.compile(r"^[0-9]{1,2}$")


def code_tree(prefix_counts):
    # {"11": 5, "12": 2, "21": 7} -> [{"key": "1", "count": 7, "children":
    # [{"key": "11", "count": 5}, {"key": "12", "count": 2}]}, {"key": "2", ...}]
    tops = {}
    for prefix in sorted(prefix_counts.keys()):
        if prefix == "":
            continue
        # end if
        top = prefix[:1]
        if top not in tops:
            tops[top] = {"key": top, "count": 0, "children": []}
        # end if
        tops[top]["count"] = tops[top]["count"] + prefix_counts[prefix]
        if len(prefix) == 2:
            tops[top]["children"].append({"key": prefix, "count": prefix_counts[prefix]})
        # end if
    # end for
    return [tops[key] for key in sorted(tops.keys())]
# end def


def move_type_of(doc):
    # The MOVE_TYPES entry of a db_invoice document (old ones: faktur).
    return MOVE_TYPES.get((doc or {}).get("move_type") or MOVE_INVOICE, MOVE_TYPES[MOVE_INVOICE])
# end def

# ---------------------------------------------------------------------------
# Bagan Akun (Konfigurasi > Bagan Akun), stored in db_account by code.
# Document lines pick from any active account except Piutang / Utang
# (Penghasilan first on faktur, Beban first on tagihan); the journal posts
# the receivable / payable and PPN to the fixed ACCOUNT_* codes above.
# ---------------------------------------------------------------------------

ACCOUNT_GROUPS = {"asset": "Aset", "liability": "Liabilitas", "equity": "Ekuitas",
                  "income": "Penghasilan", "expense": "Beban"}
ACCOUNT_TYPES = [
    {"key": "asset_receivable", "label": "Piutang", "group": "asset"},
    {"key": "asset_cash", "label": "Bank dan Kas", "group": "asset"},
    {"key": "asset_current", "label": "Aset Lancar", "group": "asset"},
    {"key": "asset_prepayments", "label": "Pembayaran di Muka", "group": "asset"},
    {"key": "asset_fixed", "label": "Aset Tetap", "group": "asset"},
    {"key": "asset_non_current", "label": "Aset Tidak Lancar", "group": "asset"},
    {"key": "liability_payable", "label": "Utang", "group": "liability"},
    {"key": "liability_current", "label": "Liabilitas Lancar", "group": "liability"},
    {"key": "liability_non_current", "label": "Liabilitas Jangka Panjang", "group": "liability"},
    {"key": "equity", "label": "Ekuitas", "group": "equity"},
    {"key": "equity_unaffected", "label": "Laba Tahun Berjalan", "group": "equity"},
    {"key": "income", "label": "Penghasilan", "group": "income"},
    {"key": "income_other", "label": "Penghasilan Lain", "group": "income"},
    {"key": "expense", "label": "Beban", "group": "expense"},
    {"key": "expense_direct_cost", "label": "Harga Pokok Penjualan", "group": "expense"},
    {"key": "expense_depreciation", "label": "Penyusutan", "group": "expense"}
]
ACCOUNT_TYPE_MAP = {}
for _type in ACCOUNT_TYPES:
    ACCOUNT_TYPE_MAP[_type["key"]] = _type
# end for
LINE_EXCLUDED_TYPES = ["asset_receivable", "liability_payable"]
ACCOUNT_CODE_PATTERN = re.compile(r"^[0-9A-Za-z.]{1,20}$")
ACCOUNT_LOG_LABELS = {"name": "Nama Akun", "account_type": "Tipe", "description": "Deskripsi", "active": "Aktif"}

DEFAULT_LINE_ACCOUNT = {"income": "41000010", "expense": "51000010"}

# Added when missing (by code): the accounts documents post to. The rest of
# a standard chart is injected by the user (mongosh script).
SEED_ACCOUNTS = [
    {"code": "11210010", "name": "Piutang Dagang", "account_type": "asset_receivable",
     "description": "Tagihan ke pelanggan yang belum dibayar."},
    {"code": "21221010", "name": "PPN Keluaran", "account_type": "liability_current",
     "description": "PPN yang dipungut dari pelanggan atas penjualan."},
    {"code": "21100010", "name": "Hutang Usaha", "account_type": "liability_payable",
     "description": "Tagihan vendor yang belum dibayar."},
    {"code": "11210030", "name": "PPN Masukan", "account_type": "asset_current",
     "description": "PPN yang dibayar atas pembelian dan dapat dikreditkan."},
    {"code": "51000010", "name": "Harga Pokok Penjualan", "account_type": "expense_direct_cost",
     "description": "Biaya langsung atas jasa yang dijual (sewa armada, BBM, tol)."},
    {"code": "41000010", "name": "Penjualan", "account_type": "income",
     "description": "Pendapatan dari barang atau jasa yang dijual."},
    {"code": "41000020", "name": "Pendapatan Jasa Angkutan", "account_type": "income",
     "description": "Pendapatan dari jasa pengiriman LTL / FTL."},
    {"code": "41000030", "name": "Pendapatan Lain-lain", "account_type": "income_other",
     "description": "Pendapatan di luar usaha utama."}
]

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
TAX_BASE_LABELS = {}
for _base in TAX_BASES:
    TAX_BASE_FACTORS[_base["key"]] = _base["factor"]
    TAX_BASE_LABELS[_base["key"]] = _base["label"]
# end for
TAX_LOG_LABELS = {"name": "Nama pajak", "tax_use": "Tipe Pajak", "amount": "Persentase", "base": "Dasar pengenaan",
                  "scope": "Lingkup pajak", "invoice_label": "Label pada Faktur", "description": "Deskripsi", "active": "Aktif"}

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

# collection = where numbers with this prefix live (checked so a counter
# never re-issues a number that is already used).
SEQUENCES = [
    {"key": "out_invoice", "label": "Faktur Pelanggan", "prefix": "INV/{TAHUN}/", "padding": 5, "collection": "db_invoice"},
    {"key": "out_refund", "label": "Nota Kredit", "prefix": "RINV/{TAHUN}/", "padding": 5, "collection": "db_invoice"},
    {"key": "customer_payment", "label": "Pembayaran Pelanggan", "prefix": "PAY", "padding": 5, "collection": "db_payment"},
    {"key": "in_invoice", "label": "Tagihan Vendor", "prefix": "BILL/{TAHUN}/{BULAN}/", "padding": 4, "collection": "db_invoice"},
    {"key": "in_refund", "label": "Pengembalian Vendor", "prefix": "RBILL/{TAHUN}/{BULAN}/", "padding": 4, "collection": "db_invoice"},
    {"key": "vendor_payment", "label": "Pembayaran Vendor", "prefix": "VPAY", "padding": 5, "collection": "db_payment"}
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

INVOICE_TEXT_FIELDS = ["customer_ref", "payment_ref", "partner_bank", "notes"]
MAX_LINES = 200
NOTES_MAX = 5000

MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

# Every field the document form saves, in log order. Lines are logged
# before these: per field for rows on both sides, as one "Baris N" summary
# for added / removed rows (see _log_pair). Partner / date / reference labels
# are taken from MOVE_TYPES ("Vendor", "Tanggal Tagihan", ...).
LINE_LOG_LABELS = {"product": "Produk", "account": "Akun", "quantity": "Kuantitas", "price": "Harga", "tax": "Pajak"}
INVOICE_LOG_LABELS = {
    "number": "Nomor",
    "partner_name": "Pelanggan",
    "invoice_date": "Tanggal Faktur",
    "accounting_date": "Tanggal Akuntansi",
    "payment_term": "Termin Pembayaran",
    "due_date": "Batas Waktu",
    "customer_ref": "Referensi Pelanggan",
    "payment_ref": "Referensi Pembayaran",
    "partner_bank": "Bank Penerima",
    "salesperson_id": "Penjual",
    "delivery_date": "Tanggal Pengiriman",
    "efaktur_code": "Kode Transaksi",
    "fiscal_position": "Posisi Fiskal",
    "notes": "Syarat dan Ketentuan",
    "amount_untaxed": "Jumlah Sebelum Pajak",
    "amount_tax": "Pajak",
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
        unpaid = {"INV": self.unpaid_invoices(MOVE_INVOICE), "BILL": self.unpaid_invoices(MOVE_BILL)}
        out = []
        for journal in JOURNALS:
            card = dict(journal)
            card["amount"] = rupiah(0)
            if journal["code"] in unpaid:
                card["amount"] = rupiah(unpaid[journal["code"]]["amount"])
                card["count"] = unpaid[journal["code"]]["count"]
            # end if
            out.append(card)
        # end for
        return out
    # end def

    # ------------------------------------------------------------------
    # Konfigurasi > Bagan Akun
    # ------------------------------------------------------------------

    def ensure_default_accounts(self):
        # Adds any SEED_ACCOUNTS code that does not exist yet (also deleted
        # ones count as existing, so a removed account is not re-created).
        codes = [seed["code"] for seed in SEED_ACCOUNTS]
        have = set()
        for doc in self.mgdDB.db_account.find({"code": {"$in": codes}}, {"code": 1}):
            have.add(doc["code"])
        # end for
        for seed in SEED_ACCOUNTS:
            if seed["code"] in have:
                continue
            # end if
            rec = database.new(self.mgdDB, "db_account")
            for key in seed:
                rec.put(key, seed[key])
            # end for
            rec.put("active", True)
            rec.insert()
        # end for
    # end def

    def _account_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        acc_type = ACCOUNT_TYPE_MAP.get(doc.get("account_type", ""), {})
        doc["type_label"] = acc_type.get("label", "")
        doc["group"] = acc_type.get("group", "")
        doc["label"] = doc.get("code", "") + " " + doc.get("name", "")
        return doc
    # end def

    def line_accounts(self, include_codes=None, first_group="income"):
        # Akun picker on document lines: every active account except
        # Piutang / Utang (the journal posts those itself), first_group
        # first (Penghasilan on faktur, Beban on tagihan). include_codes keeps
        # accounts already on the document valid after they are deactivated.
        self.ensure_default_accounts()
        query = {"is_deleted": False, "account_type": {"$nin": LINE_EXCLUDED_TYPES}, "active": True}
        include_codes = [c for c in set(include_codes or []) if c]
        if len(include_codes) > 0:
            query = {"is_deleted": False, "$or": [
                {"account_type": {"$nin": LINE_EXCLUDED_TYPES}, "active": True},
                {"code": {"$in": include_codes}}
            ]}
        # end if
        projection = {"code": 1, "name": 1, "description": 1, "account_type": 1, "active": 1}
        first = []
        others = []
        for doc in self.mgdDB.db_account.find(query, projection).sort("code", 1).limit(2000):
            acc = self._account_public(doc)
            if acc["group"] == first_group:
                first.append(acc)
            else:
                others.append(acc)
            # end if
        # end for
        return first + others
    # end def

    def account_labels(self, codes):
        # {code: "41000010 Penjualan"} for the codes on a document (one $in query).
        codes = [c for c in set(codes) if c]
        if len(codes) == 0:
            return {}
        # end if
        out = {}
        for doc in self.mgdDB.db_account.find({"code": {"$in": codes}, "is_deleted": False}, {"code": 1, "name": 1}):
            out[doc["code"]] = doc["code"] + " " + doc.get("name", "")
        # end for
        return out
    # end def

    def _account_query(self, group, q, prefix=""):
        query = {"is_deleted": False}
        if group in ACCOUNT_GROUPS:
            query["account_type"] = {"$in": [t["key"] for t in ACCOUNT_TYPES if t["group"] == group]}
        # end if
        if CODE_PREFIX_PATTERN.match(prefix or "") != None:
            query["code"] = {"$regex": "^" + prefix}
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"code": {"$regex": "^" + pattern}},
                {"name": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def account_tree(self):
        # Side panel of Bagan Akun: two-digit code prefixes with counts.
        pipeline = [
            {"$match": {"is_deleted": False}},
            {"$group": {"_id": {"$substrCP": ["$code", 0, 2]}, "count": {"$sum": 1}}}
        ]
        counts = {}
        for row in self.mgdDB.db_account.aggregate(pipeline):
            counts[row["_id"] or ""] = row["count"]
        # end for
        return code_tree(counts)
    # end def

    def page_accounts(self, group, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE, prefix=""):
        self.ensure_default_accounts()
        query = self._account_query(group, q, prefix)
        total = self.mgdDB.db_account.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_account.find(query).sort("code", 1).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._account_public(rec))
        # end for
        pager["accounts"] = out
        return pager
    # end def

    def get_account(self, code):
        doc = self.mgdDB.db_account.find_one({"code": (code or "").strip(), "is_deleted": False})
        if doc == None:
            return None
        # end if
        return self._account_public(doc)
    # end def

    def _account_fields(self, params):
        name = (params.get("name") or "").strip()
        if name == "":
            return None, {"status": "ERROR", "desc": "Nama akun wajib diisi"}
        # end if
        account_type = (params.get("account_type") or "").strip()
        if account_type not in ACCOUNT_TYPE_MAP:
            return None, {"status": "ERROR", "desc": "Tipe akun tidak valid"}
        # end if
        fields = {
            "name": name[:120],
            "account_type": account_type,
            "description": (params.get("description") or "").strip()[:300],
            "active": params.get("active") == "1"
        }
        return fields, None
    # end def

    def _account_log_values(self, account):
        return {
            "name": account.get("name", ""),
            "account_type": ACCOUNT_TYPE_MAP.get(account.get("account_type", ""), {}).get("label", ""),
            "description": account.get("description", ""),
            "active": "Ya" if account.get("active") else "Tidak"
        }
    # end def

    def create_account(self, params, actor=None):
        code = (params.get("code") or "").strip()
        if ACCOUNT_CODE_PATTERN.match(code) == None:
            return {"status": "ERROR", "desc": "Kode akun hanya boleh angka, huruf, dan titik (maks. 20)"}
        # end if
        fields, err = self._account_fields(params)
        if err != None:
            return err
        # end if
        if self.mgdDB.db_account.find_one({"code": code, "is_deleted": False}, {"_id": 1}) != None:
            return {"status": "ERROR", "desc": "Kode akun " + code + " sudah dipakai"}
        # end if
        rec = database.new(self.mgdDB, "db_account")
        rec.put("code", code)
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        record_log_proc().log_create("account", str(rec.get().get("_id", "")), actor, "Akun " + code + " dibuat")
        return {"status": "SUCCESS", "desc": "Akun " + code + " dibuat", "code": code}
    # end def

    def update_account(self, code, params, actor=None):
        # The code stays fixed: invoice lines and journals reference it.
        account = self.get_account(code)
        if account == None:
            return {"status": "ERROR", "desc": "Akun tidak ditemukan"}
        # end if
        fields, err = self._account_fields(params)
        if err != None:
            return err
        # end if
        self.mgdDB.db_account.update_one({"code": account["code"], "is_deleted": False}, {"$set": fields})
        record_log_proc().log_changes("account", account["id"], self._account_log_values(account),
                                      self._account_log_values(fields), ACCOUNT_LOG_LABELS, actor)
        return {"status": "SUCCESS", "desc": "Akun " + account["code"] + " disimpan"}
    # end def

    def toggle_account(self, code, actor=None):
        account = self.get_account(code)
        if account == None:
            return {"status": "ERROR", "desc": "Akun tidak ditemukan"}
        # end if
        active = not account.get("active", True)
        self.mgdDB.db_account.update_one({"code": account["code"], "is_deleted": False}, {"$set": {"active": active}})
        record_log_proc().log_event("account", account["id"], "Akun " + ("diaktifkan" if active else "dinonaktifkan"), actor)
        desc = "Akun " + account["label"] + (" diaktifkan" if active else " dinonaktifkan")
        return {"status": "SUCCESS", "desc": desc, "active": active}
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

    def line_taxes(self, include_codes=None, tax_use="sale"):
        # Active taxes of one use (sale on faktur, purchase on tagihan) for
        # the line dropdown, plus any inactive code already used on the
        # document so old lines still display.
        self.ensure_default_taxes()
        query = {"is_deleted": False, "tax_use": tax_use, "active": True}
        if include_codes:
            query = {"is_deleted": False, "tax_use": tax_use, "$or": [{"active": True}, {"code": {"$in": list(include_codes)}}]}
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

    def _tax_log_values(self, tax):
        return {
            "name": tax.get("name", ""),
            "tax_use": TAX_USES.get(tax.get("tax_use", ""), ""),
            "amount": "{:g}".format(float(tax.get("amount") or 0)) + "%",
            "base": TAX_BASE_LABELS.get(tax.get("base", ""), ""),
            "scope": TAX_SCOPES.get(tax.get("scope", ""), ""),
            "invoice_label": tax.get("invoice_label", ""),
            "description": tax.get("description", ""),
            "active": "Ya" if tax.get("active") else "Tidak"
        }
    # end def

    def create_tax(self, params, actor=None):
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
        record_log_proc().log_create("tax", str(rec.get().get("_id", "")), actor, "Pajak " + fields["name"] + " dibuat")
        return {"status": "SUCCESS", "desc": "Pajak dibuat", "code": code}
    # end def

    def update_tax(self, code, params, actor=None):
        tax = self.get_tax(code)
        if tax == None:
            return {"status": "ERROR", "desc": "Pajak tidak ditemukan"}
        # end if
        fields, err = self._tax_fields(params)
        if err != None:
            return err
        # end if
        self.mgdDB.db_tax.update_one({"code": tax["code"], "is_deleted": False}, {"$set": fields})
        record_log_proc().log_changes("tax", tax["id"], self._tax_log_values(tax), self._tax_log_values(fields), TAX_LOG_LABELS, actor)
        return {"status": "SUCCESS", "desc": "Pajak disimpan"}
    # end def

    def toggle_tax(self, code, actor=None):
        tax = self.get_tax(code)
        if tax == None:
            return {"status": "ERROR", "desc": "Pajak tidak ditemukan"}
        # end if
        active = not tax.get("active", True)
        self.mgdDB.db_tax.update_one({"code": tax["code"], "is_deleted": False}, {"$set": {"active": active}})
        record_log_proc().log_event("tax", tax["id"], "Pajak " + ("diaktifkan" if active else "dinonaktifkan"), actor)
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

    def _highest_seq(self, prefix, collection="db_invoice"):
        # Highest sequence already used with this exact prefix (so a new or
        # renamed counter never re-issues an existing number).
        pattern = "^" + re.escape(prefix) + "[0-9]+$"
        highest = 0
        for doc in self.mgdDB[collection].find({"number": {"$regex": pattern}}, {"number": 1}):
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
        current = counter["seq"] if counter != None else self._highest_seq(prefix, row["collection"])
        return prefix + str(current + 1).zfill(row["padding"])
    # end def

    def next_number(self, key, day):
        # Atomic: concurrent creates never get the same number.
        row = self._sequence(key)
        collection = row["collection"]
        prefix = render_prefix(row["prefix"], day)
        counter_key = "SEQ:" + prefix
        if self.mgdDB.db_code_counter.find_one({"counter_key": counter_key}, {"_id": 1}) == None:
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": counter_key},
                {"$max": {"seq": self._highest_seq(prefix, collection)}},
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
            if self.mgdDB[collection].find_one({"number": number}, {"_id": 1}) == None:
                return number
            # end if
        # end for
        return number
    # end def

    # ------------------------------------------------------------------
    # Faktur: reads
    # ------------------------------------------------------------------

    def unpaid_invoices(self, move_type=MOVE_INVOICE):
        pipeline = [
            {"$match": {
                "is_deleted": False, "move_type": move_type,
                "state": STATE_POSTED, "amount_residual": {"$gt": 0}
            }},
            {"$group": {"_id": None, "amount": {"$sum": "$amount_residual"}, "count": {"$sum": 1}}}
        ]
        for row in self.mgdDB.db_invoice.aggregate(pipeline):
            return {"amount": row["amount"], "count": row["count"]}
        # end for
        return {"amount": 0, "count": 0}
    # end def

    def _invoice_query(self, state, q, move_type=MOVE_INVOICE):
        query = {"is_deleted": False, "move_type": move_type}
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

    def page_invoices(self, state, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE, move_type=MOVE_INVOICE):
        query = self._invoice_query(state, q, move_type)
        sign = MOVE_TYPES[move_type]["sign"]
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
            row = self._invoice_public(rec, today)
            if sign < 0:
                # Credit notes read as negative amounts in the list.
                for key in ["untaxed", "tax", "total", "residual"]:
                    row[key + "_fmt"] = rupiah(-(row.get("amount_" + key, 0) or 0))
                # end for
            # end if
            out.append(row)
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
        pager["sum_untaxed"] = rupiah(sign * sums["untaxed"])
        pager["sum_total"] = rupiah(sign * sums["total"])
        pager["sum_residual"] = rupiah(sign * sums["residual"])
        return pager
    # end def

    # ------------------------------------------------------------------
    # Akuntansi > Entri Jurnal: every document of every type in one list
    # ------------------------------------------------------------------

    def _entry_query(self, state, journal, q):
        query = {"is_deleted": False, "move_type": {"$in": list(MOVE_TYPES.keys())}}
        if state in STATE_LABELS:
            query["state"] = state
        # end if
        if journal in JOURNAL_FILTERS:
            query["move_type"] = {"$in": [k for k in MOVE_TYPES if MOVE_TYPES[k]["journal"] == journal]}
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

    def page_journal_entries(self, state, journal="", q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        # Total per row is signed like the reference: faktur / pengembalian
        # vendor +, nota kredit / tagihan - (MOVE_TYPES "entry_sign").
        query = self._entry_query(state, journal, q)
        projection = {
            "seq": 1, "number": 1, "state": 1, "move_type": 1, "partner_id": 1, "partner_name": 1,
            "invoice_date": 1, "customer_ref": 1, "posted_at": 1, "amount_total": 1, "amount_residual": 1,
            "payment_state": 1, "due_date": 1
        }
        total = self.mgdDB.db_invoice.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_invoice.find(query, projection).sort(
            [("invoice_date", -1), ("rec_timestamp", -1), ("_id", -1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        today = _today()
        out = []
        for rec in recs:
            row = self._invoice_public(rec, today)
            doc = move_type_of(row)
            row["doc"] = doc
            # Entri Jurnal shows the posting state, not the payment state.
            row["state_label"] = STATE_LABELS.get(row.get("state", STATE_DRAFT), "")
            row["state_class"] = (row.get("state") or STATE_DRAFT).lower()
            row["total_signed_fmt"] = rupiah(doc["entry_sign"] * (row.get("amount_total") or 0))
            out.append(row)
        # end for
        signed = 0
        if total > 0:
            branches = []
            for key in MOVE_TYPES:
                branches.append({"case": {"$eq": ["$move_type", key]}, "then": MOVE_TYPES[key]["entry_sign"]})
            # end for
            pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "total": {"$sum": {"$multiply": [
                    "$amount_total", {"$switch": {"branches": branches, "default": 1}}
                ]}}}}
            ]
            for row in self.mgdDB.db_invoice.aggregate(pipeline):
                signed = row["total"]
            # end for
        # end if
        pager["entries"] = out
        pager["sum_total"] = rupiah(signed)
        return pager
    # end def

    # ------------------------------------------------------------------
    # Kontrol > Item Jurnal: the ledger (db_journal_item). Lines are written
    # when a document becomes Terekam and soft-deleted when it goes back to
    # Draft / Batal, so the list is one paginated query.
    # ------------------------------------------------------------------

    def post_journal_items(self, doc_id):
        inv = self.get_invoice(doc_id)
        if inv == None or inv.get("state") != STATE_POSTED:
            return 0
        # end if
        self.mgdDB.db_journal_item.update_many({"move_id": inv["id"], "is_deleted": False}, {"$set": {"is_deleted": True}})
        doc = inv["doc"]
        rows = self.journal_items(inv)["rows"]
        day = inv.get("accounting_date") or inv.get("invoice_date", "")
        index = 0
        for row in rows:
            index = index + 1
            code = row.get("account_code", "")
            rec = database.new(self.mgdDB, "db_journal_item")
            rec.put("move_id", inv["id"])
            rec.put("move_type", doc["move_type"])
            rec.put("move_seq", inv.get("seq") or 0)
            rec.put("move_number", inv.get("number", ""))
            rec.put("move_slug", doc["slug"])
            rec.put("date", day)
            rec.put("account", code)
            rec.put("account_label", row.get("account", ""))
            rec.put("account_group", code[:1])
            rec.put("partner_id", inv.get("partner_id", ""))
            rec.put("partner_name", inv.get("partner_name", ""))
            rec.put("label", row.get("label", ""))
            rec.put("debit", round(row.get("debit") or 0, 2))
            rec.put("credit", round(row.get("credit") or 0, 2))
            rec.put("sequence", index)
            rec.insert()
        # end for
        self.mgdDB.db_invoice.update_one({"_id": ObjectId(inv["id"])}, {"$set": {"items_posted": True}})
        return index
    # end def

    def remove_journal_items(self, doc_id):
        self.mgdDB.db_journal_item.update_many({"move_id": doc_id, "is_deleted": False}, {"$set": {"is_deleted": True}})
        self.mgdDB.db_invoice.update_one({"_id": ObjectId(doc_id)}, {"$set": {"items_posted": False}})
    # end def

    def sync_journal_items(self, limit=500):
        # Terekam documents that have no ledger lines yet (posted before the
        # ledger existed, or inserted by a data script) get them now.
        query = {"is_deleted": False, "state": STATE_POSTED, "items_posted": {"$ne": True},
                 "move_type": {"$in": list(MOVE_TYPES.keys())}}
        done = 0
        for doc in self.mgdDB.db_invoice.find(query, {"_id": 1}).limit(limit):
            self.post_journal_items(str(doc["_id"]))
            done = done + 1
        # end for
        return done
    # end def

    def _journal_item_query(self, prefix, q):
        # prefix = account code prefix from the side tree ("1", "11", ...)
        query = {"is_deleted": False}
        if CODE_PREFIX_PATTERN.match(prefix or "") != None:
            query["account"] = {"$regex": "^" + prefix}
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"move_number": {"$regex": pattern, "$options": "i"}},
                {"partner_name": {"$regex": pattern, "$options": "i"}},
                {"label": {"$regex": pattern, "$options": "i"}},
                {"account_label": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def journal_item_tree(self):
        # Side panel of Item Jurnal: two-digit account prefixes with counts.
        pipeline = [
            {"$match": {"is_deleted": False}},
            {"$group": {"_id": {"$substrCP": ["$account", 0, 2]}, "count": {"$sum": 1}}}
        ]
        counts = {}
        for row in self.mgdDB.db_journal_item.aggregate(pipeline):
            counts[row["_id"] or ""] = row["count"]
        # end for
        return code_tree(counts)
    # end def

    def page_journal_items(self, prefix="", q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        self.sync_journal_items()
        query = self._journal_item_query(prefix, q)
        projection = {"move_id": 1, "move_seq": 1, "move_number": 1, "move_slug": 1, "date": 1,
                      "account_label": 1, "partner_name": 1, "label": 1, "debit": 1, "credit": 1}
        total = self.mgdDB.db_journal_item.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_journal_item.find(query, projection).sort(
            [("date", -1), ("move_number", -1), ("sequence", 1), ("_id", 1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        today = _today()
        out = []
        for rec in recs:
            rec["id"] = str(rec.pop("_id"))
            rec["date_short"] = short_date(rec.get("date", ""), today)
            rec["debit_fmt"] = rupiah(rec.get("debit", 0))
            rec["credit_fmt"] = rupiah(rec.get("credit", 0))
            out.append(rec)
        # end for
        sums = {"debit": 0, "credit": 0}
        if total > 0:
            pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "debit": {"$sum": "$debit"}, "credit": {"$sum": "$credit"}}}
            ]
            for row in self.mgdDB.db_journal_item.aggregate(pipeline):
                sums = row
            # end for
        # end if
        pager["lines"] = out   # not "items": in Jinja that would be dict.items
        pager["sum_debit"] = rupiah(sums["debit"])
        pager["sum_credit"] = rupiah(sums["credit"])
        return pager
    # end def

    def _next_seq(self, move_type=MOVE_INVOICE):
        # Running URL number 1, 2, 3 ... per document type (atomic). Seeded
        # from the highest seq already stored so it never collides.
        seq_key = MOVE_TYPES[move_type]["seq_key"]
        if self.mgdDB.db_code_counter.find_one({"counter_key": seq_key}, {"_id": 1}) == None:
            top = self.mgdDB.db_invoice.find_one({"seq": {"$gt": 0}, "move_type": move_type}, {"seq": 1}, sort=[("seq", -1)])
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": seq_key},
                {"$max": {"seq": (top or {}).get("seq") or 0}},
                upsert=True
            )
        # end if
        rec = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": seq_key},
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
        move_type = doc.get("move_type") or MOVE_INVOICE
        if not doc.get("seq"):
            update["seq"] = self._next_seq(move_type)
        # end if
        if (doc.get("number") or "") == "":
            day = _parse_date(doc.get("invoice_date")) or _today()
            update["number"] = self.next_number(move_type, day)
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

    def resolve_ref(self, ref, move_type=MOVE_INVOICE):
        # Old URLs (/invoices/INV/2026/00004 or /invoices/<internal id>)
        # -> the running seq for the new URL, or None.
        ref = (ref or "").strip()
        if ref == "":
            return None
        # end if
        projection = {"_id": 1, "seq": 1, "number": 1, "invoice_date": 1, "move_type": 1}
        base_query = {"is_deleted": False, "move_type": move_type}
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

    def get_invoice_by_seq(self, seq, move_type=MOVE_INVOICE):
        doc = self.mgdDB.db_invoice.find_one(
            {"seq": seq, "is_deleted": False, "move_type": move_type}, {"_id": 1}
        )
        if doc == None:
            return None
        # end if
        return self.get_invoice(str(doc["_id"]))
    # end def

    def get_invoice(self, invoice_id):
        # Any document (faktur, nota kredit, tagihan, pengembalian) by id.
        try:
            oid = ObjectId(invoice_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_invoice.find_one({"_id": oid, "is_deleted": False})
        if doc == None:
            return None
        # end if
        inv = self._invoice_public(doc, _today())
        inv["doc"] = move_type_of(inv)
        taxes = self.tax_map([line.get("tax", "") for line in inv.get("lines", [])])
        accounts = self.account_labels([line.get("account", "") for line in inv.get("lines", [])])
        for line in inv.get("lines", []):
            line["account_label"] = accounts.get(line.get("account", ""), line.get("account", ""))
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
        inv["reversed_entry_seq"] = None
        if (inv.get("reversed_entry_id") or "") != "" and ObjectId.is_valid(inv["reversed_entry_id"]):
            origin = self.mgdDB.db_invoice.find_one({"_id": ObjectId(inv["reversed_entry_id"])}, {"seq": 1})
            inv["reversed_entry_seq"] = (origin or {}).get("seq")
        # end if
        return inv
    # end def

    def journal_items(self, inv):
        # Item Jurnal tab, built from the saved lines. Faktur: line accounts
        # and PPN Keluaran credit, Piutang debit. Tagihan: line accounts and
        # PPN Masukan debit, Utang credit. Refunds post the mirror of their
        # origin (MOVE_TYPES "swap").
        doc = move_type_of(inv)
        rows = self._journal_rows(inv, doc)
        if doc["swap"]:
            for row in rows:
                row["debit"], row["credit"] = row["credit"], row["debit"]
            # end for
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

    def _journal_rows(self, inv, doc):
        # Rows in faktur orientation (lines / tax credit, counterpart debit);
        # journal_items swaps them for types that post the mirror.
        rows = []
        taxes = {}
        counterpart = doc["counterpart"]
        tax_account = doc["tax_account"]
        codes = [line.get("account", "") for line in inv.get("lines", [])] + [counterpart, tax_account]
        accounts = self.account_labels(codes)
        for line in inv.get("lines", []):
            rows.append({
                "account": accounts.get(line.get("account", ""), line.get("account", "")),
                "account_code": line.get("account", ""),
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
            rows.append({"account": accounts.get(tax_account, tax_account), "account_code": tax_account, "label": label, "debit": 0, "credit": taxes[key]})
        # end for
        total = inv.get("amount_total", 0)
        if total > 0:
            rows.append({
                "account": accounts.get(counterpart, counterpart),
                "account_code": counterpart,
                "label": inv.get("customer_ref") or inv.get("number") or doc["label"],
                "debit": total, "credit": 0
            })
        # end if
        return rows
    # end def

    # ------------------------------------------------------------------
    # Faktur: writes
    # ------------------------------------------------------------------

    def _compute_lines(self, raw_lines, keep_codes=None, keep_accounts=None, move_type=MOVE_INVOICE):
        # raw_lines: [{product, account, quantity, price_unit, tax}] as text.
        # Returns (lines, totals, err); every amount is recomputed here.
        # Allowed taxes / accounts: active ones of this document's side, plus
        # codes already on the document (keep_codes / keep_accounts) so a
        # later-deactivated one does not block saving it.
        doc = MOVE_TYPES[move_type]
        allowed = {}
        for tax in self.line_taxes(keep_codes, doc["tax_use"]):
            allowed[tax["code"]] = tax["rate"]
        # end for
        allowed[""] = 0.0
        allowed_accounts = {}
        for acc in self.line_accounts(keep_accounts, doc["account_group"]):
            allowed_accounts[acc["code"]] = True
        # end for
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
            account = (raw.get("account") or DEFAULT_LINE_ACCOUNT[doc["account_group"]]).strip()
            if account not in allowed_accounts:
                return None, None, {"status": "ERROR", "desc": "Akun baris \"" + product + "\" tidak valid atau tidak aktif"}
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

    def _invoice_fields(self, params, raw_lines, keep_codes=None, keep_accounts=None, move_type=MOVE_INVOICE):
        doc = MOVE_TYPES[move_type]
        partner_id = (params.get("partner_id") or "").strip()
        partner_name = ""
        if partner_id != "":
            try:
                oid = ObjectId(partner_id)
            except Exception:
                return None, {"status": "ERROR", "desc": doc["partner_label"] + " tidak valid"}
            # end try
            partner = self.mgdDB.db_contact.find_one({"_id": oid, "is_deleted": False}, {"name": 1})
            if partner == None:
                return None, {"status": "ERROR", "desc": doc["partner_label"] + " tidak ditemukan"}
            # end if
            partner_name = partner.get("name", "")
        # end if
        invoice_date = _parse_date(params.get("invoice_date"))
        if invoice_date == None:
            invoice_date = _today()
        # end if
        # Tanggal Akuntansi (tagihan): defaults to the document date.
        accounting_date = _parse_date(params.get("accounting_date")) or invoice_date
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
            return None, {"status": "ERROR", "desc": "Batas waktu tidak boleh sebelum " + doc["date_label"].lower()}
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
        lines, totals, err = self._compute_lines(raw_lines, keep_codes, keep_accounts, move_type)
        if err != None:
            return None, err
        # end if
        fields = {
            "partner_id": partner_id,
            "partner_name": partner_name,
            "invoice_date": invoice_date.strftime("%Y-%m-%d"),
            "accounting_date": accounting_date.strftime("%Y-%m-%d"),
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

    def _log_pair(self, before, after):
        # (old, new, labels) for log_changes: every saved field as people
        # read it. A line on both sides is compared field by field
        # ("Produk (Baris 1)", "Harga (Baris 1)", ...) so only what changed
        # shows; an added / removed line is one "Baris N" summary entry.
        # Names for salesperson / tax / account are looked up once.
        user_ids = []
        for value in [before.get("salesperson_id", ""), after.get("salesperson_id", "")]:
            if value and ObjectId.is_valid(value):
                user_ids.append(ObjectId(value))
            # end if
        # end for
        users = {}
        if len(user_ids) > 0:
            for user in self.mgdDB.db_user.find({"_id": {"$in": user_ids}}, {"username": 1, "name": 1}):
                users[str(user["_id"])] = user.get("name") or user.get("username", "")
            # end for
        # end if
        before_lines = before.get("lines") or []
        after_lines = after.get("lines") or []
        all_lines = before_lines + after_lines
        taxes = self.tax_map([line.get("tax", "") for line in all_lines])
        accounts = self.account_labels([line.get("account", "") for line in all_lines])
        efaktur = {}
        for code in EFAKTUR_CODES:
            efaktur[code["key"]] = code["label"]
        # end for
        common = min(len(before_lines), len(after_lines))

        def line_fields(line):
            tax_name = ""
            if line.get("tax"):
                tax_name = (taxes.get(line["tax"]) or {}).get("name", line["tax"])
            # end if
            return {
                "product": line.get("product", ""),
                "account": accounts.get(line.get("account", ""), line.get("account", "")),
                "quantity": "{:g}".format(line.get("quantity", 0)),
                "price": rupiah(line.get("price_unit", 0)),
                "tax": tax_name or "Tanpa pajak"
            }
        # end def

        def values(inv):
            out = {}
            for key in INVOICE_LOG_LABELS:
                out[key] = inv.get(key, "") or ""
            # end for
            for key in ["invoice_date", "accounting_date", "due_date", "delivery_date"]:
                out[key] = short_date(out[key])
            # end for
            out["salesperson_id"] = users.get(out["salesperson_id"], out["salesperson_id"])
            out["efaktur_code"] = efaktur.get(out["efaktur_code"], out["efaktur_code"])
            for key in ["amount_untaxed", "amount_tax", "amount_total"]:
                out[key] = rupiah(inv.get(key, 0))
            # end for
            index = 0
            for line in inv.get("lines") or []:
                index = index + 1
                parts = line_fields(line)
                if index <= common:
                    for key in LINE_LOG_LABELS:
                        out["line_" + str(index) + "_" + key] = parts[key]
                    # end for
                else:
                    text = parts["product"] + " · " + line.get("account", "") + " · " + parts["quantity"] + " × " + parts["price"]
                    if line.get("tax"):
                        text = text + " · " + parts["tax"]
                    # end if
                    out["line_" + str(index)] = text
                # end if
            # end for
            return out
        # end def

        # Line entries first (the edit the user made), then the header
        # fields and totals that follow from it.
        labels = {}
        rows = max(len(before_lines), len(after_lines))
        for i in range(1, rows + 1):
            if i <= common:
                for key in LINE_LOG_LABELS:
                    labels["line_" + str(i) + "_" + key] = LINE_LOG_LABELS[key] + " (Baris " + str(i) + ")"
                # end for
            else:
                labels["line_" + str(i)] = "Baris " + str(i) + (" ditambahkan" if i > len(before_lines) else " dihapus")
            # end if
        # end for
        doc = move_type_of(before)
        for key in INVOICE_LOG_LABELS:
            labels[key] = INVOICE_LOG_LABELS[key]
        # end for
        labels["partner_name"] = doc["partner_label"]
        labels["invoice_date"] = doc["date_label"]
        labels["customer_ref"] = doc["ref_label"]
        return values(before), values(after), labels
    # end def

    def _log_model(self, inv):
        return move_type_of(inv)["log_model"]
    # end def

    def _label(self, inv):
        return move_type_of(inv)["label"]
    # end def

    def refund_origin(self, origin_seq, move_type=MOVE_REFUND):
        # "Nota Kredit" / "Pengembalian" button on a Terekam faktur / tagihan:
        # prefill the new refund with its partner and a link back to it.
        origin_type = MOVE_TYPES[move_type]["origin"]
        inv = self.get_invoice_by_seq(origin_seq, origin_type)
        if inv == None or inv.get("state") != STATE_POSTED:
            return None
        # end if
        return {
            "partner_id": inv.get("partner_id", ""),
            "partner_name": inv.get("partner_name", ""),
            "payment_term": "",
            "customer_ref": "Koreksi " + inv["number"] + (" - " + inv["customer_ref"] if inv.get("customer_ref") else ""),
            "fiscal_position": inv.get("fiscal_position", ""),
            "salesperson_id": inv.get("salesperson_id", ""),
            "partner_bank": inv.get("partner_bank", ""),
            "reversed_entry_id": inv["id"],
            "reversed_entry_number": inv["number"],
            "reversed_entry_seq": inv["seq"]
        }
    # end def

    def create_invoice(self, params, raw_lines, actor=None, move_type=MOVE_INVOICE):
        fields, err = self._invoice_fields(params, raw_lines, move_type=move_type)
        if err != None:
            return err
        # end if
        doc = MOVE_TYPES[move_type]
        label = doc["label"]
        reversed_id = ""
        reversed_number = ""
        if doc["is_refund"] and (params.get("reversed_entry_id") or "").strip() != "":
            origin = self.get_invoice(params.get("reversed_entry_id").strip())
            if origin == None or origin.get("move_type") != doc["origin"]:
                return {"status": "ERROR", "desc": MOVE_TYPES[doc["origin"]]["label"] + " asal tidak ditemukan"}
            # end if
            reversed_id = origin["id"]
            reversed_number = origin["number"]
        # end if
        number = self.next_number(move_type, _parse_date(fields["invoice_date"]) or _today())
        rec = database.new(self.mgdDB, "db_invoice")
        rec.put("move_type", move_type)
        rec.put("state", STATE_DRAFT)
        rec.put("number", number)
        seq = self._next_seq(move_type)
        rec.put("seq", seq)
        rec.put("payments", [])
        rec.put("payment_state", PAY_NOT_PAID)
        rec.put("reversed_entry_id", reversed_id)
        rec.put("reversed_entry_number", reversed_number)
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        saved = rec.get()
        invoice_id = str(saved.get("_id", ""))
        record_log_proc().log_create(MOVE_TYPES[move_type]["log_model"], invoice_id, actor, label + " " + number + " dibuat")
        return {"status": "SUCCESS", "desc": label + " " + number + " disimpan", "id": invoice_id, "number": number, "seq": seq}
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
            return None, {"status": "ERROR", "desc": "Nomor urut hanya boleh angka (maks. 10 digit)"}
        # end if
        if int(digits) == 0:
            return None, {"status": "ERROR", "desc": "Nomor urut harus lebih dari 0"}
        # end if
        return prefix + digits.zfill(len(current)), None
    # end def

    def _edited_number(self, inv, digits):
        number, err = self._compose_number(inv, digits)
        if err != None:
            return None, err
        # end if
        if number != inv.get("number", "") and self.number_taken(number, inv["id"]) != None:
            return None, {"status": "ERROR", "desc": "Nomor " + number + " sudah dipakai dokumen lain. Pilih nomor lain."}
        # end if
        return number, None
    # end def

    def update_invoice(self, invoice_id, params, raw_lines, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Faktur tidak ditemukan"}
        # end if
        if inv.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya " + self._label(inv).lower() + " Draft yang bisa diubah. Reset ke Draft terlebih dulu."}
        # end if
        keep_codes = [line.get("tax", "") for line in inv.get("lines", [])]
        keep_accounts = [line.get("account", "") for line in inv.get("lines", [])]
        fields, err = self._invoice_fields(params, raw_lines, keep_codes, keep_accounts, inv["doc"]["move_type"])
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
            return {"status": "ERROR", "desc": self._label(inv) + " sudah tidak Draft, muat ulang halaman"}
        # end if
        old, new, labels = self._log_pair(inv, fields)
        record_log_proc().log_changes(self._log_model(inv), inv["id"], old, new, labels, actor)
        return {"status": "SUCCESS", "desc": self._label(inv) + " disimpan"}
    # end def

    def confirm_invoice(self, invoice_id, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Dokumen tidak ditemukan"}
        # end if
        label = self._label(inv)
        if inv.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya " + label.lower() + " Draft yang bisa dikonfirmasi"}
        # end if
        if inv.get("partner_id", "") == "":
            return {"status": "ERROR", "desc": "Pilih " + inv["doc"]["partner_label"].lower() + " sebelum konfirmasi"}
        # end if
        if len(inv.get("lines", [])) == 0 or inv.get("amount_total", 0) <= 0:
            return {"status": "ERROR", "desc": label + " harus punya minimal satu baris dengan total lebih dari 0"}
        # end if
        number = inv.get("number") or self.next_number(inv.get("move_type") or MOVE_INVOICE, _parse_date(inv.get("invoice_date")) or _today())
        now = database._get_current_datetime(hours=config.JKTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(inv["id"]), "state": STATE_DRAFT, "is_deleted": False},
            {"$set": {"state": STATE_POSTED, "number": number, "posted_at": now}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": label + " sudah dikonfirmasi"}
        # end if
        self.post_journal_items(inv["id"])
        log = record_log_proc()
        model = self._log_model(inv)
        log.log_event(model, inv["id"], label + " telah divalidasi", actor)
        log.log_changes(
            model, inv["id"],
            {"number": inv.get("number", ""), "state": STATE_LABELS[STATE_DRAFT]},
            {"number": number, "state": STATE_LABELS[STATE_POSTED]},
            {"number": "Nomor", "state": "Status"}, actor
        )
        return {"status": "SUCCESS", "desc": label + " " + number + " dikonfirmasi"}
    # end def

    def _set_state(self, invoice_id, from_states, to_state, actor, event):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Dokumen tidak ditemukan"}
        # end if
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(inv["id"]), "state": {"$in": from_states}, "is_deleted": False},
            {"$set": {"state": to_state}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Status " + self._label(inv).lower() + " tidak bisa diubah dari " + inv["state_label"]}
        # end if
        if to_state != STATE_POSTED:
            # Back to Draft / Batal: the ledger lines leave Item Jurnal.
            self.remove_journal_items(inv["id"])
        # end if
        record_log_proc().log_changes(
            self._log_model(inv), inv["id"],
            {"state": inv["state_label"]}, {"state": STATE_LABELS[to_state]},
            {"state": "Status"}, actor
        )
        return {"status": "SUCCESS", "desc": event}
    # end def

    def reset_invoice(self, invoice_id, actor=None):
        inv = self.get_invoice(invoice_id)
        if inv == None:
            return {"status": "ERROR", "desc": "Dokumen tidak ditemukan"}
        # end if
        if len(inv.get("payments", [])) > 0:
            return {"status": "ERROR", "desc": self._label(inv) + " yang sudah ada pembayaran / pelunasannya tidak bisa dikembalikan ke Draft. Reset pembayarannya ke Draft terlebih dulu."}
        # end if
        return self._set_state(invoice_id, [STATE_POSTED, STATE_CANCEL], STATE_DRAFT, actor, self._label(inv) + " dikembalikan ke Draft")
    # end def

    # ------------------------------------------------------------------
    # Refunds: "Debet / Kredit belum lunas" (apply against open origin docs)
    # ------------------------------------------------------------------

    def open_invoices(self, partner_id, move_type=MOVE_INVOICE, limit=20):
        # Terekam documents of one type (faktur / tagihan) of this partner
        # that still have an open amount.
        if (partner_id or "") == "":
            return []
        # end if
        query = {
            "is_deleted": False, "move_type": move_type, "state": STATE_POSTED,
            "partner_id": partner_id, "amount_residual": {"$gt": 0}
        }
        projection = {"seq": 1, "number": 1, "invoice_date": 1, "amount_residual": 1}
        out = []
        for doc in self.mgdDB.db_invoice.find(query, projection).sort([("invoice_date", 1), ("_id", 1)]).limit(limit):
            out.append({
                "id": str(doc["_id"]), "seq": doc.get("seq"), "number": doc.get("number", ""),
                "date": doc.get("invoice_date", ""), "date_short": short_date(doc.get("invoice_date", "")),
                "residual": doc.get("amount_residual", 0), "residual_fmt": rupiah(doc.get("amount_residual", 0))
            })
        # end for
        return out
    # end def

    def settle(self, doc_id, amount, entry):
        # Lower one document's open amount by `amount` (guarded) and record
        # the settlement in payments[]; returns True when it applied. Used by
        # nota kredit "Tambah" and by Pembayaran (payments_proc).
        result = self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(doc_id), "is_deleted": False, "state": STATE_POSTED, "amount_residual": {"$gte": amount}},
            {"$inc": {"amount_residual": -amount}, "$push": {"payments": entry}}
        )
        if result.matched_count == 0:
            return False
        # end if
        fresh = self.mgdDB.db_invoice.find_one({"_id": ObjectId(doc_id)}, {"amount_residual": 1})
        left = round(fresh.get("amount_residual") or 0, 2)
        update = {"payment_state": PAY_PAID if left <= 0 else PAY_PARTIAL}
        if left <= 0:
            update["amount_residual"] = 0
        # end if
        self.mgdDB.db_invoice.update_one({"_id": ObjectId(doc_id)}, {"$set": update})
        return True
    # end def

    def unsettle(self, doc_id, payment_id):
        # Undo what one Pembayaran settled on a document (Reset ke Draft on
        # the payment): give the amount back and drop its payments[] entry.
        # Returns the amount given back (0 when nothing was applied).
        doc = self.mgdDB.db_invoice.find_one({"_id": ObjectId(doc_id)}, {"payments": 1})
        amount = 0
        for entry in (doc or {}).get("payments") or []:
            if entry.get("payment_id") == payment_id:
                amount = round(amount + (entry.get("amount") or 0), 2)
            # end if
        # end for
        if amount <= 0:
            return 0
        # end if
        self.mgdDB.db_invoice.update_one(
            {"_id": ObjectId(doc_id)},
            {"$inc": {"amount_residual": amount}, "$pull": {"payments": {"payment_id": payment_id}}}
        )
        fresh = self.mgdDB.db_invoice.find_one({"_id": ObjectId(doc_id)}, {"amount_residual": 1, "amount_total": 1})
        left = round(fresh.get("amount_residual") or 0, 2)
        pay_state = PAY_NOT_PAID if left >= round(fresh.get("amount_total") or 0, 2) else PAY_PARTIAL
        self.mgdDB.db_invoice.update_one({"_id": ObjectId(doc_id)}, {"$set": {"payment_state": pay_state}})
        return amount
    # end def

    def apply_credit_note(self, credit_id, invoice_id, actor=None):
        # Tambah: use a refund's open amount (nota kredit / pengembalian) to
        # settle an open document it can correct (faktur / tagihan) of the
        # same partner (amount = the smaller of the two).
        cn = self.get_invoice(credit_id)
        inv = self.get_invoice(invoice_id)
        if cn == None or not cn["doc"]["is_refund"]:
            return {"status": "ERROR", "desc": "Dokumen pengurang tidak ditemukan"}
        # end if
        cn_label = cn["doc"]["label"]
        origin_label = MOVE_TYPES[cn["doc"]["origin"]]["label"]
        if inv == None or inv.get("move_type") != cn["doc"]["origin"]:
            return {"status": "ERROR", "desc": origin_label + " tidak ditemukan"}
        # end if
        if cn.get("state") != STATE_POSTED or inv.get("state") != STATE_POSTED:
            return {"status": "ERROR", "desc": cn_label + " dan " + origin_label.lower() + " harus sudah Terekam"}
        # end if
        if cn.get("partner_id") != inv.get("partner_id"):
            return {"status": "ERROR", "desc": cn_label + " dan " + origin_label.lower() + " harus untuk " + cn["doc"]["partner_label"].lower() + " yang sama"}
        # end if
        amount = round(min(cn.get("amount_residual") or 0, inv.get("amount_residual") or 0), 2)
        if amount <= 0:
            return {"status": "ERROR", "desc": "Tidak ada sisa yang bisa dipakai"}
        # end if
        author = (actor or {}).get("name") or "Sistem"
        today = _today().strftime("%Y-%m-%d")
        if not self.settle(cn["id"], amount, {"date": today, "amount": amount, "method": "Pelunasan " + origin_label, "memo": inv["number"], "author_name": author}):
            return {"status": "ERROR", "desc": "Sisa " + cn_label.lower() + " sudah berubah, muat ulang halaman"}
        # end if
        if not self.settle(inv["id"], amount, {"date": today, "amount": amount, "method": cn_label, "memo": cn["number"], "author_name": author}):
            # Origin changed in between: give the amount back to the refund.
            self.mgdDB.db_invoice.update_one(
                {"_id": ObjectId(cn["id"])},
                {"$inc": {"amount_residual": amount}, "$pull": {"payments": {"memo": inv["number"], "amount": amount, "date": today}}}
            )
            fresh = self.mgdDB.db_invoice.find_one({"_id": ObjectId(cn["id"])}, {"amount_residual": 1, "amount_total": 1})
            restored = PAY_NOT_PAID if round(fresh["amount_residual"], 2) >= round(fresh["amount_total"], 2) else PAY_PARTIAL
            self.mgdDB.db_invoice.update_one({"_id": ObjectId(cn["id"])}, {"$set": {"payment_state": restored}})
            return {"status": "ERROR", "desc": "Sisa " + origin_label.lower() + " sudah berubah, muat ulang halaman"}
        # end if
        log = record_log_proc()
        log.log_event(cn["doc"]["log_model"], cn["id"], "Dipakai " + rupiah(amount) + " untuk melunasi " + inv["number"], actor)
        log.log_event(inv["doc"]["log_model"], inv["id"], "Dilunasi " + rupiah(amount) + " dengan " + cn_label.lower() + " " + cn["number"], actor)
        return {"status": "SUCCESS", "desc": rupiah(amount) + " dari " + cn["number"] + " dipakai untuk " + inv["number"]}
    # end def

    def cancel_invoice(self, invoice_id, actor=None):
        inv = self.get_invoice(invoice_id) or {}
        return self._set_state(invoice_id, [STATE_DRAFT], STATE_CANCEL, actor, self._label(inv) + " dibatalkan")
    # end def

    def delete_invoices(self, invoice_ids, move_type=MOVE_INVOICE):
        # Only drafts / cancelled documents that were never confirmed can be
        # deleted; anything that was ever Terekam stays for the audit trail.
        # move_type None = any type (Entri Jurnal list).
        oids = []
        for iid in invoice_ids:
            try:
                oids.append(ObjectId(iid))
            except Exception:
                pass
            # end try
        # end for
        label = MOVE_TYPES[move_type]["label"].lower() if move_type else "entri jurnal"
        if len(oids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu " + label}
        # end if
        query = {
            "_id": {"$in": oids}, "is_deleted": False, "posted_at": "",
            "state": {"$in": [STATE_DRAFT, STATE_CANCEL]}
        }
        if move_type:
            query["move_type"] = move_type
        # end if
        result = self.mgdDB.db_invoice.update_many(query, {"$set": {"is_deleted": True}})
        skipped = len(oids) - result.modified_count
        desc = str(result.modified_count) + " " + label + " dihapus"
        if skipped > 0:
            desc = desc + "; " + str(skipped) + " yang pernah dikonfirmasi tidak bisa dihapus (batalkan saja)"
        # end if
        return {"status": "SUCCESS", "desc": desc}
    # end def
# end class
