import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for
from flask_login import login_user, logout_user, login_required, current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from auth.auth_proc import auth_proc, superadmin_required
from shipments.shipments_proc import shipments_proc
from contacts.contacts_proc import contacts_proc

# ---------------------------------------------------------------------------
# AUTH MODULE — view / render layer.
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": shipments_proc().sidebar_counts()
    }
# end def

def html_login():
    if request.method == "GET":
        if current_user.is_authenticated:
            return redirect(url_for("auth_blueprint.dashboard"))
        # end if
        proc = auth_proc()
        bootstrapped = proc.ensure_default_superadmin()
        data = _base_data()
        data["form_error"] = (request.args.get("error") or "").strip()
        data["bootstrapped"] = bootstrapped
        data["default_username"] = config.G_SUPERADMIN_USERNAME if bootstrapped else ""
        return render_template("login.html", data=data)
    # end if
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.login", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = auth_proc()
    user = proc.authenticate(
        (params.get("username") or "").strip(), params.get("password") or ""
    )
    if user == None:
        return redirect(url_for("auth_blueprint.login", error="Nama pengguna atau kata sandi salah"))
    # end if
    login_user(user)
    next_url = (params.get("next") or "").strip()
    if next_url == "" or not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("auth_blueprint.dashboard")
    # end if
    return redirect(next_url)
# end def

@login_required
def html_logout():
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.dashboard"))
    # end if
    logout_user()
    return redirect(url_for("auth_blueprint.login"))
# end def

@login_required
def html_dashboard():
    proc = shipments_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["stats"] = proc.dashboard_stats()
    data["status_counts"] = proc.status_counts()
    recent = proc.recent_shipments(6)
    cproc = contacts_proc()
    contacts_map = cproc.get_contacts_map([
        rec.get("sender_id", "") for rec in recent
    ])
    for rec in recent:
        sender = contacts_map.get(rec.get("sender_id", ""), None)
        rec["sender_name"] = sender.get("name", "") if sender != None else ""
    # end for
    data["recent"] = recent
    return render_template("dashboard.html", data=data)
# end def

@superadmin_required
def html_users():
    proc = auth_proc()
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["users"] = proc.list_users()
    return render_template("users.html", data=data)
# end def

@superadmin_required
def html_new_user():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["user_rec"] = None
    return render_template("user_form.html", data=data)
# end def

@superadmin_required
def html_edit_user(user_id):
    user_rec = auth_proc().get_user(user_id)
    if user_rec == None:
        return redirect(url_for("auth_blueprint.users", error="Pengguna tidak ditemukan"))
    # end if
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["user_rec"] = user_rec
    return render_template("user_form.html", data=data)
# end def

@superadmin_required
def html_update_user(user_id):
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users_edit", user_id=user_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = auth_proc().update_user(user_id, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users_edit", user_id=user_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users", success=result.get("desc", "")))
# end def

@superadmin_required
def html_delete_user(user_id):
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users", error="Sesi tidak valid, coba lagi"))
    # end if
    result = auth_proc().delete_user(user_id, str(current_user.id))
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users", error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users", success=result.get("desc", "")))
# end def

@superadmin_required
def html_create_user():
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = auth_proc()
    result = proc.create_user(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users", success=result.get("desc", "")))
# end def
