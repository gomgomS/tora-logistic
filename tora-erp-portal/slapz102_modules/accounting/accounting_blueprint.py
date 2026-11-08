import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.accounting import view_accounting

# ---------------------------------------------------------------------------
# ACCOUNTING MODULE — route layer.
#
# /accounting                         Dasbor Akuntansi (journal cards)
# /accounting/invoices                Faktur list
# /accounting/invoices/new|create     new faktur form / POST
# /accounting/invoices/<seq>          faktur form by running number, e.g. /accounting/invoices/4
# /accounting/invoices/<seq>/update   POST save (action=confirm saves + confirms)
# /accounting/invoices/<seq>/state    POST action=reset|cancel
# /accounting/invoices/<seq>/pay      POST Bayar (register a payment)
# /accounting/invoices/<seq>/print    Cetak / Pratinjau (?print=1 opens the print dialog)
# /accounting/invoices/<seq>/check-number?n=00007  JSON: is that number free?
# /accounting/invoices/<old ref>      old number / internal id links -> redirect to <seq>
# /accounting/invoices/bulk-delete    POST soft delete of never-confirmed drafts
# /accounting/settings[/save]         Konfigurasi > Pengaturan (nomor dokumen)
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

@accounting_blueprint.route("/accounting/invoices", methods=["GET"])
def invoices():
    try:
        return view_accounting.html_invoices()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/new", methods=["GET"])
def invoice_new():
    try:
        return view_accounting.html_invoice_new()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/create", methods=["POST"])
def invoice_create():
    try:
        return view_accounting.html_invoice_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/bulk-delete", methods=["POST"])
def invoice_bulk_delete():
    try:
        return view_accounting.html_invoice_bulk_delete()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>", methods=["GET"])
def invoice_edit(seq):
    try:
        return view_accounting.html_invoice_edit(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>/update", methods=["POST"])
def invoice_update(seq):
    try:
        return view_accounting.html_invoice_update(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>/state", methods=["POST"])
def invoice_state(seq):
    try:
        return view_accounting.html_invoice_state(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>/pay", methods=["POST"])
def invoice_pay(seq):
    try:
        return view_accounting.html_invoice_pay(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>/check-number", methods=["GET"])
def invoice_check_number(seq):
    try:
        return view_accounting.api_invoice_check_number(seq)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<int:seq>/print", methods=["GET"])
def invoice_print(seq):
    try:
        return view_accounting.html_invoice_print(seq)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@accounting_blueprint.route("/accounting/invoices/<path:ref>", methods=["GET"])
def invoice_legacy(ref):
    # Old links (/invoices/INV/2026/00004 or /invoices/<internal id>).
    try:
        return view_accounting.html_invoice_legacy(ref)
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

@accounting_blueprint.route("/accounting/<slug>", methods=["GET"])
def page(slug):
    try:
        return view_accounting.html_page(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def
