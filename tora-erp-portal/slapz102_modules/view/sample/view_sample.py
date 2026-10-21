import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from sample.sample_proc import sample_proc

# ---------------------------------------------------------------------------
# SAMPLE MODULE — view / render layer.
#
# A view function reads the request, sanitizes input, calls proc methods and
# renders a template. Views hold no business logic beyond glue like this.
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/"
    }
# end def

def html_index():
    proc = sample_proc()
    data = _base_data()
    data["sample_items"] = proc.list_items()
    data["form_error"] = (request.args.get("error") or "").strip()
    return render_template("index.html", data=data)
# end def

def html_item(slug):
    proc = sample_proc()
    item = proc.get_item(slug)
    if item == None:
        return "Not found", 404
    # end if
    data = _base_data()
    data["item"] = item
    return render_template("sample_item.html", data=data)
# end def

def html_create():
    if not csrf.validate():
        return redirect(url_for("sample_blueprint.index", error="Invalid session, please try again"))
    # end if
    # Every POST/GET input goes through sanitize before it reaches a proc
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = sample_proc()
    result = proc.create_item(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("sample_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("sample_blueprint.index"))
# end def

def html_delete(slug):
    if not csrf.validate():
        return redirect(url_for("sample_blueprint.index", error="Invalid session, please try again"))
    # end if
    proc = sample_proc()
    proc.delete_item(slug)
    return redirect(url_for("sample_blueprint.index"))
# end def
