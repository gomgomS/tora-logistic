import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.ai import view_ai

# ---------------------------------------------------------------------------
# AI ASSISTANT — route layer.
#
# /api/ai/chat    propose a reply and optional records
# /api/ai/apply   write the records the user confirmed
# ---------------------------------------------------------------------------

ai_blueprint = Blueprint("ai_blueprint", __name__)

@ai_blueprint.route("/api/ai/chat", methods=["POST"])
def chat():
    try:
        return view_ai.api_chat()
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def

@ai_blueprint.route("/api/ai/apply", methods=["POST"])
def apply():
    try:
        return view_ai.api_apply()
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def
