import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.manifests import view_manifests

# ---------------------------------------------------------------------------
# MANIFESTS MODULE — route layer (Consolidated Manifest System + Hub).
#
# /manifests                     manifest list
# /manifests/create              build a manifest (vehicle + driver + N shipments)
# /manifests/detail/<code>       detail + bulk status update form
# /manifests/<code>/update       POST bulk tracking update (update_many + $push)
# /hub                           transit-hub sorting, feeder, and door delivery
# ---------------------------------------------------------------------------

manifests_blueprint = Blueprint("manifests_blueprint", __name__)

@manifests_blueprint.route("/manifests", methods=["GET"])
def index():
    try:
        return view_manifests.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/create", methods=["GET", "POST"])
def create():
    try:
        return view_manifests.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/detail/<manifest_code>", methods=["GET"])
def detail(manifest_code):
    try:
        return view_manifests.html_detail(manifest_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/<manifest_code>/fleet", methods=["POST"])
def manifest_fleet(manifest_code):
    try:
        return view_manifests.html_update_fleet(manifest_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/<manifest_code>/delete", methods=["POST"])
def manifest_delete(manifest_code):
    try:
        return view_manifests.html_delete_manifest(manifest_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/<manifest_code>/advance", methods=["POST"])
def advance(manifest_code):
    try:
        return view_manifests.html_advance(manifest_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/manifests/<manifest_code>/update", methods=["POST"])
def update(manifest_code):
    try:
        return view_manifests.html_update(manifest_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/new", methods=["GET"])
def hub_new():
    try:
        return view_manifests.html_new_hub()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/api/wilayah/<kind>", methods=["GET"])
def wilayah(kind):
    try:
        return view_manifests.api_wilayah(kind)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/create", methods=["POST"])
def hub_create():
    try:
        return view_manifests.html_create_hub()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/<hub_id>/edit", methods=["GET"])
def hub_edit(hub_id):
    try:
        return view_manifests.html_edit_hub(hub_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/<hub_id>/update", methods=["POST"])
def hub_update(hub_id):
    try:
        return view_manifests.html_update_hub(hub_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/<hub_id>/delete", methods=["POST"])
def hub_delete(hub_id):
    try:
        return view_manifests.html_delete_hub(hub_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes", methods=["GET"])
def routes():
    try:
        return view_manifests.html_routes()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes/new", methods=["GET"])
def route_new():
    try:
        return view_manifests.html_new_route()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes/create", methods=["POST"])
def route_create():
    try:
        return view_manifests.html_create_route()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes/<route_id>/edit", methods=["GET"])
def route_edit(route_id):
    try:
        return view_manifests.html_edit_route(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes/<route_id>/update", methods=["POST"])
def route_update(route_id):
    try:
        return view_manifests.html_update_route(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/routes/<route_id>/delete", methods=["POST"])
def route_delete(route_id):
    try:
        return view_manifests.html_delete_route(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/antar", methods=["POST"])
def hub_antar():
    try:
        return view_manifests.html_start_antar()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/antar/<code>/deliver", methods=["POST"])
def hub_antar_deliver(code):
    try:
        return view_manifests.html_antar_deliver(code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/antar/<code>/fail", methods=["POST"])
def hub_antar_fail(code):
    try:
        return view_manifests.html_antar_fail(code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub/<hub_id>", methods=["GET"])
def hub_desk(hub_id):
    try:
        return view_manifests.html_hub_desk(hub_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@manifests_blueprint.route("/hub", methods=["GET"])
def hub():
    try:
        return view_manifests.html_hub()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
