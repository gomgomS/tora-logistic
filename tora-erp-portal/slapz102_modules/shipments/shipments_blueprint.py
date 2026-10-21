import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.shipments import view_shipments

# ---------------------------------------------------------------------------
# SHIPMENTS MODULE — route layer (Order Entry, LTL + FTL).
#
# /shipments                order list with filters
# /shipments/create         order entry form (auto AWB, optional PO number)
# /shipments/detail/<code>  detail + tracking timeline + manual milestone
# /shipments/<code>/log     POST manual tracking-log update
# ---------------------------------------------------------------------------

shipments_blueprint = Blueprint("shipments_blueprint", __name__)

@shipments_blueprint.route("/shipments", methods=["GET"])
def index():
    try:
        return view_shipments.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/create", methods=["GET", "POST"])
def create():
    try:
        return view_shipments.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/<tracking_code>/edit", methods=["GET"])
def edit(tracking_code):
    try:
        return view_shipments.html_edit(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/<tracking_code>/update", methods=["POST"])
def update(tracking_code):
    try:
        return view_shipments.html_update(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/<tracking_code>/delete", methods=["POST"])
def delete(tracking_code):
    try:
        return view_shipments.html_delete(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/detail/<tracking_code>", methods=["GET"])
def detail(tracking_code):
    try:
        return view_shipments.html_detail(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@shipments_blueprint.route("/shipments/<tracking_code>/log", methods=["POST"])
def add_log(tracking_code):
    try:
        return view_shipments.html_add_log(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
