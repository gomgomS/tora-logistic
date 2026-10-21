import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, request, jsonify
from slapz102_core import config
from slapz102_stdlib import sanitize

from tracking.tracking_proc import tracking_proc

# ---------------------------------------------------------------------------
# TRACKING MODULE — view / render layer (public).
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/track"
    }
# end def

def html_track():
    params = sanitize.clean_html_dic(request.args.to_dict())
    query = (params.get("q") or "").strip()
    result = None
    not_found = False
    if query != "":
        proc = tracking_proc()
        result = proc.track(query)
        not_found = result == None
    # end if
    data = _base_data()
    data["query"] = query
    data["result"] = result
    data["not_found"] = not_found
    return render_template("track.html", data=data)
# end def

def api_track():
    params = sanitize.clean_html_dic(request.args.to_dict())
    query = (params.get("q") or params.get("code") or "").strip()
    if query == "":
        return jsonify({
            "status": "ERROR",
            "desc": "Provide ?q=<tracking_code or po_number>",
            "data": None
        }), 400
    # end if
    proc = tracking_proc()
    result = proc.track(query)
    if result == None:
        return jsonify({
            "status": "NOT_FOUND",
            "desc": "No shipment found for " + query,
            "data": None
        }), 404
    # end if
    shipment = dict(result)
    logs = shipment.pop("tracking_logs", [])
    return jsonify({
        "status": "SUCCESS",
        "desc": "OK",
        "data": {"shipment": shipment, "tracking_logs": logs}
    })
# end def
