import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, jsonify
from flask_login import login_required, current_user
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from record_log.record_log_proc import record_log_proc

# ---------------------------------------------------------------------------
# RECORD LOG MODULE — view / render layer.
# ---------------------------------------------------------------------------

def actor_from_user(user):
    # Shared by every module that writes log entries from a request.
    return {"id": str(user.id), "name": user.username}
# end def

def _wants_json():
    return request.headers.get("X-Requested-With", "") == "fetch"
# end def

def _safe_next(next_url):
    next_url = (next_url or "").strip()
    if next_url == "" or not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    # end if
    return next_url
# end def

@login_required
def html_add_note(model, record_id):
    params = sanitize.clean_html_dic(request.form.to_dict())
    next_url = _safe_next(params.get("next"))
    joiner = "&" if "?" in next_url else "?"
    if not csrf.validate():
        if _wants_json():
            return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
        # end if
        return redirect(next_url + joiner + "error=Sesi+tidak+valid,+coba+lagi")
    # end if
    model = sanitize.clean_html(model)
    record_id = sanitize.clean_html(record_id)
    proc = record_log_proc()
    area = proc.model_area(model)
    if area != None and not current_user.can(area, "read"):
        result = {"status": "ERROR", "desc": "Anda tidak punya akses ke data ini"}
    else:
        result = proc.add_note(model, record_id, params.get("body"), actor_from_user(current_user))
    # end if
    if _wants_json():
        if result.get("status") != "SUCCESS":
            return jsonify(result), 400
        # end if
        html = render_template("_record_log_entry.html", entry=result["entry"])
        return jsonify({"status": "SUCCESS", "desc": result["desc"], "html": html})
    # end if
    if result.get("status") != "SUCCESS":
        return redirect(next_url + joiner + "error=" + result.get("desc", "").replace(" ", "+"))
    # end if
    return redirect(next_url)
# end def
