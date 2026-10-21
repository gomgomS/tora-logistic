import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import jsonify, render_template, redirect, request, url_for
from flask_login import login_required, current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from manifests.manifests_proc import manifests_proc, MANIFEST_STATUSES
from shipments.shipments_proc import shipments_proc, SERVICE_CITIES
from fleet.fleet_proc import fleet_proc
from contacts.contacts_proc import contacts_proc

# ---------------------------------------------------------------------------
# MANIFESTS MODULE — view / render layer.
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

def _enrich_manifests(recs):
    # Join vehicle / driver / shipment-count info for list rendering.
    fproc = fleet_proc()
    vehicle_map = fproc.get_vehicles_map([rec.get("vehicle_id", "") for rec in recs])
    driver_map = fproc.get_drivers_map([rec.get("driver_id", "") for rec in recs])
    for rec in recs:
        vehicle = vehicle_map.get(rec.get("vehicle_id", ""), None)
        driver = driver_map.get(rec.get("driver_id", ""), None)
        rec["vehicle_label"] = ""
        if vehicle != None:
            rec["vehicle_label"] = vehicle.get("plate_number", "") + " (" + vehicle.get("vehicle_type", "") + ")"
        # end if
        rec["driver_name"] = driver.get("contact_name", "") if driver != None else ""
        rec["shipment_count"] = len(rec.get("shipment_ids", []))
    # end for
# end def

@login_required
def html_index():
    proc = manifests_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["status_filter"] = (request.args.get("status") or "").strip().upper()
    data["statuses"] = MANIFEST_STATUSES
    manifests = proc.list_manifests(data["status_filter"])
    _enrich_manifests(manifests)
    data["manifests"] = manifests
    return render_template("manifests.html", data=data)
# end def

@login_required
def html_create():
    proc = manifests_proc()
    sproc = shipments_proc()
    if request.method == "GET":
        data = _base_data()
        data["current_user"] = current_user
        data["form_error"] = (request.args.get("error") or "").strip()
        data["form_success"] = (request.args.get("success") or "").strip()
        data["service_cities"] = SERVICE_CITIES
        # Candidate shipments: fresh orders + hub-sorted cargo. The hub page
        # is the guided flow; this page allows manual cherry-picking.
        candidates = sproc.available_for_manifest()
        data["candidates"] = candidates
        data["default_origin"] = (request.args.get("origin") or "").strip()
        data["default_destination"] = (request.args.get("destination") or "").strip()
        data["routes"] = proc.list_routes()
        return render_template("manifest_create.html", data=data)
    # end if
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.create", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    params["shipment_ids"] = [sanitize.clean_html(x) for x in request.form.getlist("shipment_ids")]
    result = proc.create_manifest(params, str(current_user.id))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.create", error=result.get("desc", "")))
    # end if
    return redirect(url_for(
        "manifests_blueprint.detail", manifest_code=result.get("manifest_code", ""),
        success=result.get("desc", "")
    ))
# end def

@login_required
def html_detail(manifest_code):
    proc = manifests_proc()
    manifest = proc.get_by_code(manifest_code)
    if manifest == None:
        return "Not found", 404
    # end if
    sproc = shipments_proc()
    shipments = sproc.get_shipments_by_ids(manifest.get("shipment_ids", []))
    _enrich_manifests([manifest])
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["manifest"] = manifest
    data["shipments"] = shipments
    data["journey"] = proc.journey(manifest)
    data["next_statuses"] = proc.next_statuses(manifest.get("status", "PLANNED"))
    vehicles, drivers = _fleet_choices()
    data["vehicles"] = vehicles
    data["drivers"] = drivers
    return render_template("manifest_detail.html", data=data)
# end def

@login_required
def html_update_fleet(manifest_code):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.detail", manifest_code=manifest_code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = manifests_proc().update_manifest_fleet(manifest_code, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.detail", manifest_code=manifest_code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.detail", manifest_code=manifest_code, success=result.get("desc", "")))
# end def

@login_required
def html_delete_manifest(manifest_code):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = manifests_proc().delete_manifest(manifest_code)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.detail", manifest_code=manifest_code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_update(manifest_code):
    if not csrf.validate():
        return redirect(url_for(
            "manifests_blueprint.detail", manifest_code=manifest_code,
            error="Sesi tidak valid, coba lagi"
        ))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = manifests_proc()
    result = proc.update_status(
        manifest_code,
        params.get("status", ""),
        params.get("location", ""),
        params.get("notes", ""),
        str(current_user.id)
    )
    if result.get("status") != "SUCCESS":
        return redirect(url_for(
            "manifests_blueprint.detail", manifest_code=manifest_code,
            error=result.get("desc", "")
        ))
    # end if
    return redirect(url_for(
        "manifests_blueprint.detail", manifest_code=manifest_code,
        success=result.get("desc", "")
    ))
# end def

@login_required
def html_advance(manifest_code):
    if not csrf.validate():
        return redirect(url_for(
            "manifests_blueprint.detail", manifest_code=manifest_code,
            error="Sesi tidak valid, coba lagi"
        ))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = manifests_proc()
    if params.get("step", "") == "back":
        result = proc.retreat(manifest_code, str(current_user.id))
    else:
        result = proc.advance(manifest_code, str(current_user.id))
    # end if
    if result.get("status") != "SUCCESS":
        return redirect(url_for(
            "manifests_blueprint.detail", manifest_code=manifest_code,
            error=result.get("desc", "")
        ))
    # end if
    return redirect(url_for(
        "manifests_blueprint.detail", manifest_code=manifest_code,
        success=result.get("desc", "")
    ))
# end def

def _hub_query_args(destination, error, success):
    args = {}
    if destination != "":
        args["destination"] = destination
    # end if
    if error != "":
        args["error"] = error
    # end if
    if success != "":
        args["success"] = success
    # end if
    return args
# end def


def _fill_party(rec, contacts_map):
    sender = contacts_map.get(rec.get("sender_id", ""), None)
    receiver = contacts_map.get(rec.get("receiver_id", ""), None)
    rec["sender_name"] = sender.get("name", "") if sender != None else ""
    rec["sender_phone"] = sender.get("phone", "") if sender != None else ""
    rec["receiver_name"] = receiver.get("name", "") if receiver != None else ""
    rec["receiver_phone"] = receiver.get("phone", "") if receiver != None else ""
    address = (rec.get("destination_address") or "").strip()
    if address == "" and receiver != None:
        address = (receiver.get("address") or "").strip()
    # end if
    rec["receiver_address"] = address
# end def


def _desk_data(hub_name, hub_id, destination, hub_info=None):
    proc = manifests_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["service_cities"] = SERVICE_CITIES
    data["hub"] = hub_name
    data["hub_id"] = hub_id
    data["hub_info"] = hub_info
    data["destination"] = destination
    cargo = proc.hub_shipments(hub_name, destination)
    runs = proc.open_deliveries(hub_name)
    party_ids = []
    for rec in cargo:
        party_ids.append(rec.get("sender_id", ""))
        party_ids.append(rec.get("receiver_id", ""))
    # end for
    for run in runs:
        for rec in run.get("shipments") or []:
            party_ids.append(rec.get("sender_id", ""))
            party_ids.append(rec.get("receiver_id", ""))
        # end for
    # end for
    contacts_map = contacts_proc().get_contacts_map(party_ids)
    for rec in cargo:
        _fill_party(rec, contacts_map)
    # end for
    moving = 0
    for run in runs:
        for rec in run.get("shipments") or []:
            _fill_party(rec, contacts_map)
            moving = moving + 1
        # end for
    # end for
    antar = []
    feeder = []
    for rec in cargo:
        if proc.ready_for_antar(hub_name, rec):
            antar.append(rec)
        else:
            feeder.append(rec)
        # end if
    # end for
    data["antar"] = antar
    data["feeder"] = feeder
    data["runs"] = runs
    data["moving"] = moving
    if hub_id != "":
        data["page_url"] = url_for("manifests_blueprint.hub_desk", hub_id=hub_id)
    else:
        data["page_url"] = url_for("manifests_blueprint.hub", hub=hub_name)
    # end if
    return data
# end def


@login_required
def html_hub():
    proc = manifests_proc()
    params = sanitize.clean_html_dic(request.args.to_dict())
    hub = (params.get("hub") or "").strip()
    destination = (params.get("destination") or "").strip()
    query = (params.get("q") or "").strip()
    if hub != "":
        found = proc._find_hub_by_name(hub)
        if found != None:
            return redirect(url_for(
                "manifests_blueprint.hub_desk",
                hub_id=str(found["_id"]),
                **_hub_query_args(
                    destination,
                    (request.args.get("error") or "").strip(),
                    (request.args.get("success") or "").strip()
                )
            ))
        # end if
        return render_template("hub_desk.html", data=_desk_data(hub, "", destination))
    # end if
    hubs = proc.list_hubs()
    if query != "":
        narrowed = []
        needle = query.lower()
        for item in hubs:
            if needle in (item.get("name") or "").lower():
                narrowed.append(item)
            # end if
        # end for
        hubs = narrowed
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["hubs"] = hubs
    data["q"] = query
    return render_template("hub.html", data=data)
# end def


@login_required
def html_hub_desk(hub_id):
    proc = manifests_proc()
    hub = proc.get_hub(hub_id)
    if hub == None:
        return redirect(url_for("manifests_blueprint.hub", error="Hub tidak ditemukan"))
    # end if
    destination = (request.args.get("destination") or "").strip()
    return render_template("hub_desk.html", data=_desk_data(hub.get("name", ""), hub["id"], destination, hub))
# end def


def _hub_back(hub, result):
    key = "success"
    if result.get("status") != "SUCCESS":
        key = "error"
    # end if
    found = manifests_proc()._find_hub_by_name(hub)
    args = {key: result.get("desc", "")}
    if found != None:
        return redirect(url_for(
            "manifests_blueprint.hub_desk",
            hub_id=str(found["_id"]),
            **args
        ))
    # end if
    args["hub"] = hub
    return redirect(url_for("manifests_blueprint.hub", **args))
# end def


@login_required
def html_start_antar():
    if not csrf.validate():
        hub = (request.form.get("hub") or "").strip()
        return redirect(url_for("manifests_blueprint.hub", hub=hub, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    hub = (params.get("hub") or "").strip()
    shipment_ids = [sanitize.clean_html(x) for x in request.form.getlist("shipment_ids")]
    result = manifests_proc().start_delivery(
        hub, shipment_ids, params.get("vehicle_id", ""), params.get("driver_id", ""),
        str(current_user.id)
    )
    return _hub_back(hub, result)
# end def


@login_required
def html_antar_deliver(code):
    if not csrf.validate():
        hub = (request.form.get("hub") or "").strip()
        return redirect(url_for("manifests_blueprint.hub", hub=hub, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    hub = (params.get("hub") or "").strip()
    result = manifests_proc().deliver_shipment(
        code, params.get("shipment_id", ""), params.get("received_by", ""),
        str(current_user.id)
    )
    return _hub_back(hub, result)
# end def


@login_required
def html_antar_fail(code):
    if not csrf.validate():
        hub = (request.form.get("hub") or "").strip()
        return redirect(url_for("manifests_blueprint.hub", hub=hub, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    hub = (params.get("hub") or "").strip()
    result = manifests_proc().fail_delivery(
        code, params.get("shipment_id", ""), params.get("reason", ""),
        str(current_user.id)
    )
    return _hub_back(hub, result)
# end def

def _fleet_choices():
    fproc = fleet_proc()
    vehicles = []
    for rec in fproc.list_vehicles():
        vehicles.append({"id": rec["id"], "label": fproc.vehicle_label(rec)})
    # end for
    drivers = []
    for rec in fproc.list_drivers():
        drivers.append({
            "id": rec["id"],
            "label": rec.get("contact_name", "") + " — SIM " + rec.get("license_number", "")
        })
    # end for
    return vehicles, drivers
# end def

@login_required
def html_routes():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["routes"] = manifests_proc().list_routes()
    return render_template("routes.html", data=data)
# end def

def _route_form_data(route):
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    proc = manifests_proc()
    hubs = proc.list_hubs()
    data["hubs"] = hubs
    vehicles, drivers = _fleet_choices()
    data["vehicles"] = vehicles
    data["drivers"] = drivers
    data["route"] = route
    stops = []
    if route != None:
        by_id = {}
        for hub in hubs:
            by_id[hub["id"]] = hub
        # end for
        ids = route.get("hub_ids") or []
        if not isinstance(ids, list) or len(ids) == 0:
            ids = [route.get("origin_hub_id", ""), route.get("destination_hub_id", "")]
        # end if
        for hub_id in ids:
            hub = by_id.get(hub_id, None)
            if hub == None:
                continue
            # end if
            stops.append({
                "id": hub["id"],
                "name": hub.get("name", ""),
                "place": hub.get("regency", "")
            })
        # end for
    # end if
    data["initial_stops"] = stops
    return data
# end def

@login_required
def html_new_route():
    return render_template("route_form.html", data=_route_form_data(None))
# end def

@login_required
def html_edit_route(route_id):
    route = manifests_proc().get_route(route_id)
    if route == None:
        return redirect(url_for("manifests_blueprint.routes", error="Rute tidak ditemukan"))
    # end if
    return render_template("route_form.html", data=_route_form_data(route))
# end def

@login_required
def html_create_route():
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.route_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    params["hub_ids"] = request.form.getlist("hub_ids")
    result = manifests_proc().create_route(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.route_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.routes", success=result.get("desc", "")))
# end def

@login_required
def html_update_route(route_id):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.route_edit", route_id=route_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    params["hub_ids"] = request.form.getlist("hub_ids")
    result = manifests_proc().update_route(route_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.route_edit", route_id=route_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.routes", success=result.get("desc", "")))
# end def

@login_required
def html_delete_route(route_id):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.routes", error="Sesi tidak valid, coba lagi"))
    # end if
    result = manifests_proc().delete_route(route_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.routes", error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.routes", success=result.get("desc", "")))
# end def

@login_required
def html_new_hub():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["hub"] = None
    return render_template("hub_form.html", data=data)
# end def

@login_required
def html_edit_hub(hub_id):
    hub = manifests_proc().get_hub(hub_id)
    if hub == None:
        return redirect(url_for("manifests_blueprint.hub", error="Hub tidak ditemukan"))
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["hub"] = hub
    return render_template("hub_form.html", data=data)
# end def

@login_required
def html_update_hub(hub_id):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.hub_edit", hub_id=hub_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = manifests_proc().update_hub(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.hub_edit", hub_id=hub_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.hub", hub=result.get("name", ""), success=result.get("desc", "")))
# end def

@login_required
def html_create_hub():
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.hub_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = manifests_proc()
    result = proc.create_hub(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.hub_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.hub", hub=result.get("name", ""), success=result.get("desc", "")))
# end def

@login_required
def html_delete_hub(hub_id):
    if not csrf.validate():
        return redirect(url_for("manifests_blueprint.hub", error="Sesi tidak valid, coba lagi"))
    # end if
    result = manifests_proc().delete_hub(hub_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("manifests_blueprint.hub", error=result.get("desc", "")))
    # end if
    return redirect(url_for("manifests_blueprint.hub", success=result.get("desc", "")))
# end def

@login_required
def api_wilayah(kind):
    result = manifests_proc().wilayah(kind, request.args.to_dict())
    code = 200
    if result.get("status") != "SUCCESS":
        code = 400
    # end if
    return jsonify(result), code
# end def
