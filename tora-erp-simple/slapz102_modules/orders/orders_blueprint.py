import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint

from view.orders import view_orders

orders_blueprint = Blueprint("orders_blueprint", __name__)

@orders_blueprint.route("/orders", methods=["GET"])
def index():
    try:
        return view_orders.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/new", methods=["GET"])
def new():
    try:
        return view_orders.html_new()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/create", methods=["POST"])
def create():
    try:
        return view_orders.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/detail/<tracking_code>", methods=["GET"])
def detail(tracking_code):
    try:
        return view_orders.html_detail(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/<tracking_code>/advance", methods=["POST"])
def advance(tracking_code):
    try:
        return view_orders.html_advance(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/<tracking_code>/insert-hub", methods=["POST"])
def insert_hub(tracking_code):
    try:
        return view_orders.html_insert_hub(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/<tracking_code>/stop-event", methods=["POST"])
def stop_event(tracking_code):
    try:
        return view_orders.html_stop_event(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/<tracking_code>/refresh-riwayat", methods=["POST"])
def refresh_riwayat(tracking_code):
    try:
        return view_orders.html_refresh_riwayat(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@orders_blueprint.route("/orders/<tracking_code>/delete", methods=["POST"])
def delete(tracking_code):
    try:
        return view_orders.html_delete(tracking_code)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
