import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for, jsonify
from flask_login import login_required, current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize
from slapz102_stdlib import paginate

from contacts.contacts_proc import contacts_proc, CATEGORIES
from contacts.contacts_proc import PAYMENT_TERMS, PAYMENT_METHODS, FISCAL_POSITIONS, INDUSTRIES
from contacts.contacts_proc import LOG_MODEL
from shipments.shipments_proc import shipments_proc
from auth.auth_proc import auth_proc, access_required
from record_log.record_log_proc import record_log_proc
from view.record_log.view_record_log import actor_from_user

# ---------------------------------------------------------------------------
# CONTACTS MODULE — view / render layer.
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": shipments_proc().sidebar_counts()
    }
# end def

@access_required("contacts", "read")
def html_index():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["category"] = (params.get("category") or "").strip().upper()
    data["q"] = (params.get("q") or "").strip()
    data["categories"] = CATEGORIES
    page, per_page = paginate.read_params(params)
    pager = contacts_proc().page_contacts(data["category"], data["q"], page, per_page)
    data["contacts"] = pager["contacts"]
    data["pager"] = pager
    data["page_args"] = {"category": data["category"], "q": data["q"]}
    return render_template("contacts.html", data=data)
# end def

@access_required("contacts", "delete")
def html_bulk_delete():
    params = sanitize.clean_html_dic(request.form.to_dict())
    category = (params.get("category") or "").strip().upper()
    q = (params.get("q") or "").strip()
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.index", category=category, q=q, error="Sesi tidak valid, coba lagi"))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = contacts_proc().delete_contacts(ids)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("contacts_blueprint.index", category=category, q=q, error=result.get("desc", "")))
    # end if
    return redirect(url_for("contacts_blueprint.index", category=category, q=q, success=result.get("desc", "")))
# end def

def _form_data(contact, params):
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (params.get("error") or "").strip()
    data["categories"] = CATEGORIES
    data["payment_terms"] = PAYMENT_TERMS
    data["payment_methods"] = PAYMENT_METHODS
    data["fiscal_positions"] = FISCAL_POSITIONS
    data["industries"] = INDUSTRIES
    data["salespeople"] = auth_proc().list_user_options()
    data["contact"] = contact
    data["related"] = []
    data["log_groups"] = []
    return data
# end def

@access_required("contacts", "create")
def html_new():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _form_data(None, params)
    # "Tambah kontak terkait" opens the form with the company prefilled.
    data["prefill_company"] = (params.get("company") or "").strip()
    return render_template("contact_form.html", data=data)
# end def

@access_required("contacts", "read")
def html_edit(contact_id):
    proc = contacts_proc()
    contact = proc.get_contact(contact_id)
    if contact == None:
        return redirect(url_for("contacts_blueprint.index", error="Kontak tidak ditemukan"))
    # end if
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _form_data(contact, params)
    data["prefill_company"] = ""
    data["form_success"] = (params.get("success") or "").strip()
    data["related"] = proc.related_contacts(contact)
    data["log_groups"] = record_log_proc().list_groups(LOG_MODEL, contact["id"])
    return render_template("contact_form.html", data=data)
# end def

@access_required("contacts", "update")
def html_update(contact_id):
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.edit_contact", contact_id=contact_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = contacts_proc().update_contact(contact_id, params, actor_from_user(current_user))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("contacts_blueprint.edit_contact", contact_id=contact_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("contacts_blueprint.edit_contact", contact_id=contact_id, success=result.get("desc", "")))
# end def

@access_required("contacts", "delete")
def html_delete(contact_id):
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = contacts_proc().delete_contact(contact_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("contacts_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("contacts_blueprint.index", success=result.get("desc", "")))
# end def

@access_required("contacts", "create")
def html_create():
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = contacts_proc()
    result = proc.create_contact(params, actor_from_user(current_user))
    # Inline creation during order entry sends "next" so the user lands back
    # on the form they came from; only same-site relative paths are honored.
    # The contact form sends no "next": it opens the saved record (with its
    # activity log) instead.
    next_url = (params.get("next") or "").strip()
    if next_url == "" and result.get("status") == "SUCCESS":
        return redirect(url_for("contacts_blueprint.edit_contact", contact_id=result.get("id", ""), success=result.get("desc", "")))
    # end if
    if next_url == "" or not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("contacts_blueprint.index")
    # end if
    joiner = "&" if "?" in next_url else "?"
    if result.get("status") != "SUCCESS":
        if next_url == url_for("contacts_blueprint.index"):
            next_url = url_for("contacts_blueprint.new_contact")
            joiner = "?"
        # end if
        return redirect(next_url + joiner + "error=" + result.get("desc", "").replace(" ", "+"))
    # end if
    return redirect(next_url + joiner + "success=" + result.get("desc", "").replace(" ", "+"))
# end def

@login_required
def api_create():
    if not csrf.validate():
        return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = contacts_proc().create_contact(params, actor_from_user(current_user))
    if result.get("status") != "SUCCESS":
        return jsonify(result), 400
    # end if
    return jsonify(result)
# end def

@login_required
def api_search():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = contacts_proc()
    payload = proc.search_contacts(
        params.get("category", ""), params.get("q", "")
    )
    return jsonify(payload)
# end def
