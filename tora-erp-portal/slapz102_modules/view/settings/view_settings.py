import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, request
from flask_login import current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from auth.auth_proc import auth_proc, access_required, ACCESS_SECTIONS
from shipments.shipments_proc import shipments_proc

# ---------------------------------------------------------------------------
# SETTINGS MODULE — view / render layer.
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

@access_required("users", "read")
def html_index():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["active_users"] = auth_proc().count_active_users()
    area_count = 0
    for section in ACCESS_SECTIONS:
        area_count = area_count + len(section["areas"])
    # end for
    data["access_area_count"] = area_count
    return render_template("settings.html", data=data)
# end def
