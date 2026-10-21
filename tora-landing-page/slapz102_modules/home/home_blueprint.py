import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.home import view_home

# ---------------------------------------------------------------------------
# HOME MODULE — route layer (public landing page).
#
# "/"   marketing landing page (hero, services, coverage, tracking CTA)
# ---------------------------------------------------------------------------

home_blueprint = Blueprint("home_blueprint", __name__)

@home_blueprint.route("/", methods=["GET"])
def index():
    try:
        return view_home.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
