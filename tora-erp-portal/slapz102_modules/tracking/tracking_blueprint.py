import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.tracking import view_tracking

# ---------------------------------------------------------------------------
# TRACKING MODULE — route layer (public, no login).
#
# /track      public tracking page with the milestone timeline (ID/EN)
# /api/track  JSON: {status, data: {shipment, tracking_logs}} searched by
#             tracking_code OR po_number
# ---------------------------------------------------------------------------

tracking_blueprint = Blueprint("tracking_blueprint", __name__)

@tracking_blueprint.route("/track", methods=["GET"])
def track_page():
    try:
        return view_tracking.html_track()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@tracking_blueprint.route("/api/track", methods=["GET"])
def api_track():
    try:
        return view_tracking.api_track()
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "An error occurred", "data": None}, 500
    # end try
# end def
