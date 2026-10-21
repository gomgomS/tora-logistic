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

from routes.routes_proc import routes_proc
from orders.orders_proc import orders_proc


def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": {"orders_active": orders_proc().active_count()},
        "current_user": current_user
    }
# end def


def _hub_names_from_form():
    names = []
    for raw in request.form.getlist("hub_names"):
        names.append(sanitize.clean_html(raw))
    # end for
    return names
# end def


@login_required
def html_index():
    proc = routes_proc()
    data = _base_data()
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["routes"] = proc.list_routes()
    return render_template("routes.html", data=data)
# end def


@login_required
def html_form(route_id):
    proc = routes_proc()
    data = _base_data()
    data["form_error"] = (request.args.get("error") or "").strip()
    data["route"] = None
    data["stops"] = ["", ""]
    if route_id != None:
        route = proc.get_route(route_id)
        if route == None:
            return redirect(url_for("routes_blueprint.index", error="Rute tidak ditemukan"))
        # end if
        data["route"] = route
        stops = list(route.get("hub_names") or [])
        if len(stops) < 2:
            stops = ["", ""]
        # end if
        data["stops"] = stops
    # end if
    return render_template("route_form.html", data=data)
# end def


@login_required
def html_create():
    if not csrf.validate():
        return redirect(url_for("routes_blueprint.new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    params["hub_names"] = _hub_names_from_form()
    result = routes_proc().create_route(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("routes_blueprint.new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("routes_blueprint.index", success=result.get("desc", "")))
# end def


@login_required
def html_update(route_id):
    if not csrf.validate():
        return redirect(url_for("routes_blueprint.edit", route_id=route_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    params["hub_names"] = _hub_names_from_form()
    result = routes_proc().update_route(route_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("routes_blueprint.edit", route_id=route_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("routes_blueprint.index", success=result.get("desc", "")))
# end def


@login_required
def html_delete(route_id):
    if not csrf.validate():
        return redirect(url_for("routes_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = routes_proc().delete_route(route_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("routes_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("routes_blueprint.index", success=result.get("desc", "")))
# end def
