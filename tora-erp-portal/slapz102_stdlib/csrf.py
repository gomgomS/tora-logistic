import secrets

from flask import request, session

# ---------------------------------------------------------------------------
# CSRF protection for form POSTs.
#
# Every POST form must include the token:
#     <input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
#
# Every view function that handles a POST must validate it first:
#     if not csrf.validate():
#         return redirect(url_for("sample_blueprint.index", error="Invalid session, try again"))
#     # end if
# ---------------------------------------------------------------------------

def get_token():
    token = session.get("csrf_token", "")
    if token == "":
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    # end if
    return token
# end def

def validate():
    sent = (request.form.get("csrf_token") or "").strip()
    good = session.get("csrf_token", "")
    if sent == "" or good == "":
        return False
    # end if
    return secrets.compare_digest(sent, good)
# end def

# Same comparison for transports that cannot put the token in request.form
# (JSON bodies, custom headers): the caller extracts the token itself.
def validate_token(sent):
    sent = (sent or "").strip()
    good = session.get("csrf_token", "")
    if sent == "" or good == "":
        return False
    # end if
    return secrets.compare_digest(sent, good)
# end def
