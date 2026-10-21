import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.contacts import view_contacts

# ---------------------------------------------------------------------------
# CONTACTS MODULE — route layer.
#
# /contacts            master list
# /contacts/new        new-contact page
# /contacts/create     form POST (order entry may send "next")
# /api/contacts        autocomplete JSON and quick create
# ---------------------------------------------------------------------------

contacts_blueprint = Blueprint("contacts_blueprint", __name__)

@contacts_blueprint.route("/contacts", methods=["GET"])
def index():
    try:
        return view_contacts.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/contacts/new", methods=["GET"])
def new_contact():
    try:
        return view_contacts.html_new()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/contacts/<contact_id>/edit", methods=["GET"])
def edit_contact(contact_id):
    try:
        return view_contacts.html_edit(contact_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/contacts/<contact_id>/update", methods=["POST"])
def update_contact(contact_id):
    try:
        return view_contacts.html_update(contact_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/contacts/<contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    try:
        return view_contacts.html_delete(contact_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/contacts/create", methods=["POST"])
def create():
    try:
        return view_contacts.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@contacts_blueprint.route("/api/contacts", methods=["GET"])
def api_search():
    try:
        return view_contacts.api_search()
    except Exception as e:
        print(traceback.format_exc())
        return {"results": [], "error": "Terjadi kesalahan"}, 500
    # end try
# end def

@contacts_blueprint.route("/api/contacts", methods=["POST"])
def api_create():
    try:
        return view_contacts.api_create()
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def
