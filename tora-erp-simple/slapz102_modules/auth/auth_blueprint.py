import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import os
from flask import Blueprint, send_from_directory
from slapz102_core import config

from view.auth import view_auth

auth_blueprint = Blueprint("auth_blueprint", __name__)

@auth_blueprint.route("/", methods=["GET"])
def home():
    try:
        return view_auth.html_home()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    try:
        return view_auth.html_login()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/logout", methods=["POST"])
def logout():
    try:
        return view_auth.html_logout()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    try:
        brand_dir = os.path.join(config.G_HOME_PATH, "static", "brand")
        return send_from_directory(
            brand_dir, "favicon.svg", mimetype="image/svg+xml"
        )
    except Exception as e:
        print(traceback.format_exc())
        return "Not found", 404
    # end try
# end def
