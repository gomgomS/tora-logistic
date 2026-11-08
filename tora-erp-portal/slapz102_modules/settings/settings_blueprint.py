import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.settings import view_settings

# ---------------------------------------------------------------------------
# SETTINGS MODULE — route layer.
#
# /settings     Pengaturan Umum (sections linking to Kelola Pengguna, ...)
# User management itself lives in the auth module (/users ...).
# ---------------------------------------------------------------------------

settings_blueprint = Blueprint("settings_blueprint", __name__)

@settings_blueprint.route("/settings", methods=["GET"])
def index():
    try:
        return view_settings.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def
