import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for
from flask_login import login_required, current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from shipments.shipments_proc import (
    shipments_proc, SERVICE_TYPES, SERVICE_CITIES, SHIPMENT_STATUSES,
    MANUAL_MILESTONES
)
from contacts.contacts_proc import contacts_proc
from auth.auth_proc import auth_proc

# ---------------------------------------------------------------------------
# SHIPMENTS MODULE — view / render layer.
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

def _contact_names(recs):
    # Resolve sender/receiver refs into display names for a list of shipments.
    cproc = contacts_proc()
    ids = []
    for rec in recs:
        ids.append(rec.get("sender_id", ""))
        ids.append(rec.get("receiver_id", ""))
    # end for
    return cproc.get_contacts_map(ids)
# end def

@login_required
def html_index():
    proc = shipments_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    filters = sanitize.clean_html_dic(request.args.to_dict())
    data["filters"] = filters
    data["statuses"] = SHIPMENT_STATUSES
    data["service_types"] = SERVICE_TYPES
    data["service_cities"] = SERVICE_CITIES
    shipments = proc.list_shipments(filters)
    contacts_map = _contact_names(shipments)
    for rec in shipments:
        sender = contacts_map.get(rec.get("sender_id", ""), None)
        receiver = contacts_map.get(rec.get("receiver_id", ""), None)
        rec["sender_name"] = sender.get("name", "") if sender != None else ""
        rec["receiver_name"] = receiver.get("name", "") if receiver != None else ""
    # end for
    data["shipments"] = shipments
    return render_template("shipments.html", data=data)
# end def

@login_required
def html_create():
    proc = shipments_proc()
    if request.method == "GET":
        data = _base_data()
        data["current_user"] = current_user
        data["form_error"] = (request.args.get("error") or "").strip()
        data["form_success"] = (request.args.get("success") or "").strip()
        data["service_types"] = SERVICE_TYPES
        data["service_cities"] = SERVICE_CITIES
        data["prefill_service"] = (request.args.get("service_type") or "LTL").upper()
        data["shipment"] = None
        return render_template("shipment_create.html", data=data)
    # end if
    if not csrf.validate():
        return redirect(url_for("shipments_blueprint.create", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = proc.create_shipment(params, str(current_user.id))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("shipments_blueprint.create", error=result.get("desc", "")))
    # end if
    return redirect(url_for(
        "shipments_blueprint.detail", tracking_code=result.get("tracking_code", ""),
        success="Order dibuat dengan nomor AWB " + result.get("tracking_code", "")
    ))
# end def

@login_required
def html_edit(tracking_code):
    proc = shipments_proc()
    shipment = proc.get_by_code(tracking_code)
    if shipment == None:
        return redirect(url_for("shipments_blueprint.index", error="Order tidak ditemukan"))
    # end if
    if shipment.get("status_utama") != "REGISTERED":
        return redirect(url_for("shipments_blueprint.detail", tracking_code=tracking_code, error="Order yang sudah masuk manifest tidak bisa diubah"))
    # end if
    cproc = contacts_proc()
    contacts_map = cproc.get_contacts_map([
        shipment.get("sender_id", ""), shipment.get("receiver_id", "")
    ])
    sender = contacts_map.get(shipment.get("sender_id", ""), None)
    receiver = contacts_map.get(shipment.get("receiver_id", ""), None)
    shipment["sender_name"] = sender.get("name", "") if sender != None else ""
    shipment["receiver_name"] = receiver.get("name", "") if receiver != None else ""
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["service_types"] = SERVICE_TYPES
    data["service_cities"] = SERVICE_CITIES
    data["prefill_service"] = shipment.get("service_type", "LTL")
    data["shipment"] = shipment
    return render_template("shipment_create.html", data=data)
# end def

@login_required
def html_update(tracking_code):
    if not csrf.validate():
        return redirect(url_for("shipments_blueprint.edit", tracking_code=tracking_code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = shipments_proc().update_shipment(tracking_code, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("shipments_blueprint.edit", tracking_code=tracking_code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("shipments_blueprint.detail", tracking_code=tracking_code, success=result.get("desc", "")))
# end def

@login_required
def html_delete(tracking_code):
    if not csrf.validate():
        return redirect(url_for("shipments_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = shipments_proc().delete_shipment(tracking_code)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("shipments_blueprint.detail", tracking_code=tracking_code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("shipments_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_detail(tracking_code):
    proc = shipments_proc()
    shipment = proc.get_by_code(tracking_code)
    if shipment == None:
        return "Not found", 404
    # end if
    cproc = contacts_proc()
    contacts_map = cproc.get_contacts_map([
        shipment.get("sender_id", ""), shipment.get("receiver_id", "")
    ])
    sender = contacts_map.get(shipment.get("sender_id", ""), None)
    receiver = contacts_map.get(shipment.get("receiver_id", ""), None)
    shipment["sender_name"] = sender.get("name", "") if sender != None else ""
    shipment["sender_company"] = sender.get("company_name", "") if sender != None else ""
    shipment["receiver_name"] = receiver.get("name", "") if receiver != None else ""
    shipment["receiver_company"] = receiver.get("company_name", "") if receiver != None else ""
    logs = proc.sorted_logs(shipment)
    user_ids = []
    for log in logs:
        user_ids.append(log.get("updated_by", ""))
    # end for
    users_map = auth_proc().get_users_map(user_ids)
    for log in logs:
        log["updated_by_name"] = users_map.get(log.get("updated_by", ""), log.get("updated_by", "SYSTEM"))
    # end for
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["shipment"] = shipment
    data["logs"] = logs
    data["manual_milestones"] = MANUAL_MILESTONES
    return render_template("shipment_detail.html", data=data)
# end def

@login_required
def html_add_log(tracking_code):
    if not csrf.validate():
        return redirect(url_for(
            "shipments_blueprint.detail", tracking_code=tracking_code,
            error="Sesi tidak valid, coba lagi"
        ))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = shipments_proc()
    result = proc.add_tracking_log(
        tracking_code,
        params.get("milestone_status", ""),
        params.get("location", ""),
        params.get("notes", ""),
        str(current_user.id)
    )
    if result.get("status") != "SUCCESS":
        return redirect(url_for(
            "shipments_blueprint.detail", tracking_code=tracking_code,
            error=result.get("desc", "")
        ))
    # end if
    return redirect(url_for(
        "shipments_blueprint.detail", tracking_code=tracking_code,
        success=result.get("desc", "")
    ))
# end def
