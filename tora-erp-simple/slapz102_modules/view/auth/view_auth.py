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

from auth.auth_proc import auth_proc
from orders.orders_proc import orders_proc


def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": {"orders_active": orders_proc().active_count()}
    }
# end def


def html_home():
    if current_user.is_authenticated:
        return redirect(url_for("orders_blueprint.index"))
    # end if
    return redirect(url_for("auth_blueprint.login"))
# end def


def html_login():
    if request.method == "GET":
        if current_user.is_authenticated:
            return redirect(url_for("orders_blueprint.index"))
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
        next_url = url_for("orders_blueprint.index")
    # end if
    return redirect(next_url)
# end def


@login_required
def html_logout():
    if not csrf.validate():
        return redirect(url_for("orders_blueprint.index"))
    # end if
    logout_user()
    return redirect(url_for("auth_blueprint.login"))
# end def
