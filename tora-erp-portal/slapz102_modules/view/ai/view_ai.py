import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import jsonify, request
from flask_login import login_required, current_user
from slapz102_stdlib import csrf

from ai.ai_proc import ai_proc

# ---------------------------------------------------------------------------
# AI ASSISTANT — view layer. Chat proposes records. Apply writes them.
# ---------------------------------------------------------------------------

def _payload():
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    # end try
    if not isinstance(payload, dict):
        payload = {}
    # end if
    return payload
# end def

def _csrf_ok(payload):
    sent = payload.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    return csrf.validate_token(sent)
# end def

@login_required
def api_chat():
    payload = _payload()
    if not _csrf_ok(payload):
        return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
    # end if
    messages = payload.get("messages") or []
    result = ai_proc().chat(messages)
    code = 200 if result.get("status") == "SUCCESS" else 400
    return jsonify(result), code
# end def

@login_required
def api_apply():
    payload = _payload()
    if not _csrf_ok(payload):
        return jsonify({"status": "ERROR", "desc": "Sesi tidak valid, coba lagi"}), 400
    # end if
    user_id = ""
    try:
        user_id = str(current_user.id)
    except Exception:
        user_id = "SYSTEM"
    # end try
    result = ai_proc().apply(payload.get("actions") or [], user_id)
    code = 200 if result.get("status") == "SUCCESS" else 400
    return jsonify(result), code
# end def
