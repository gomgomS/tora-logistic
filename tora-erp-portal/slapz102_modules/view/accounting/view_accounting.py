import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for, jsonify
from flask_login import current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from slapz102_stdlib import paginate

from accounting.accounting_proc import accounting_proc, MENUS, PAGES, LOG_MODEL, today_iso
from accounting.accounting_proc import REVENUE_ACCOUNTS, EFAKTUR_CODES, STATE_LABELS, DEFAULT_SALE_TAX
from accounting.accounting_proc import TAX_USES, TAX_SCOPES, TAX_BASES
from contacts.contacts_proc import PAYMENT_TERMS, PAYMENT_METHODS, FISCAL_POSITIONS
from auth.auth_proc import auth_proc, access_required
from shipments.shipments_proc import shipments_proc
from record_log.record_log_proc import record_log_proc
from view.record_log.view_record_log import actor_from_user

# ---------------------------------------------------------------------------
# ACCOUNTING MODULE — view / render layer.
# ---------------------------------------------------------------------------

def _base_data():
    params = sanitize.clean_html_dic(request.args.to_dict())
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": shipments_proc().sidebar_counts(),
        "current_user": current_user,
        "form_error": (params.get("error") or "").strip(),
        "form_success": (params.get("success") or "").strip(),
        "acc_menus": MENUS,
        "acc_pages": PAGES
    }
# end def

@access_required("accounting", "read")
def html_index():
    data = _base_data()
    data["journals"] = accounting_proc().dashboard_journals()
    return render_template("accounting_dashboard.html", data=data)
# end def

# ---------------------------------------------------------------------------
# Faktur Pelanggan
# ---------------------------------------------------------------------------

def _raw_lines():
    # Invoice lines arrive as parallel arrays (line_product[], ...).
    products = request.form.getlist("line_product")
    accounts = request.form.getlist("line_account")
    quantities = request.form.getlist("line_quantity")
    prices = request.form.getlist("line_price")
    taxes = request.form.getlist("line_tax")
    out = []
    for i in range(len(products)):
        out.append({
            "product": sanitize.clean_html(products[i]),
            "account": sanitize.clean_html(accounts[i] if i < len(accounts) else ""),
            "quantity": sanitize.clean_html(quantities[i] if i < len(quantities) else ""),
            "price_unit": sanitize.clean_html(prices[i] if i < len(prices) else ""),
            "tax": sanitize.clean_html(taxes[i] if i < len(taxes) else "")
        })
    # end for
    return out
# end def

def _invoice_url(seq, **message):
    # Faktur form URL by running number (/accounting/invoices/4), with an
    # optional success= / error= flash message.
    return url_for("accounting_blueprint.invoice_edit", seq=seq, **message)
# end def

def _result_redirect(seq, result):
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(_invoice_url(seq, **{key: result.get("desc", "")}))
# end def

def _not_found():
    return redirect(url_for("accounting_blueprint.invoices", error="Faktur tidak ditemukan"))
# end def

def _invoice_form_data(inv):
    proc = accounting_proc()
    data = _base_data()
    data["page"] = PAGES["invoices"]
    data["slug"] = "invoices"
    data["invoice"] = inv
    data["accounts"] = REVENUE_ACCOUNTS
    used = []
    if inv != None:
        used = [line.get("tax", "") for line in inv.get("lines", [])]
    # end if
    data["taxes"] = proc.sale_taxes(used)
    data["default_tax"] = DEFAULT_SALE_TAX
    data["next_number"] = proc.preview_number("out_invoice")
    data["efaktur_codes"] = EFAKTUR_CODES
    data["payment_terms"] = PAYMENT_TERMS
    data["payment_methods"] = PAYMENT_METHODS
    data["partner_email"] = ""
    data["invoice_link"] = ""
    data["fiscal_positions"] = FISCAL_POSITIONS
    data["salespeople"] = auth_proc().list_user_options()
    data["state_labels"] = STATE_LABELS
    data["journal"] = None
    data["log_groups"] = []
    return data
# end def

@access_required("accounting", "read")
def html_invoices():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["page"] = PAGES["invoices"]
    data["slug"] = "invoices"
    data["state"] = (params.get("state") or "").strip().upper()
    if data["state"] not in STATE_LABELS:
        data["state"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["state_labels"] = STATE_LABELS
    page, per_page = paginate.read_params(params)
    pager = accounting_proc().page_invoices(data["state"], data["q"], page, per_page)
    data["invoices"] = pager["invoices"]
    data["pager"] = pager
    data["page_args"] = {"state": data["state"], "q": data["q"]}
    return render_template("accounting_invoices.html", data=data)
# end def

@access_required("accounting", "create")
def html_invoice_new():
    data = _invoice_form_data(None)
    data["today"] = today_iso()
    return render_template("accounting_invoice_form.html", data=data)
# end def

@access_required("accounting", "read")
def html_invoice_legacy(ref):
    # Old links by invoice number or internal id -> the running-number URL.
    seq = accounting_proc().resolve_ref(sanitize.clean_html(ref))
    if seq == None:
        return _not_found()
    # end if
    return redirect(_invoice_url(seq, **sanitize.clean_html_dic(request.args.to_dict())))
# end def

@access_required("accounting", "read")
def html_invoice_edit(seq):
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return _not_found()
    # end if
    data = _invoice_form_data(inv)
    params = sanitize.clean_html_dic(request.args.to_dict())
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["today"] = today_iso()
    data["journal"] = proc.journal_items(inv)
    data["log_groups"] = record_log_proc().list_groups(LOG_MODEL, inv["id"])
    data["partner_email"] = proc.partner_email(inv.get("partner_id", ""))
    data["invoice_link"] = url_for("accounting_blueprint.invoice_print", seq=inv["seq"], _external=True)
    return render_template("accounting_invoice_form.html", data=data)
# end def

@access_required("accounting", "read")
def api_invoice_check_number(seq):
    # Live warning on the Draft number field.
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return jsonify({"status": "ERROR", "desc": "Faktur tidak ditemukan"}), 404
    # end if
    digits = sanitize.clean_html(request.args.get("n") or "")
    result = proc.check_number(inv, digits)
    if result.get("seq"):
        result["url"] = _invoice_url(result["seq"])
    # end if
    return jsonify(result)
# end def

@access_required("accounting", "read")
def html_invoice_print(seq):
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return _not_found()
    # end if
    data = _base_data()
    data["invoice"] = inv
    data["partner"] = proc.partner_card(inv.get("partner_id", ""))
    data["auto_print"] = request.args.get("print") == "1"
    return render_template("accounting_invoice_print.html", data=data)
# end def

@access_required("accounting", "create")
def html_invoice_create():
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.invoice_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = accounting_proc()
    actor = actor_from_user(current_user)
    result = proc.create_invoice(params, _raw_lines(), actor)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("accounting_blueprint.invoice_new", error=result.get("desc", "")))
    # end if
    if params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_invoice_url(result["seq"], error="Anda tidak punya akses untuk mengkonfirmasi faktur"))
        # end if
        return _result_redirect(result["seq"], proc.confirm_invoice(result["id"], actor))
    # end if
    return _result_redirect(result["seq"], result)
# end def

# Editing a Draft only needs "tambah" (create): whoever may create an
# invoice may keep editing it until it is confirmed. Konfirmasi, Batal,
# Reset ke Draft and Bayar need "ubah" (update).
@access_required("accounting", "create")
def html_invoice_update(seq):
    if not csrf.validate():
        return redirect(_invoice_url(seq, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return _not_found()
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    actor = actor_from_user(current_user)
    result = proc.update_invoice(inv["id"], params, _raw_lines(), actor)
    if result.get("status") == "SUCCESS" and params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_invoice_url(seq, error="Faktur disimpan, tetapi Anda tidak punya akses untuk mengkonfirmasi"))
        # end if
        result = proc.confirm_invoice(inv["id"], actor)
    # end if
    return _result_redirect(seq, result)
# end def

@access_required("accounting", "update")
def html_invoice_state(seq):
    if not csrf.validate():
        return redirect(_invoice_url(seq, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return _not_found()
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    action = (params.get("action") or "").strip()
    actor = actor_from_user(current_user)
    if action == "reset":
        result = proc.reset_invoice(inv["id"], actor)
    elif action == "cancel":
        result = proc.cancel_invoice(inv["id"], actor)
    else:
        result = {"status": "ERROR", "desc": "Aksi tidak dikenal"}
    # end if
    return _result_redirect(seq, result)
# end def

@access_required("accounting", "update")
def html_invoice_pay(seq):
    if not csrf.validate():
        return redirect(_invoice_url(seq, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq)
    if inv == None:
        return _not_found()
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = proc.register_payment(inv["id"], params, actor_from_user(current_user))
    return _result_redirect(seq, result)
# end def

@access_required("accounting", "delete")
def html_invoice_bulk_delete():
    params = sanitize.clean_html_dic(request.form.to_dict())
    back = {"state": params.get("state", ""), "q": params.get("q", "")}
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.invoices", error="Sesi tidak valid, coba lagi", **back))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = accounting_proc().delete_invoices(ids)
    key = "success" if result.get("status") == "SUCCESS" else "error"
    back[key] = result.get("desc", "")
    return redirect(url_for("accounting_blueprint.invoices", **back))
# end def

# ---------------------------------------------------------------------------
# Konfigurasi > Pengaturan (nomor dokumen)
# ---------------------------------------------------------------------------

CONFIG_PAGES = {
    "settings": {"label": "Pengaturan", "title": "Pengaturan Akuntansi", "menu": "Konfigurasi"},
    "taxes": {"label": "Pajak", "title": "Pajak", "menu": "Konfigurasi"}
}

@access_required("accounting", "read")
def html_settings():
    data = _base_data()
    data["page"] = CONFIG_PAGES["settings"]
    data["slug"] = "settings"
    data["sequences"] = accounting_proc().get_sequences()
    data["can_edit"] = current_user.can("accounting", "update")
    data["today"] = today_iso()
    return render_template("accounting_settings.html", data=data)
# end def

@access_required("accounting", "update")
def html_settings_save():
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.settings", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().save_sequences(params)
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.settings", **{key: result.get("desc", "")}))
# end def

# ---------------------------------------------------------------------------
# Konfigurasi > Pajak
# ---------------------------------------------------------------------------

@access_required("accounting", "read")
def html_taxes():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["page"] = CONFIG_PAGES["taxes"]
    data["slug"] = "taxes"
    data["tax_use"] = (params.get("tax_use") or "").strip()
    if data["tax_use"] not in TAX_USES:
        data["tax_use"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["tax_uses"] = TAX_USES
    page, per_page = paginate.read_params(params)
    pager = accounting_proc().page_taxes(data["tax_use"], data["q"], page, per_page)
    data["taxes"] = pager["taxes"]
    data["pager"] = pager
    data["page_args"] = {"tax_use": data["tax_use"], "q": data["q"]}
    return render_template("accounting_taxes.html", data=data)
# end def

def _tax_form_data(tax):
    data = _base_data()
    data["page"] = CONFIG_PAGES["taxes"]
    data["slug"] = "taxes"
    data["tax"] = tax
    data["tax_uses"] = TAX_USES
    data["tax_scopes"] = TAX_SCOPES
    data["tax_bases"] = TAX_BASES
    return data
# end def

@access_required("accounting", "create")
def html_tax_new():
    return render_template("accounting_tax_form.html", data=_tax_form_data(None))
# end def

@access_required("accounting", "read")
def html_tax_edit(code):
    tax = accounting_proc().get_tax(sanitize.clean_html(code))
    if tax == None:
        return redirect(url_for("accounting_blueprint.taxes", error="Pajak tidak ditemukan"))
    # end if
    return render_template("accounting_tax_form.html", data=_tax_form_data(tax))
# end def

@access_required("accounting", "create")
def html_tax_create():
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.tax_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().create_tax(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("accounting_blueprint.tax_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("accounting_blueprint.taxes", success=result.get("desc", "")))
# end def

@access_required("accounting", "update")
def html_tax_update(code):
    code = sanitize.clean_html(code)
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.tax_edit", code=code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().update_tax(code, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("accounting_blueprint.tax_edit", code=code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("accounting_blueprint.taxes", success=result.get("desc", "")))
# end def

@access_required("accounting", "update")
def html_tax_toggle(code):
    # Aktif switch in the Pajak list: fetch -> JSON, plain form -> redirect.
    if not csrf.validate():
        if request.headers.get("X-Requested-With", "") == "fetch":
            return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
        # end if
        return redirect(url_for("accounting_blueprint.taxes", error="Sesi tidak valid, coba lagi"))
    # end if
    result = accounting_proc().toggle_tax(sanitize.clean_html(code))
    if request.headers.get("X-Requested-With", "") == "fetch":
        if result.get("status") != "SUCCESS":
            return jsonify(result), 400
        # end if
        return jsonify(result)
    # end if
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.taxes", **{key: result.get("desc", "")}))
# end def

@access_required("accounting", "read")
def html_page(slug):
    slug = sanitize.clean_html(slug)
    page = accounting_proc().page(slug)
    if page == None:
        return redirect(url_for("accounting_blueprint.index", error="Halaman tidak ditemukan"))
    # end if
    data = _base_data()
    data["slug"] = slug
    data["page"] = page
    return render_template("accounting_page.html", data=data)
# end def
