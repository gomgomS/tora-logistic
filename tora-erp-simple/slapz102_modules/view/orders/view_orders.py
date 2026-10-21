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

from orders.orders_proc import orders_proc, ORDER_STATUSES, STOP_EVENT_LIST
from routes.routes_proc import routes_proc


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


@login_required
def html_index():
    proc = orders_proc()
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["filters"] = {
        "q": (params.get("q") or "").strip(),
        "status": (params.get("status") or "").strip().upper()
    }
    data["statuses"] = ORDER_STATUSES
    data["orders"] = proc.list_orders(data["filters"])
    return render_template("orders.html", data=data)
# end def


@login_required
def html_new():
    data = _base_data()
    data["form_error"] = (request.args.get("error") or "").strip()
    data["routes"] = routes_proc().list_routes()
    return render_template("order_form.html", data=data)
# end def


@login_required
def html_create():
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = orders_proc().create_order(params, str(current_user.id))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("orders_blueprint.new", error=result.get("desc", "")))
    # end if
    return redirect(url_for(
        "orders_blueprint.detail",
        tracking_code=result.get("tracking_code", ""),
        success=result.get("desc", "")
    ))
# end def


@login_required
def html_detail(tracking_code):
    proc = orders_proc()
    order = proc.get_by_code(tracking_code)
    if order == None:
        return "Not found", 404
    # end if
    data = _base_data()
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["order"] = order
    data["journey"] = proc.journey(order)
    data["stop_events"] = STOP_EVENT_LIST
    return render_template("order_detail.html", data=data)
# end def


@login_required
def html_advance(tracking_code):
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    step = (params.get("step") or "forward").strip().lower()
    proc = orders_proc()
    if step == "back":
        result = proc.retreat(tracking_code, str(current_user.id))
    else:
        result = proc.advance(tracking_code, str(current_user.id))
    # end if
    key = "success"
    if result.get("status") != "SUCCESS":
        key = "error"
    # end if
    args = {key: result.get("desc", "")}
    return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, **args))
# end def


@login_required
def html_insert_hub(tracking_code):
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = orders_proc().insert_hub(
        tracking_code,
        params.get("after_index"),
        params.get("hub_name"),
        str(current_user.id)
    )
    key = "success"
    if result.get("status") != "SUCCESS":
        key = "error"
    # end if
    args = {key: result.get("desc", "")}
    return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, **args))
# end def


@login_required
def html_stop_event(tracking_code):
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = orders_proc().add_stop_event(
        tracking_code,
        params.get("stop_index"),
        params.get("event_note"),
        str(current_user.id)
    )
    key = "success"
    if result.get("status") != "SUCCESS":
        key = "error"
    # end if
    args = {key: result.get("desc", "")}
    return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, **args))
# end def


@login_required
def html_refresh_riwayat(tracking_code):
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, error="Sesi tidak valid, coba lagi"))
    # end if
    result = orders_proc().refresh_riwayat(tracking_code, str(current_user.id))
    key = "success"
    if result.get("status") != "SUCCESS":
        key = "error"
    # end if
    args = {key: result.get("desc", "")}
    return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, **args))
# end def


@login_required
def html_delete(tracking_code):
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = orders_proc().delete_order(tracking_code)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("orders_blueprint.detail", tracking_code=tracking_code, error=result.get("desc", "")))
    # end if
    return redirect(url_for("orders_blueprint.index", success=result.get("desc", "")))
# end def
