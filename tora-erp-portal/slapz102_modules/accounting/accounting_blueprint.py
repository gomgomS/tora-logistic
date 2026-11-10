import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.accounting import view_accounting
from view.accounting import view_payments
from view.accounting import view_products
from view.accounting import view_control
from accounting.accounting_proc import MOVE_REFUND, MOVE_BILL, MOVE_BILL_REFUND
from accounting.payments_proc import PARTNER_CUSTOMER, PARTNER_SUPPLIER

# ---------------------------------------------------------------------------
# ACCOUNTING MODULE — route layer.
#
# Paths are named after the navbar menu they sit in: Pelanggan -> client-*,
# Vendor -> vendor-* (client-invoices, client-credit-notes, client-payments,
# vendor-bills, ...). Old names (/accounting/invoices/...) redirect (301).
#
# /accounting                                  Dasbor Akuntansi (journal cards)
# /accounting/client-invoices                  Faktur list
# /accounting/client-invoices/new|create       new faktur form / POST
# /accounting/client-invoices/<seq>            faktur form by running number, e.g. /accounting/client-invoices/4
# /accounting/client-invoices/<seq>/update     POST save (action=confirm saves + confirms)
# /accounting/client-invoices/<seq>/state      POST action=reset|cancel
# /accounting/client-invoices/<seq>/pay        POST Bayar (creates a Pembayaran)
# /accounting/client-invoices/<seq>/print      Cetak / Pratinjau (?print=1 opens the print dialog)
# /accounting/client-invoices/<seq>/check-number?n=00007  JSON: is that number free?
# /accounting/client-invoices/<old ref>        old number / internal id links -> redirect to <seq>
# /accounting/client-invoices/bulk-delete      POST soft delete of never-confirmed drafts
# /accounting/client-credit-notes/...          Nota Kredit: same routes as invoices
#                                              (new?invoice=<seq> prefills from a faktur),
#                                              plus /<seq>/apply (Tambah in Debet belum lunas)
# /accounting/vendor-bills/...                 Tagihan Vendor: same routes as invoices
# /accounting/vendor-refunds/...               Pengembalian Vendor: same routes as credit
#                                              notes (new?invoice=<bill seq>, /<seq>/apply)
# /accounting/client-payments                  Pembayaran Pelanggan list (new?invoice=<id>
#                                              starts from a faktur / nota kredit)
# /accounting/client-payments/<seq>[/update|/state]  form, save (action=confirm),
#                                              action=reset|cancel|sent; /bulk-delete
# /accounting/vendor-payments/...              Pembayaran Vendor: same routes as client-payments
# /accounting/client-products|vendor-products  Produk: same catalogue, default filter Penjualan / Pembelian;
#                                              /new, /create, /<seq>, /<seq>/update stay on the route used
# /accounting/journal-items                    Kontrol > Item Jurnal: ledger lines (?group=1..9, ?q=)
# /accounting/audit-trail                      Kontrol > Log Catatan: all accounting log entries (?model=, ?q=)
# /accounting/journal-entries                  Entri Jurnal: all documents (?state=ALL, ?journal=sale|purchase);
#                                              /<doc slug>/<seq> opens the document page; /bulk-delete
# /accounting/contact.CLIENT|VENDOR            Pelanggan / Vendor: the Kontak list inside
#                                              Akuntansi; /new, /create, /bulk-delete,
#                                              /<contact_id>[/update] stay in Akuntansi too
# /accounting/settings[/save]         Konfigurasi > Pengaturan (nomor dokumen)
# /accounting/accounts[/new|/create]  Konfigurasi > Bagan Akun list / new
# /accounting/accounts/<code>[/update|/toggle]  edit, save, Aktif switch
# /accounting/taxes[/new|/create]     Konfigurasi > Pajak list / new
# /accounting/taxes/<code>[/update|/toggle]  edit, save, Aktif switch
# /accounting/<slug>                  other document pages (segera hadir)
# ---------------------------------------------------------------------------

accounting_blueprint = Blueprint("accounting_blueprint", __name__)

@accounting_blueprint.route("/accounting", methods=["GET"])
def index():
    try:
        return view_accounting.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Faktur Pelanggan ———

@accounting_blueprint.route("/accounting/client-invoices", methods=["GET"])
def invoices():
    try:
        return view_accounting.html_invoices()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/new", methods=["GET"])
def invoice_new():
    try:
        return view_accounting.html_invoice_new()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/create", methods=["POST"])
def invoice_create():
    try:
        return view_accounting.html_invoice_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/bulk-delete", methods=["POST"])
def invoice_bulk_delete():
    try:
        return view_accounting.html_invoice_bulk_delete()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>", methods=["GET"])
def invoice_edit(seq):
    try:
        return view_accounting.html_invoice_edit(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>/update", methods=["POST"])
def invoice_update(seq):
    try:
        return view_accounting.html_invoice_update(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>/state", methods=["POST"])
def invoice_state(seq):
    try:
        return view_accounting.html_invoice_state(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>/pay", methods=["POST"])
def invoice_pay(seq):
    try:
        return view_accounting.html_invoice_pay(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>/check-number", methods=["GET"])
def invoice_check_number(seq):
    try:
        return view_accounting.api_invoice_check_number(seq)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<int:seq>/print", methods=["GET"])
def invoice_print(seq):
    try:
        return view_accounting.html_invoice_print(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-invoices/<path:ref>", methods=["GET"])
def invoice_legacy(ref):
    # Old links (/invoices/INV/2026/00004 or /invoices/<internal id>).
    try:
        return view_accounting.html_invoice_legacy(ref)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Nota Kredit (same views as Faktur, move_type out_refund) ———

@accounting_blueprint.route("/accounting/client-credit-notes", methods=["GET"])
def credit_notes():
    try:
        return view_accounting.html_invoices(move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/new", methods=["GET"])
def credit_note_new():
    try:
        return view_accounting.html_invoice_new(move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/create", methods=["POST"])
def credit_note_create():
    try:
        return view_accounting.html_invoice_create(move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/bulk-delete", methods=["POST"])
def credit_note_bulk_delete():
    try:
        return view_accounting.html_invoice_bulk_delete(move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>", methods=["GET"])
def credit_note_edit(seq):
    try:
        return view_accounting.html_invoice_edit(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/update", methods=["POST"])
def credit_note_update(seq):
    try:
        return view_accounting.html_invoice_update(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/state", methods=["POST"])
def credit_note_state(seq):
    try:
        return view_accounting.html_invoice_state(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/pay", methods=["POST"])
def credit_note_pay(seq):
    try:
        return view_accounting.html_invoice_pay(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/apply", methods=["POST"])
def credit_note_apply(seq):
    try:
        return view_accounting.html_credit_note_apply(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/check-number", methods=["GET"])
def credit_note_check_number(seq):
    try:
        return view_accounting.api_invoice_check_number(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<int:seq>/print", methods=["GET"])
def credit_note_print(seq):
    try:
        return view_accounting.html_invoice_print(seq, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-credit-notes/<path:ref>", methods=["GET"])
def credit_note_legacy(ref):
    try:
        return view_accounting.html_invoice_legacy(ref, move_type=MOVE_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Tagihan Vendor (same views as Faktur, move_type in_invoice) ———

@accounting_blueprint.route("/accounting/vendor-bills", methods=["GET"])
def bills():
    try:
        return view_accounting.html_invoices(move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/new", methods=["GET"])
def bill_new():
    try:
        return view_accounting.html_invoice_new(move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/create", methods=["POST"])
def bill_create():
    try:
        return view_accounting.html_invoice_create(move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/bulk-delete", methods=["POST"])
def bill_bulk_delete():
    try:
        return view_accounting.html_invoice_bulk_delete(move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>", methods=["GET"])
def bill_edit(seq):
    try:
        return view_accounting.html_invoice_edit(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>/update", methods=["POST"])
def bill_update(seq):
    try:
        return view_accounting.html_invoice_update(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>/state", methods=["POST"])
def bill_state(seq):
    try:
        return view_accounting.html_invoice_state(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>/pay", methods=["POST"])
def bill_pay(seq):
    try:
        return view_accounting.html_invoice_pay(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>/check-number", methods=["GET"])
def bill_check_number(seq):
    try:
        return view_accounting.api_invoice_check_number(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<int:seq>/print", methods=["GET"])
def bill_print(seq):
    try:
        return view_accounting.html_invoice_print(seq, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-bills/<path:ref>", methods=["GET"])
def bill_legacy(ref):
    try:
        return view_accounting.html_invoice_legacy(ref, move_type=MOVE_BILL)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Pengembalian Vendor (same views as Faktur, move_type in_refund) ———

@accounting_blueprint.route("/accounting/vendor-refunds", methods=["GET"])
def vendor_refunds():
    try:
        return view_accounting.html_invoices(move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/new", methods=["GET"])
def vendor_refund_new():
    try:
        return view_accounting.html_invoice_new(move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/create", methods=["POST"])
def vendor_refund_create():
    try:
        return view_accounting.html_invoice_create(move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/bulk-delete", methods=["POST"])
def vendor_refund_bulk_delete():
    try:
        return view_accounting.html_invoice_bulk_delete(move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>", methods=["GET"])
def vendor_refund_edit(seq):
    try:
        return view_accounting.html_invoice_edit(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/update", methods=["POST"])
def vendor_refund_update(seq):
    try:
        return view_accounting.html_invoice_update(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/state", methods=["POST"])
def vendor_refund_state(seq):
    try:
        return view_accounting.html_invoice_state(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/pay", methods=["POST"])
def vendor_refund_pay(seq):
    try:
        return view_accounting.html_invoice_pay(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/apply", methods=["POST"])
def vendor_refund_apply(seq):
    try:
        return view_accounting.html_credit_note_apply(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/check-number", methods=["GET"])
def vendor_refund_check_number(seq):
    try:
        return view_accounting.api_invoice_check_number(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<int:seq>/print", methods=["GET"])
def vendor_refund_print(seq):
    try:
        return view_accounting.html_invoice_print(seq, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-refunds/<path:ref>", methods=["GET"])
def vendor_refund_legacy(ref):
    try:
        return view_accounting.html_invoice_legacy(ref, move_type=MOVE_BILL_REFUND)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Produk (one catalogue; Pelanggan > Produk = Penjualan, Vendor > Produk = Pembelian) ———

@accounting_blueprint.route("/accounting/client-products", methods=["GET"])
def client_products():
    try:
        return view_products.html_products(shell="client")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-products/new", methods=["GET"])
def client_product_new():
    try:
        return view_products.html_product_new(shell="client")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-products/create", methods=["POST"])
def client_product_create():
    try:
        return view_products.html_product_create(shell="client")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-products/<int:seq>", methods=["GET"])
def client_product_edit(seq):
    try:
        return view_products.html_product_edit(seq, shell="client")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-products/<int:seq>/update", methods=["POST"])
def client_product_update(seq):
    try:
        return view_products.html_product_update(seq, shell="client")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-products", methods=["GET"])
def vendor_products():
    try:
        return view_products.html_products(shell="vendor")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-products/new", methods=["GET"])
def vendor_product_new():
    try:
        return view_products.html_product_new(shell="vendor")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-products/create", methods=["POST"])
def vendor_product_create():
    try:
        return view_products.html_product_create(shell="vendor")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-products/<int:seq>", methods=["GET"])
def vendor_product_edit(seq):
    try:
        return view_products.html_product_edit(seq, shell="vendor")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-products/<int:seq>/update", methods=["POST"])
def vendor_product_update(seq):
    try:
        return view_products.html_product_update(seq, shell="vendor")
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Akuntansi > Entri Jurnal (all documents; detail = the document page) ———

@accounting_blueprint.route("/accounting/journal-entries", methods=["GET"])
def journal_entries():
    try:
        return view_accounting.html_journal_entries()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/journal-entries/bulk-delete", methods=["POST"])
def journal_entry_bulk_delete():
    try:
        return view_accounting.html_journal_entry_bulk_delete()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/journal-entries/<slug>/<int:seq>", methods=["GET"])
def journal_entry(slug, seq):
    try:
        return view_accounting.html_journal_entry(slug, seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Kontrol: Item Jurnal (ledger lines) and Log Catatan (audit trail) ———

@accounting_blueprint.route("/accounting/journal-items", methods=["GET"])
def journal_items():
    try:
        return view_control.html_journal_items()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/audit-trail", methods=["GET"])
def audit_trail():
    try:
        return view_control.html_audit_trail()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Konfigurasi ———

@accounting_blueprint.route("/accounting/settings", methods=["GET"])
def settings():
    try:
        return view_accounting.html_settings()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/settings/save", methods=["POST"])
def settings_save():
    try:
        return view_accounting.html_settings_save()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Pelanggan / Vendor (Kontak list + form inside Akuntansi) ———

@accounting_blueprint.route("/accounting/contact.<category>", methods=["GET"])
def contacts(category):
    try:
        return view_accounting.html_contacts(category)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/contact.<category>/new", methods=["GET"])
def contact_new(category):
    try:
        return view_accounting.html_contact_new(category)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/contact.<category>/create", methods=["POST"])
def contact_create(category):
    try:
        return view_accounting.html_contact_create(category)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/contact.<category>/bulk-delete", methods=["POST"])
def contact_bulk_delete(category):
    try:
        return view_accounting.html_contact_bulk_delete(category)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/contact.<category>/<contact_id>", methods=["GET"])
def contact_edit(category, contact_id):
    try:
        return view_accounting.html_contact_edit(category, contact_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/contact.<category>/<contact_id>/update", methods=["POST"])
def contact_update(category, contact_id):
    try:
        return view_accounting.html_contact_update(category, contact_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Pembayaran Pelanggan ———

@accounting_blueprint.route("/accounting/client-payments", methods=["GET"])
def customer_payments():
    try:
        return view_payments.html_payments(partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/new", methods=["GET"])
def customer_payment_new():
    try:
        return view_payments.html_payment_new(partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/create", methods=["POST"])
def customer_payment_create():
    try:
        return view_payments.html_payment_create(partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/bulk-delete", methods=["POST"])
def customer_payment_bulk_delete():
    try:
        return view_payments.html_payment_bulk_delete(partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/<int:seq>", methods=["GET"])
def customer_payment_edit(seq):
    try:
        return view_payments.html_payment_edit(seq, partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/<int:seq>/update", methods=["POST"])
def customer_payment_update(seq):
    try:
        return view_payments.html_payment_update(seq, partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/client-payments/<int:seq>/state", methods=["POST"])
def customer_payment_state(seq):
    try:
        return view_payments.html_payment_state(seq, partner_type=PARTNER_CUSTOMER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

# ——— Pembayaran Vendor (same views, partner_type supplier) ———

@accounting_blueprint.route("/accounting/vendor-payments", methods=["GET"])
def vendor_payments():
    try:
        return view_payments.html_payments(partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/new", methods=["GET"])
def vendor_payment_new():
    try:
        return view_payments.html_payment_new(partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/create", methods=["POST"])
def vendor_payment_create():
    try:
        return view_payments.html_payment_create(partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/bulk-delete", methods=["POST"])
def vendor_payment_bulk_delete():
    try:
        return view_payments.html_payment_bulk_delete(partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/<int:seq>", methods=["GET"])
def vendor_payment_edit(seq):
    try:
        return view_payments.html_payment_edit(seq, partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/<int:seq>/update", methods=["POST"])
def vendor_payment_update(seq):
    try:
        return view_payments.html_payment_update(seq, partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/vendor-payments/<int:seq>/state", methods=["POST"])
def vendor_payment_state(seq):
    try:
        return view_payments.html_payment_state(seq, partner_type=PARTNER_SUPPLIER)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts", methods=["GET"])
def accounts():
    try:
        return view_accounting.html_accounts()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts/new", methods=["GET"])
def account_new():
    try:
        return view_accounting.html_account_new()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts/create", methods=["POST"])
def account_create():
    try:
        return view_accounting.html_account_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts/<code>", methods=["GET"])
def account_edit(code):
    try:
        return view_accounting.html_account_edit(code)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts/<code>/update", methods=["POST"])
def account_update(code):
    try:
        return view_accounting.html_account_update(code)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/accounts/<code>/toggle", methods=["POST"])
def account_toggle(code):
    try:
        return view_accounting.html_account_toggle(code)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes", methods=["GET"])
def taxes():
    try:
        return view_accounting.html_taxes()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes/new", methods=["GET"])
def tax_new():
    try:
        return view_accounting.html_tax_new()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes/create", methods=["POST"])
def tax_create():
    try:
        return view_accounting.html_tax_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes/<code>", methods=["GET"])
def tax_edit(code):
    try:
        return view_accounting.html_tax_edit(code)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes/<code>/update", methods=["POST"])
def tax_update(code):
    try:
        return view_accounting.html_tax_update(code)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/taxes/<code>/toggle", methods=["POST"])
def tax_toggle(code):
    try:
        return view_accounting.html_tax_toggle(code)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/<any(invoices, 'credit-notes', 'customer-payments', 'sale-products', bills, refunds, 'purchase-products'):old>/<path:rest>", methods=["GET"])
def legacy_redirect(old, rest):
    # Old sub-paths (/accounting/invoices/4) -> new names; old list URLs
    # are redirected by page() below.
    try:
        return view_accounting.html_legacy_redirect(old, rest)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/<slug>", methods=["GET"])
def page(slug):
    try:
        return view_accounting.html_page(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def
