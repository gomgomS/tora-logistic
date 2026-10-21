import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template
from slapz102_core import config
from slapz102_stdlib import csrf

# ---------------------------------------------------------------------------
# HOME MODULE — view / render layer (public landing page, no DB access).
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
    data = _base_data()
    return render_template("home.html", data=data)
# end def
