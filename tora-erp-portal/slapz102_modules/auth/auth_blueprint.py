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

# ---------------------------------------------------------------------------
# AUTH MODULE — route layer (login / logout / dashboard / user management).
# ---------------------------------------------------------------------------

auth_blueprint = Blueprint("auth_blueprint", __name__)

@auth_blueprint.route("/", methods=["GET"])
def dashboard():
    try:
        return view_auth.html_dashboard()
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

@auth_blueprint.route("/users", methods=["GET"])
def users():
    try:
        return view_auth.html_users()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/users/new", methods=["GET"])
def users_new():
    try:
        return view_auth.html_new_user()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/users/<user_id>/edit", methods=["GET"])
def users_edit(user_id):
    try:
        return view_auth.html_edit_user(user_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/users/<user_id>/update", methods=["POST"])
def users_update(user_id):
    try:
        return view_auth.html_update_user(user_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/users/<user_id>/delete", methods=["POST"])
def users_delete(user_id):
    try:
        return view_auth.html_delete_user(user_id)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/users/create", methods=["POST"])
def users_create():
    try:
        return view_auth.html_create_user()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@auth_blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    # Same handler as the sample module, kept at the root because the sample
    # blueprint now lives under /sample.
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
