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

from accounting.accounting_proc import accounting_proc, MENUS, PAGES, today_iso
from accounting.accounting_proc import MOVE_TYPES, MOVE_INVOICE, MOVE_BY_SLUG, JOURNAL_FILTERS
from accounting.accounting_proc import EFAKTUR_CODES, STATE_LABELS, STATE_POSTED
from accounting.accounting_proc import TAX_USES, TAX_SCOPES, TAX_BASES
from accounting.accounting_proc import ACCOUNT_GROUPS, ACCOUNT_TYPES, CODE_PREFIX_PATTERN
from accounting.payments_proc import payments_proc
from view.contacts import view_contacts
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

def base_data():
    # Shared page data for every Akuntansi screen (also view_payments).
    return _base_data()
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

# Every document handler below serves all four types (Faktur, Nota Kredit,
# Tagihan, Pengembalian): the blueprint passes move_type; MOVE_TYPES holds
# the differences (labels, endpoints, accounts, taxes, partner side).

def _ep(move_type, name):
    # "edit" -> "accounting_blueprint.invoice_edit" / ".bill_edit" / ...
    return "accounting_blueprint." + MOVE_TYPES[move_type]["ep"] + "_" + name
# end def

def _list_ep(move_type):
    return "accounting_blueprint." + MOVE_TYPES[move_type]["list_ep"]
# end def

def _invoice_url(seq, move_type=MOVE_INVOICE, **message):
    # Document form URL by running number (/accounting/client-invoices/4,
    # /accounting/client-credit-notes/2), with an optional success= / error= message.
    return url_for(_ep(move_type, "edit"), seq=seq, **message)
# end def

def _result_redirect(seq, result, move_type=MOVE_INVOICE):
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(_invoice_url(seq, move_type, **{key: result.get("desc", "")}))
# end def

def _not_found(move_type=MOVE_INVOICE):
    return redirect(url_for(_list_ep(move_type), error=MOVE_TYPES[move_type]["label"] + " tidak ditemukan"))
# end def

def _page_meta(data, move_type):
    doc = MOVE_TYPES[move_type]
    data["doc"] = doc
    data["page"] = PAGES[doc["slug"]]
    data["slug"] = doc["slug"]
    return data
# end def

def _invoice_form_data(inv, move_type=MOVE_INVOICE):
    proc = accounting_proc()
    data = _page_meta(_base_data(), move_type)
    data["invoice"] = inv
    data["crumb"] = None
    data["origin"] = None
    data["open_invoices"] = []
    used = []
    if inv != None:
        used = [line.get("tax", "") for line in inv.get("lines", [])]
    # end if
    doc = MOVE_TYPES[move_type]
    # Picker options: active accounts only, this side's group first. Lines
    # keep showing an account that was deactivated later (line.account_label).
    data["account_options"] = []
    for acc in proc.line_accounts(None, doc["account_group"]):
        data["account_options"].append({"value": acc["code"], "label": acc["label"], "description": acc.get("description", "")})
    # end for
    data["default_account"] = data["account_options"][0] if len(data["account_options"]) > 0 else {"value": "", "label": ""}
    data["taxes"] = proc.line_taxes(used, doc["tax_use"])
    # Refunds / corrections usually carry no tax; faktur / tagihan lines
    # default to PPN of their side.
    data["default_tax"] = doc["default_tax"]
    data["counterpart_account"] = proc.account_labels([doc["counterpart"]]).get(doc["counterpart"], doc["counterpart"])
    data["next_number"] = proc.preview_number(move_type)
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
def html_invoices(move_type=MOVE_INVOICE):
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _page_meta(_base_data(), move_type)
    data["state"] = (params.get("state") or "").strip().upper()
    if data["state"] not in STATE_LABELS:
        data["state"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["state_labels"] = STATE_LABELS
    page, per_page = paginate.read_params(params)
    pager = accounting_proc().page_invoices(data["state"], data["q"], page, per_page, move_type)
    data["invoices"] = pager["invoices"]
    data["pager"] = pager
    data["page_args"] = {"state": data["state"], "q": data["q"]}
    return render_template("accounting_invoices.html", data=data)
# end def

@access_required("accounting", "create")
def html_invoice_new(move_type=MOVE_INVOICE):
    proc = accounting_proc()
    data = _invoice_form_data(None, move_type)
    data["today"] = today_iso()
    if MOVE_TYPES[move_type]["is_refund"]:
        # From a faktur's "Nota Kredit" / tagihan's "Pengembalian" button:
        # ?invoice=<origin seq>
        params = sanitize.clean_html_dic(request.args.to_dict())
        try:
            origin_seq = int(params.get("invoice") or "0")
        except Exception:
            origin_seq = 0
        # end try
        if origin_seq > 0:
            data["origin"] = proc.refund_origin(origin_seq, move_type)
        # end if
    # end if
    return render_template("accounting_invoice_form.html", data=data)
# end def

@access_required("accounting", "read")
def html_invoice_legacy(ref, move_type=MOVE_INVOICE):
    # Old links by number or internal id -> the running-number URL.
    seq = accounting_proc().resolve_ref(sanitize.clean_html(ref), move_type)
    if seq == None:
        return _not_found(move_type)
    # end if
    return redirect(_invoice_url(seq, move_type, **sanitize.clean_html_dic(request.args.to_dict())))
# end def

@access_required("accounting", "read")
def html_invoice_edit(seq, move_type=MOVE_INVOICE):
    return _render_invoice_edit(seq, move_type)
# end def

def _render_invoice_edit(seq, move_type, crumb=None):
    # Document detail page. crumb = {"label", "url"} replaces the list link
    # in the breadcrumb (Entri Jurnal opens the same page under its name).
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return _not_found(move_type)
    # end if
    data = _invoice_form_data(inv, move_type)
    if crumb != None:
        data["crumb"] = crumb
        data["page"] = PAGES["journal-entries"]
        data["slug"] = "journal-entries"
    # end if
    params = sanitize.clean_html_dic(request.args.to_dict())
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["today"] = today_iso()
    data["journal"] = proc.journal_items(inv)
    data["log_groups"] = record_log_proc().list_groups(MOVE_TYPES[move_type]["log_model"], inv["id"])
    data["partner_email"] = proc.partner_email(inv.get("partner_id", ""))
    data["invoice_link"] = url_for(_ep(move_type, "print"), seq=inv["seq"], _external=True)
    if MOVE_TYPES[move_type]["is_refund"]:
        # Debet / Kredit belum lunas: this partner's open faktur / tagihan
        data["open_invoices"] = proc.open_invoices(inv.get("partner_id", ""), MOVE_TYPES[move_type]["origin"])
    # end if
    return render_template("accounting_invoice_form.html", data=data)
# end def

@access_required("accounting", "read")
def api_invoice_check_number(seq, move_type=MOVE_INVOICE):
    # Live warning on the Draft number field.
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return jsonify({"status": "ERROR", "desc": MOVE_TYPES[move_type]["label"] + " tidak ditemukan"}), 404
    # end if
    digits = sanitize.clean_html(request.args.get("n") or "")
    result = proc.check_number(inv, digits)
    if result.get("seq"):
        result["url"] = _invoice_url(result["seq"], move_type)
    # end if
    return jsonify(result)
# end def

@access_required("accounting", "read")
def html_invoice_print(seq, move_type=MOVE_INVOICE):
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return _not_found(move_type)
    # end if
    data = _page_meta(_base_data(), move_type)
    data["invoice"] = inv
    data["partner"] = proc.partner_card(inv.get("partner_id", ""))
    data["auto_print"] = request.args.get("print") == "1"
    return render_template("accounting_invoice_print.html", data=data)
# end def

@access_required("accounting", "create")
def html_invoice_create(move_type=MOVE_INVOICE):
    if not csrf.validate():
        return redirect(url_for(_ep(move_type, "new"), error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = accounting_proc()
    actor = actor_from_user(current_user)
    result = proc.create_invoice(params, _raw_lines(), actor, move_type)
    if result.get("status") != "SUCCESS":
        return redirect(url_for(_ep(move_type, "new"), error=result.get("desc", "")))
    # end if
    if params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_invoice_url(result["seq"], move_type, error="Anda tidak punya akses untuk mengkonfirmasi"))
        # end if
        return _result_redirect(result["seq"], proc.confirm_invoice(result["id"], actor), move_type)
    # end if
    return _result_redirect(result["seq"], result, move_type)
# end def

# Editing a Draft only needs "tambah" (create): whoever may create an
# invoice may keep editing it until it is confirmed. Konfirmasi, Batal,
# Reset ke Draft and Bayar need "ubah" (update).
@access_required("accounting", "create")
def html_invoice_update(seq, move_type=MOVE_INVOICE):
    if not csrf.validate():
        return redirect(_invoice_url(seq, move_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return _not_found(move_type)
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    actor = actor_from_user(current_user)
    result = proc.update_invoice(inv["id"], params, _raw_lines(), actor)
    if result.get("status") == "SUCCESS" and params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_invoice_url(seq, move_type, error="Disimpan, tetapi Anda tidak punya akses untuk mengkonfirmasi"))
        # end if
        result = proc.confirm_invoice(inv["id"], actor)
    # end if
    return _result_redirect(seq, result, move_type)
# end def

@access_required("accounting", "update")
def html_invoice_state(seq, move_type=MOVE_INVOICE):
    if not csrf.validate():
        return redirect(_invoice_url(seq, move_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return _not_found(move_type)
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
    return _result_redirect(seq, result, move_type)
# end def

@access_required("accounting", "update")
def html_invoice_pay(seq, move_type=MOVE_INVOICE):
    if not csrf.validate():
        return redirect(_invoice_url(seq, move_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    inv = proc.get_invoice_by_seq(seq, move_type)
    if inv == None:
        return _not_found(move_type)
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = payments_proc().pay_document(inv["id"], params, actor_from_user(current_user))
    return _result_redirect(seq, result, move_type)
# end def

@access_required("accounting", "update")
def html_credit_note_apply(seq, move_type):
    # Tambah in "Debet / Kredit belum lunas": settle an open faktur /
    # tagihan with this nota kredit / pengembalian.
    if not csrf.validate():
        return redirect(_invoice_url(seq, move_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = accounting_proc()
    cn = proc.get_invoice_by_seq(seq, move_type)
    if cn == None:
        return _not_found(move_type)
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = proc.apply_credit_note(cn["id"], (params.get("invoice_id") or "").strip(), actor_from_user(current_user))
    return _result_redirect(seq, result, move_type)
# end def

@access_required("accounting", "delete")
def html_invoice_bulk_delete(move_type=MOVE_INVOICE):
    params = sanitize.clean_html_dic(request.form.to_dict())
    back = {"state": params.get("state", ""), "q": params.get("q", "")}
    if not csrf.validate():
        return redirect(url_for(_list_ep(move_type), error="Sesi tidak valid, coba lagi", **back))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = accounting_proc().delete_invoices(ids, move_type)
    key = "success" if result.get("status") == "SUCCESS" else "error"
    back[key] = result.get("desc", "")
    return redirect(url_for(_list_ep(move_type), **back))
# end def

# ---------------------------------------------------------------------------
# Konfigurasi > Pengaturan (nomor dokumen)
# ---------------------------------------------------------------------------

CONFIG_PAGES = {
    "settings": {"label": "Pengaturan", "title": "Pengaturan Akuntansi", "menu": "Konfigurasi"},
    "accounts": {"label": "Bagan Akun", "title": "Bagan Akun", "menu": "Konfigurasi"},
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
# Konfigurasi > Bagan Akun
# ---------------------------------------------------------------------------

@access_required("accounting", "read")
def html_accounts():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["page"] = CONFIG_PAGES["accounts"]
    data["slug"] = "accounts"
    data["group"] = (params.get("group") or "").strip()
    if data["group"] not in ACCOUNT_GROUPS:
        data["group"] = ""
    # end if
    # ?prefix=1 / ?prefix=11 from the account-code tree on the left
    data["prefix"] = (params.get("prefix") or "").strip()
    if CODE_PREFIX_PATTERN.match(data["prefix"]) == None:
        data["prefix"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["account_groups"] = ACCOUNT_GROUPS
    proc = accounting_proc()
    page, per_page = paginate.read_params(params)
    pager = proc.page_accounts(data["group"], data["q"], page, per_page, data["prefix"])
    data["accounts"] = pager["accounts"]
    data["pager"] = pager
    data["tree"] = proc.account_tree()
    data["page_args"] = {"group": data["group"], "prefix": data["prefix"], "q": data["q"]}
    return render_template("accounting_accounts.html", data=data)
# end def

def _account_form_data(account):
    data = _base_data()
    data["page"] = CONFIG_PAGES["accounts"]
    data["slug"] = "accounts"
    data["account"] = account
    data["account_groups"] = ACCOUNT_GROUPS
    data["account_types"] = ACCOUNT_TYPES
    data["log_groups"] = []
    if account != None:
        data["log_groups"] = record_log_proc().list_groups("account", account["id"])
    # end if
    return data
# end def

@access_required("accounting", "create")
def html_account_new():
    return render_template("accounting_account_form.html", data=_account_form_data(None))
# end def

@access_required("accounting", "read")
def html_account_edit(code):
    account = accounting_proc().get_account(sanitize.clean_html(code))
    if account == None:
        return redirect(url_for("accounting_blueprint.accounts", error="Akun tidak ditemukan"))
    # end if
    return render_template("accounting_account_form.html", data=_account_form_data(account))
# end def

@access_required("accounting", "create")
def html_account_create():
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.account_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().create_account(params, actor_from_user(current_user))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("accounting_blueprint.account_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("accounting_blueprint.account_edit", code=result["code"], success=result.get("desc", "")))
# end def

@access_required("accounting", "update")
def html_account_update(code):
    code = sanitize.clean_html(code)
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.account_edit", code=code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().update_account(code, params, actor_from_user(current_user))
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.account_edit", code=code, **{key: result.get("desc", "")}))
# end def

@access_required("accounting", "update")
def html_account_toggle(code):
    # Aktif switch in the Bagan Akun list: fetch -> JSON, plain form -> redirect.
    is_fetch = request.headers.get("X-Requested-With", "") == "fetch"
    if not csrf.validate():
        if is_fetch:
            return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
        # end if
        return redirect(url_for("accounting_blueprint.accounts", error="Sesi tidak valid, coba lagi"))
    # end if
    result = accounting_proc().toggle_account(sanitize.clean_html(code), actor_from_user(current_user))
    if is_fetch:
        if result.get("status") != "SUCCESS":
            return jsonify(result), 400
        # end if
        return jsonify(result)
    # end if
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.accounts", **{key: result.get("desc", "")}))
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
    data["log_groups"] = []
    if tax != None:
        data["log_groups"] = record_log_proc().list_groups("tax", tax["id"])
    # end if
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
    result = accounting_proc().create_tax(params, actor_from_user(current_user))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("accounting_blueprint.tax_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("accounting_blueprint.tax_edit", code=result["code"], success=result.get("desc", "")))
# end def

@access_required("accounting", "update")
def html_tax_update(code):
    code = sanitize.clean_html(code)
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.tax_edit", code=code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = accounting_proc().update_tax(code, params, actor_from_user(current_user))
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.tax_edit", code=code, **{key: result.get("desc", "")}))
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
    result = accounting_proc().toggle_tax(sanitize.clean_html(code), actor_from_user(current_user))
    if request.headers.get("X-Requested-With", "") == "fetch":
        if result.get("status") != "SUCCESS":
            return jsonify(result), 400
        # end if
        return jsonify(result)
    # end if
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(url_for("accounting_blueprint.taxes", **{key: result.get("desc", "")}))
# end def

# ---------------------------------------------------------------------------
# Akuntansi > Entri Jurnal: every document in one list; a row opens the
# same document page under the "Entri Jurnal" breadcrumb.
# ---------------------------------------------------------------------------

ENTRY_STATE_ALL = "ALL"

@access_required("accounting", "read")
def html_journal_entries():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["page"] = PAGES["journal-entries"]
    data["slug"] = "journal-entries"
    # Default filter = Terekam, like the reference; ?state=ALL shows all.
    state = (params.get("state") or STATE_POSTED).strip().upper()
    if state != ENTRY_STATE_ALL and state not in STATE_LABELS:
        state = STATE_POSTED
    # end if
    data["state"] = state
    data["journal"] = (params.get("journal") or "").strip()
    if data["journal"] not in JOURNAL_FILTERS:
        data["journal"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["state_labels"] = STATE_LABELS
    data["journal_filters"] = JOURNAL_FILTERS
    data["state_all"] = ENTRY_STATE_ALL
    data["new_documents"] = [MOVE_TYPES[key] for key in MOVE_TYPES]
    page, per_page = paginate.read_params(params)
    pager = accounting_proc().page_journal_entries("" if state == ENTRY_STATE_ALL else state, data["journal"], data["q"], page, per_page)
    data["entries"] = pager["entries"]
    data["pager"] = pager
    data["page_args"] = {"state": state, "journal": data["journal"], "q": data["q"]}
    return render_template("accounting_journal_entries.html", data=data)
# end def

@access_required("accounting", "read")
def html_journal_entry(slug, seq):
    move_type = MOVE_BY_SLUG.get(sanitize.clean_html(slug))
    if move_type == None:
        return redirect(url_for("accounting_blueprint.journal_entries", error="Entri jurnal tidak ditemukan"))
    # end if
    return _render_invoice_edit(seq, move_type, {"label": "Entri Jurnal", "url": url_for("accounting_blueprint.journal_entries")})
# end def

@access_required("accounting", "delete")
def html_journal_entry_bulk_delete():
    params = sanitize.clean_html_dic(request.form.to_dict())
    back = {"state": params.get("state", ""), "journal": params.get("journal", ""), "q": params.get("q", "")}
    if not csrf.validate():
        return redirect(url_for("accounting_blueprint.journal_entries", error="Sesi tidak valid, coba lagi", **back))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = accounting_proc().delete_invoices(ids, None)
    key = "success" if result.get("status") == "SUCCESS" else "error"
    back[key] = result.get("desc", "")
    return redirect(url_for("accounting_blueprint.journal_entries", **back))
# end def

# ---------------------------------------------------------------------------
# Pelanggan / Vendor master lists: the Kontak list + form inside Akuntansi
# (/accounting/contact.CLIENT, /accounting/contact.VENDOR). Access is the
# Kontak access (checked by view_contacts); only the shell differs.
# ---------------------------------------------------------------------------

CONTACT_SHELLS = {
    "CLIENT": {"title": "Pelanggan", "menu": "Pelanggan"},
    "VENDOR": {"title": "Vendor", "menu": "Vendor"}
}

def _contact_shell(category):
    category = (category or "").strip().upper()
    meta = CONTACT_SHELLS.get(category)
    if meta == None:
        return None
    # end if
    return {
        "shell": "accounting",
        "base": "accounting_base.html",
        "title": meta["title"],
        "category": category,
        "args": {"category": category},
        "list_ep": "accounting_blueprint.contacts",
        "new_ep": "accounting_blueprint.contact_new",
        "edit_ep": "accounting_blueprint.contact_edit",
        "update_ep": "accounting_blueprint.contact_update",
        "create_ep": "accounting_blueprint.contact_create",
        "bulk_ep": "accounting_blueprint.contact_bulk_delete",
        "data": {
            "acc_menus": MENUS,
            "acc_pages": PAGES,
            "page": {"label": meta["title"], "title": meta["title"], "menu": meta["menu"]},
            "slug": "contact." + category
        }
    }
# end def

def _unknown_contact_shell():
    return redirect(url_for("accounting_blueprint.index", error="Halaman tidak ditemukan"))
# end def

def html_contacts(category):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_index(ct)
# end def

def html_contact_new(category):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_new(ct)
# end def

def html_contact_edit(category, contact_id):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_edit(sanitize.clean_html(contact_id), ct)
# end def

def html_contact_create(category):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_create(ct)
# end def

def html_contact_update(category, contact_id):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_update(sanitize.clean_html(contact_id), ct)
# end def

def html_contact_bulk_delete(category):
    ct = _contact_shell(sanitize.clean_html(category))
    if ct == None:
        return _unknown_contact_shell()
    # end if
    return view_contacts.html_bulk_delete(ct)
# end def

# Old URL prefixes (before the client- / vendor- naming) -> new prefix.
LEGACY_SLUGS = {
    "invoices": "client-invoices",
    "credit-notes": "client-credit-notes",
    "customer-payments": "client-payments",
    "sale-products": "client-products",
    "bills": "vendor-bills",
    "refunds": "vendor-refunds",
    "purchase-products": "vendor-products"
}

def html_legacy_redirect(old, rest=""):
    # /accounting/invoices/4?x=1 -> /accounting/client-invoices/4?x=1
    target = "/accounting/" + LEGACY_SLUGS[old]
    if rest:
        target = target + "/" + rest
    # end if
    query = request.query_string.decode("utf-8")
    if query:
        target = target + "?" + query
    # end if
    return redirect(target, code=301)
# end def

@access_required("accounting", "read")
def html_page(slug):
    slug = sanitize.clean_html(slug)
    if slug in LEGACY_SLUGS:
        return html_legacy_redirect(slug)
    # end if
    page = accounting_proc().page(slug)
    if page == None:
        return redirect(url_for("accounting_blueprint.index", error="Halaman tidak ditemukan"))
    # end if
    data = _base_data()
    data["slug"] = slug
    data["page"] = page
    return render_template("accounting_page.html", data=data)
# end def
