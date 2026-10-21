import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint

from view.routes import view_routes

routes_blueprint = Blueprint("routes_blueprint", __name__)

@routes_blueprint.route("/routes", methods=["GET"])
def index():
    try:
        return view_routes.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@routes_blueprint.route("/routes/new", methods=["GET"])
def new():
    try:
        return view_routes.html_form(None)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@routes_blueprint.route("/routes/create", methods=["POST"])
def create():
    try:
        return view_routes.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@routes_blueprint.route("/routes/<route_id>/edit", methods=["GET"])
def edit(route_id):
    try:
        return view_routes.html_form(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@routes_blueprint.route("/routes/<route_id>/update", methods=["POST"])
def update(route_id):
    try:
        return view_routes.html_update(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@routes_blueprint.route("/routes/<route_id>/delete", methods=["POST"])
def delete(route_id):
    try:
        return view_routes.html_delete(route_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
