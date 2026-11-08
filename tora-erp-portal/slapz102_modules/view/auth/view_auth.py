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
from slapz102_stdlib import paginate

from auth.auth_proc import auth_proc, access_required, access_level
from auth.auth_proc import ROLE_ADMIN, ROLE_SUPERADMIN, VALID_ROLES, ROLE_LABELS, STATUS_LABELS
from auth.auth_proc import ACCESS_LEVELS, ACCESS_SECTIONS
from shipments.shipments_proc import shipments_proc
from contacts.contacts_proc import contacts_proc
from record_log.record_log_proc import record_log_proc

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
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    return render_template("dashboard.html", data=data)
# end def

@login_required
def html_operations():
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
    return render_template("operations.html", data=data)
# end def

# ---------------------------------------------------------------------------
# Pengaturan > Pengguna
# ---------------------------------------------------------------------------

def _actor():
    return current_user._get_current_object()
# end def

@access_required("users", "read")
def html_users():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["role"] = (params.get("role") or "").strip()
    if data["role"] not in VALID_ROLES:
        data["role"] = ""
    # end if
    data["status"] = (params.get("status") or "").strip().upper()
    if data["status"] not in STATUS_LABELS:
        data["status"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["roles"] = VALID_ROLES
    data["role_labels"] = ROLE_LABELS
    data["status_labels"] = STATUS_LABELS
    page, per_page = paginate.read_params(params)
    pager = auth_proc().page_users(data["role"], data["status"], data["q"], page, per_page)
    data["users"] = pager["users"]
    data["pager"] = pager
    data["page_args"] = {"role": data["role"], "status": data["status"], "q": data["q"]}
    return render_template("users.html", data=data)
# end def

def _user_form_data(user_rec, params):
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (params.get("error") or "").strip()
    data["form_success"] = (params.get("success") or "").strip()
    data["user_rec"] = user_rec
    data["access_sections"] = ACCESS_SECTIONS
    data["access_levels"] = ACCESS_LEVELS
    data["role_labels"] = ROLE_LABELS
    perms = {}
    if user_rec != None:
        perms = user_rec.get("permissions") or {}
    # end if
    levels = {}
    for section in ACCESS_SECTIONS:
        for area in section["areas"]:
            levels[area["key"]] = access_level(ROLE_ADMIN, perms, area["key"])
        # end for
    # end for
    data["user_levels"] = levels
    data["log_groups"] = []
    return data
# end def

@access_required("users", "create")
def html_new_user():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _user_form_data(None, params)
    return render_template("user_form.html", data=data)
# end def

@access_required("users", "read")
def html_edit_user(user_id):
    user_rec = auth_proc().get_user_form(user_id)
    if user_rec == None:
        return redirect(url_for("auth_blueprint.users", error="Pengguna tidak ditemukan"))
    # end if
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _user_form_data(user_rec, params)
    data["log_groups"] = record_log_proc().list_groups("user", user_rec["id"])
    return render_template("user_form.html", data=data)
# end def

@access_required("users", "update")
def html_update_user(user_id):
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users_edit", user_id=user_id, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = auth_proc().update_user(user_id, params, _actor())
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users_edit", user_id=user_id, error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users_edit", user_id=user_id, success=result.get("desc", "")))
# end def

@access_required("users", "delete")
def html_delete_user(user_id):
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users", error="Sesi tidak valid, coba lagi"))
    # end if
    result = auth_proc().delete_users([user_id], str(current_user.id), current_user.role == ROLE_SUPERADMIN)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users", error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users", success=result.get("desc", "")))
# end def

@access_required("users", "delete")
def html_bulk_delete_users():
    params = sanitize.clean_html_dic(request.form.to_dict())
    back = {"role": params.get("role", ""), "status": params.get("status", ""), "q": params.get("q", "")}
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users", error="Sesi tidak valid, coba lagi", **back))
    # end if
    ids = []
    for value in request.form.getlist("ids"):
        ids.append(sanitize.clean_html(value))
    # end for
    result = auth_proc().delete_users(ids, str(current_user.id), current_user.role == ROLE_SUPERADMIN)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users", error=result.get("desc", ""), **back))
    # end if
    return redirect(url_for("auth_blueprint.users", success=result.get("desc", ""), **back))
# end def

@access_required("users", "create")
def html_create_user():
    if not csrf.validate():
        return redirect(url_for("auth_blueprint.users_new", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = auth_proc().create_user(params, _actor())
    if result.get("status") != "SUCCESS":
        return redirect(url_for("auth_blueprint.users_new", error=result.get("desc", "")))
    # end if
    return redirect(url_for("auth_blueprint.users_edit", user_id=result.get("id", ""), success=result.get("desc", "")))
# end def
