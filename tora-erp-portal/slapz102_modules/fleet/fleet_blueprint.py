import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.fleet import view_fleet

# ---------------------------------------------------------------------------
# FLEET MODULE — route layer.
#
# /fleet                 vehicles + drivers master page
# /fleet/vehicle/create  form POST (unique plate enforcement in proc)
# /fleet/driver/create   form POST (driver linked to a DRIVER contact)
# /api/vehicles          Select2 autocomplete JSON
# /api/drivers           Select2 autocomplete JSON
# ---------------------------------------------------------------------------

fleet_blueprint = Blueprint("fleet_blueprint", __name__)

@fleet_blueprint.route("/fleet", methods=["GET"])
def index():
    try:
        return view_fleet.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/vehicle/new", methods=["GET"])
def vehicle_new():
    try:
        return view_fleet.html_new_vehicle()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/driver/new", methods=["GET"])
def driver_new():
    try:
        return view_fleet.html_new_driver()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/vehicle/<vehicle_id>/edit", methods=["GET"])
def vehicle_edit(vehicle_id):
    try:
        return view_fleet.html_edit_vehicle(vehicle_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/vehicle/<vehicle_id>/update", methods=["POST"])
def vehicle_update(vehicle_id):
    try:
        return view_fleet.html_update_vehicle(vehicle_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/vehicle/<vehicle_id>/delete", methods=["POST"])
def vehicle_delete(vehicle_id):
    try:
        return view_fleet.html_delete_vehicle(vehicle_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/driver/<driver_id>/edit", methods=["GET"])
def driver_edit(driver_id):
    try:
        return view_fleet.html_edit_driver(driver_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/driver/<driver_id>/update", methods=["POST"])
def driver_update(driver_id):
    try:
        return view_fleet.html_update_driver(driver_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/driver/<driver_id>/delete", methods=["POST"])
def driver_delete(driver_id):
    try:
        return view_fleet.html_delete_driver(driver_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/vehicle/create", methods=["POST"])
def vehicle_create():
    try:
        return view_fleet.html_create_vehicle()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/fleet/driver/create", methods=["POST"])
def driver_create():
    try:
        return view_fleet.html_create_driver()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@fleet_blueprint.route("/api/vehicles", methods=["GET"])
def api_vehicles():
    try:
        return view_fleet.api_vehicles()
    except Exception as e:
        print(traceback.format_exc())
        return {"results": [], "error": "Terjadi kesalahan"}, 500
    # end try
# end def

@fleet_blueprint.route("/api/drivers", methods=["GET"])
def api_drivers():
    try:
        return view_fleet.api_drivers()
    except Exception as e:
        print(traceback.format_exc())
        return {"results": [], "error": "Terjadi kesalahan"}, 500
    # end try
# end def
