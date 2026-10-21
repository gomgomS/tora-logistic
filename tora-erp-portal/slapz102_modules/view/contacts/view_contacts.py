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

from contacts.contacts_proc import contacts_proc, CATEGORIES
from shipments.shipments_proc import shipments_proc

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

@login_required
def html_index():
    proc = contacts_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["category"] = (request.args.get("category") or "").strip().upper()
    data["q"] = (request.args.get("q") or "").strip()
    data["categories"] = CATEGORIES
    data["contacts"] = proc.list_contacts(data["category"], data["q"])
    return render_template("contacts.html", data=data)
# end def

@login_required
def html_new():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["categories"] = CATEGORIES
    data["contact"] = None
    return render_template("contact_form.html", data=data)
# end def

@login_required
def html_edit(contact_id):
    contact = contacts_proc().get_contact(contact_id)
    if contact == None:
        return redirect(url_for("contacts_blueprint.index", error="Kontak tidak ditemukan"))
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["categories"] = CATEGORIES
    data["contact"] = contact
    return render_template("contact_form.html", data=data)
# end def

@login_required
def html_update(contact_id):
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.edit_contact", contact_id=contact_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = contacts_proc().update_contact(contact_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("contacts_blueprint.edit_contact", contact_id=contact_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("contacts_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
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

@login_required
def html_create():
    if not csrf.validate():
        return redirect(url_for("contacts_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = contacts_proc()
    result = proc.create_contact(params)
    # Inline creation during order entry sends "next" so the user lands back
    # on the form they came from; only same-site relative paths are honored.
    next_url = (params.get("next") or "").strip()
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
    result = contacts_proc().create_contact(params)
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
