import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.record_log import view_record_log

# ---------------------------------------------------------------------------
# RECORD LOG MODULE — route layer.
#
# /log/<model>/<record_id>/note   POST "Log catatan" (fetch -> JSON, or form
#                                 post -> redirect back to "next")
# ---------------------------------------------------------------------------

record_log_blueprint = Blueprint("record_log_blueprint", __name__)

@record_log_blueprint.route("/log/<model>/<record_id>/note", methods=["POST"])
def add_note(model, record_id):
    try:
        return view_record_log.html_add_note(model, record_id)
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def
