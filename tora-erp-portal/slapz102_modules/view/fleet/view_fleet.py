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

from fleet.fleet_proc import fleet_proc, VEHICLE_TYPES, OWNERSHIPS, DRIVER_TYPES
from shipments.shipments_proc import shipments_proc

# ---------------------------------------------------------------------------
# FLEET MODULE — view / render layer.
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
    proc = fleet_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["vehicles"] = proc.list_vehicles()
    data["drivers"] = proc.list_drivers()
    data["vehicle_types"] = VEHICLE_TYPES
    data["ownerships"] = OWNERSHIPS
    data["driver_types"] = DRIVER_TYPES
    return render_template("fleet.html", data=data)
# end def

@login_required
def html_create_vehicle():
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.vehicle_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = fleet_proc()
    result = proc.create_vehicle(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.vehicle_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_new_vehicle():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["vehicle_types"] = VEHICLE_TYPES
    data["ownerships"] = OWNERSHIPS
    data["vehicle"] = None
    return render_template("vehicle_form.html", data=data)
# end def

@login_required
def html_edit_vehicle(vehicle_id):
    vehicle = fleet_proc().get_vehicle(vehicle_id)
    if vehicle == None:
        return redirect(url_for("fleet_blueprint.index", error="Kendaraan tidak ditemukan"))
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["vehicle_types"] = VEHICLE_TYPES
    data["ownerships"] = OWNERSHIPS
    data["vehicle"] = vehicle
    return render_template("vehicle_form.html", data=data)
# end def

@login_required
def html_update_vehicle(vehicle_id):
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.vehicle_edit", vehicle_id=vehicle_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = fleet_proc().update_vehicle(vehicle_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.vehicle_edit", vehicle_id=vehicle_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_delete_vehicle(vehicle_id):
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = fleet_proc().delete_vehicle(vehicle_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_new_driver():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["driver_types"] = DRIVER_TYPES
    data["driver"] = None
    return render_template("driver_form.html", data=data)
# end def

@login_required
def html_edit_driver(driver_id):
    driver = fleet_proc().get_driver(driver_id)
    if driver == None:
        return redirect(url_for("fleet_blueprint.index", error="Sopir tidak ditemukan"))
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["driver_types"] = DRIVER_TYPES
    data["driver"] = driver
    return render_template("driver_form.html", data=data)
# end def

@login_required
def html_update_driver(driver_id):
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.driver_edit", driver_id=driver_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = fleet_proc().update_driver(driver_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.driver_edit", driver_id=driver_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_delete_driver(driver_id):
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = fleet_proc().delete_driver(driver_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_create_driver():
    if not csrf.validate():
        return redirect(url_for("fleet_blueprint.driver_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = fleet_proc()
    result = proc.create_driver(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("fleet_blueprint.driver_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("fleet_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def api_vehicles():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = fleet_proc()
    return jsonify(proc.search_vehicles(params.get("q", "")))
# end def

@login_required
def api_drivers():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = fleet_proc()
    return jsonify(proc.search_drivers(params.get("q", "")))
# end def
