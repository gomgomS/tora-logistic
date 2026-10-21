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

from view.sample import view_sample

# ---------------------------------------------------------------------------
# SAMPLE MODULE — route layer.
#
# A blueprint does three things only:
#   1. declare the route + method
#   2. delegate to a view_* function
#   3. catch exceptions -> log traceback -> generic 500
# It never touches the database and never renders a template itself.
# ---------------------------------------------------------------------------

sample_blueprint = Blueprint("sample_blueprint", __name__)

@sample_blueprint.route("/", methods=["GET"])
def index():
    try:
        return view_sample.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@sample_blueprint.route("/sample/create", methods=["POST"])
def create():
    try:
        return view_sample.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@sample_blueprint.route("/sample/delete/<slug>", methods=["POST"])
def delete(slug):
    try:
        return view_sample.html_delete(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@sample_blueprint.route("/sample/<slug>", methods=["GET"])
def detail(slug):
    try:
        return view_sample.html_item(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@sample_blueprint.route("/favicon.ico", methods=["GET"])
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
