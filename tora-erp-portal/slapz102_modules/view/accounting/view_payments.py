import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for
from flask_login import current_user
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize
from slapz102_stdlib import paginate

from accounting.accounting_proc import PAGES, MOVE_TYPES, today_iso
from accounting.payments_proc import payments_proc, STATE_LABELS, PAYMENT_TYPES, JOURNALS
from accounting.payments_proc import PARTNER_TYPES, PARTNER_CUSTOMER
from contacts.contacts_proc import PAYMENT_METHODS
from auth.auth_proc import access_required
from record_log.record_log_proc import record_log_proc
from view.record_log.view_record_log import actor_from_user
from view.accounting.view_accounting import base_data

# ---------------------------------------------------------------------------
# PEMBAYARAN (Pelanggan / Vendor) — view / render layer. Every handler takes
# partner_type ("customer" for /accounting/client-payments, "supplier" for
# /accounting/vendor-payments); PARTNER_TYPES holds labels and endpoints.
# Viewing needs "lihat", a new / Draft payment "tambah", Konfirmasi,
# Reset ke Draft, Batal and Tandai sebagai Terkirim "ubah", delete "hapus".
# ---------------------------------------------------------------------------

LOG_MODEL = "payment"


def _ep(partner_type, name):
    # "edit" -> "accounting_blueprint.customer_payment_edit" / ".vendor_payment_edit"
    return "accounting_blueprint." + PARTNER_TYPES[partner_type]["ep"] + "_" + name
# end def

def _list_ep(partner_type):
    return "accounting_blueprint." + PARTNER_TYPES[partner_type]["list_ep"]
# end def

def _meta(data, partner_type):
    pt = PARTNER_TYPES[partner_type]
    data["pt"] = pt
    data["page"] = PAGES[pt["slug"]]
    data["slug"] = pt["slug"]
    return data
# end def

def _url(seq, partner_type, **message):
    return url_for(_ep(partner_type, "edit"), seq=seq, **message)
# end def

def _result_redirect(seq, result, partner_type):
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(_url(seq, partner_type, **{key: result.get("desc", "")}))
# end def

def _not_found(partner_type):
    return redirect(url_for(_list_ep(partner_type), error="Pembayaran tidak ditemukan"))
# end def

def _form_data(pay, partner_type):
    proc = payments_proc()
    data = _meta(base_data(), partner_type)
    data["payment"] = pay
    data["payment_types"] = PAYMENT_TYPES
    data["journal_options"] = JOURNALS
    data["payment_methods"] = PAYMENT_METHODS
    data["state_labels"] = STATE_LABELS
    data["today"] = today_iso()
    data["next_number"] = proc.preview_number(partner_type)
    # Dokumen picker: open documents of this side.
    data["document_options"] = proc.document_options(partner_type)
    data["document"] = None
    data["log_groups"] = []
    if pay != None:
        data["log_groups"] = record_log_proc().list_groups(LOG_MODEL, pay["id"])
        doc = proc.document_of(pay)
        if doc != None:
            doc["url"] = url_for("accounting_blueprint." + MOVE_TYPES[doc["move_type"]]["ep"] + "_edit", seq=doc["seq"])
            data["document"] = doc
        # end if
    # end if
    return data
# end def

@access_required("accounting", "read")
def html_payments(partner_type=PARTNER_CUSTOMER):
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _meta(base_data(), partner_type)
    data["state"] = (params.get("state") or "").strip().upper()
    if data["state"] not in STATE_LABELS:
        data["state"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["state_labels"] = STATE_LABELS
    page, per_page = paginate.read_params(params)
    pager = payments_proc().page_payments(data["state"], data["q"], page, per_page, partner_type)
    data["payments"] = pager["payments"]
    data["pager"] = pager
    data["page_args"] = {"state": data["state"], "q": data["q"]}
    return render_template("accounting_payments.html", data=data)
# end def

@access_required("accounting", "create")
def html_payment_new(partner_type=PARTNER_CUSTOMER):
    pt = PARTNER_TYPES[partner_type]
    data = _form_data(None, partner_type)
    # ?invoice=<id>: start from a document (prefills partner + amount).
    params = sanitize.clean_html_dic(request.args.to_dict())
    data["prefill"] = {"payment_type": pt["default_type"], "invoice_id": "", "invoice_number": "",
                       "partner_id": "", "partner_name": "", "amount": 0}
    wanted = (params.get("invoice") or "").strip()
    for opt in data["document_options"]:
        if opt["value"] == wanted:
            data["prefill"] = {"payment_type": opt["payment_type"], "invoice_id": opt["value"], "invoice_number": opt["label"],
                               "partner_id": opt["partner_id"], "partner_name": opt["partner_name"], "amount": opt["residual"]}
        # end if
    # end for
    return render_template("accounting_payment_form.html", data=data)
# end def

@access_required("accounting", "read")
def html_payment_edit(seq, partner_type=PARTNER_CUSTOMER):
    pay = payments_proc().get_by_seq(seq, partner_type)
    if pay == None:
        return _not_found(partner_type)
    # end if
    data = _form_data(pay, partner_type)
    data["prefill"] = None
    return render_template("accounting_payment_form.html", data=data)
# end def

@access_required("accounting", "create")
def html_payment_create(partner_type=PARTNER_CUSTOMER):
    if not csrf.validate():
        return redirect(url_for(_ep(partner_type, "new"), error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = payments_proc()
    actor = actor_from_user(current_user)
    result = proc.create_payment(params, actor, partner_type)
    if result.get("status") != "SUCCESS":
        return redirect(url_for(_ep(partner_type, "new"), error=result.get("desc", "")))
    # end if
    if params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_url(result["seq"], partner_type, error="Disimpan, tetapi Anda tidak punya akses untuk mengkonfirmasi"))
        # end if
        return _result_redirect(result["seq"], proc.confirm_payment(result["id"], actor), partner_type)
    # end if
    return _result_redirect(result["seq"], result, partner_type)
# end def

@access_required("accounting", "create")
def html_payment_update(seq, partner_type=PARTNER_CUSTOMER):
    if not csrf.validate():
        return redirect(_url(seq, partner_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = payments_proc()
    pay = proc.get_by_seq(seq, partner_type)
    if pay == None:
        return _not_found(partner_type)
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    actor = actor_from_user(current_user)
    result = proc.update_payment(pay["id"], params, actor)
    if result.get("status") == "SUCCESS" and params.get("action") == "confirm":
        if not current_user.can("accounting", "update"):
            return redirect(_url(seq, partner_type, error="Disimpan, tetapi Anda tidak punya akses untuk mengkonfirmasi"))
        # end if
        result = proc.confirm_payment(pay["id"], actor)
    # end if
    return _result_redirect(seq, result, partner_type)
# end def

@access_required("accounting", "update")
def html_payment_state(seq, partner_type=PARTNER_CUSTOMER):
    if not csrf.validate():
        return redirect(_url(seq, partner_type, error="Sesi tidak valid, coba lagi"))
    # end if
    proc = payments_proc()
    pay = proc.get_by_seq(seq, partner_type)
    if pay == None:
        return _not_found(partner_type)
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    action = (params.get("action") or "").strip()
    actor = actor_from_user(current_user)
    if action == "reset":
        result = proc.reset_payment(pay["id"], actor)
    elif action == "cancel":
        result = proc.cancel_payment(pay["id"], actor)
    elif action == "sent":
        result = proc.mark_sent(pay["id"], actor)
    else:
        result = {"status": "ERROR", "desc": "Aksi tidak dikenal"}
    # end if
    return _result_redirect(seq, result, partner_type)
# end def

@access_required("accounting", "delete")
def html_payment_bulk_delete(partner_type=PARTNER_CUSTOMER):
    params = sanitize.clean_html_dic(request.form.to_dict())
    back = {"state": params.get("state", ""), "q": params.get("q", "")}
    if not csrf.validate():
        return redirect(url_for(_list_ep(partner_type), error="Sesi tidak valid, coba lagi", **back))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = payments_proc().delete_payments(ids, partner_type)
    key = "success" if result.get("status") == "SUCCESS" else "error"
    back[key] = result.get("desc", "")
    return redirect(url_for(_list_ep(partner_type), **back))
# end def
