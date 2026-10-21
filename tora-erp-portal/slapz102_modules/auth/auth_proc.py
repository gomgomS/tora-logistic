import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import functools

from flask import redirect, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# AUTH MODULE — business logic layer.
#
# Session auth is handled by Flask-Login; this proc supplies:
#   - the erp_user wrapper Flask-Login serializes into the session
#   - credential verification against db_user (werkzeug password hashes)
#   - one-time bootstrap of the default superadmin
#   - user administration (list / create) for the RBAC roles below
#
# Roles: "superadmin" (full access incl. user management),
#        "admin" (operational access).
# ---------------------------------------------------------------------------

ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
VALID_ROLES = [ROLE_SUPERADMIN, ROLE_ADMIN]


class erp_user(UserMixin):

    def __init__(self, doc):
        self.user_doc = doc
        self.id = str(doc["_id"])
        self.username = doc.get("username", "")
        self.role = doc.get("role", "")
    # end def
# end class


def superadmin_required(view_func):
    # Route guard for views only superadmin may open (e.g. user management).
    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth_blueprint.login"))
        # end if
        if current_user.role != ROLE_SUPERADMIN:
            return redirect(url_for("auth_blueprint.dashboard", error="Akses superadmin diperlukan"))
        # end if
        return view_func(*args, **kwargs)
    # end def
    return wrapper
# end def


class auth_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def get_login_user(self, user_id):
        # Flask-Login user_loader: session id -> erp_user (or None).
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_user.find_one(
            {"_id": oid, "is_deleted": False, "status": "ENABLE"}
        )
        if doc == None:
            return None
        # end if
        return erp_user(doc)
    # end def

    def authenticate(self, username, password):
        doc = self.mgdDB.db_user.find_one(
            {"username": username, "is_deleted": False, "status": "ENABLE"}
        )
        if doc == None:
            return None
        # end if
        if not check_password_hash(doc.get("password", ""), password):
            return None
        # end if
        return erp_user(doc)
    # end def

    def ensure_default_superadmin(self):
        # One-time bootstrap so a fresh deployment can be logged into.
        # Returns True when the default account was just created.
        count = self.mgdDB.db_user.count_documents({"is_deleted": False})
        if count > 0:
            return False
        # end if
        rec = database.new(self.mgdDB, "db_user")
        rec.put("fk_user_id", "")
        rec.put("username", config.G_SUPERADMIN_USERNAME)
        rec.put("password", generate_password_hash(config.G_SUPERADMIN_PASSWORD))
        rec.put("role", ROLE_SUPERADMIN)
        rec.put("name", "Default Superadmin")
        rec.put("phone", "")
        rec.put("email", "")
        rec.put("status", "ENABLE")
        rec.insert()
        return True
    # end def

    def _user_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def list_users(self):
        recs = list(self.mgdDB.db_user.find(
            {"is_deleted": False}
        ).sort("username", 1))
        out = []
        for rec in recs:
            out.append(self._user_public(rec))
        # end for
        return out
    # end def

    def create_user(self, params):
        username = (params.get("username") or "").strip()
        password = params.get("password") or ""
        role = (params.get("role") or "").strip()
        if username == "" or len(username) < 3:
            return {"status": "ERROR", "desc": "Nama pengguna wajib diisi (minimal 3 karakter)"}
        # end if
        if len(password) < 8:
            return {"status": "ERROR", "desc": "Kata sandi minimal 8 karakter"}
        # end if
        if role not in VALID_ROLES:
            return {"status": "ERROR", "desc": "Peran harus Superadmin atau Admin"}
        # end if
        existing = self.mgdDB.db_user.find_one(
            {"username": username, "is_deleted": False}
        )
        if existing != None:
            return {"status": "ERROR", "desc": "Nama pengguna sudah ada"}
        # end if
        rec = database.new(self.mgdDB, "db_user")
        rec.put("fk_user_id", "")
        rec.put("username", username)
        rec.put("password", generate_password_hash(password))
        rec.put("role", role)
        rec.put("name", (params.get("name") or "").strip())
        rec.put("phone", (params.get("phone") or "").strip())
        rec.put("email", (params.get("email") or "").strip())
        rec.put("status", "ENABLE")
        rec.insert()
        return {"status": "SUCCESS", "desc": "Pengguna dibuat"}
    # end def

    def get_user(self, user_id):
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_user.find_one({"_id": oid, "is_deleted": False})
        if doc == None:
            return None
        # end if
        return self._user_public(doc)
    # end def

    def update_user(self, user_id, params):
        current = self.get_user(user_id)
        if current == None:
            return {"status": "ERROR", "desc": "Pengguna tidak ditemukan"}
        # end if
        username = (params.get("username") or "").strip()
        password = params.get("password") or ""
        role = (params.get("role") or "").strip()
        status = (params.get("status") or "ENABLE").strip().upper()
        if username == "" or len(username) < 3:
            return {"status": "ERROR", "desc": "Nama pengguna wajib diisi (minimal 3 karakter)"}
        # end if
        if password != "" and len(password) < 8:
            return {"status": "ERROR", "desc": "Kata sandi minimal 8 karakter"}
        # end if
        if role not in VALID_ROLES:
            return {"status": "ERROR", "desc": "Peran harus Superadmin atau Admin"}
        # end if
        if status not in ["ENABLE", "DISABLE"]:
            return {"status": "ERROR", "desc": "Status tidak valid"}
        # end if
        existing = self.mgdDB.db_user.find_one(
            {"username": username, "is_deleted": False}
        )
        if existing != None and str(existing.get("_id", "")) != current["id"]:
            return {"status": "ERROR", "desc": "Nama pengguna sudah ada"}
        # end if
        if current.get("role") == ROLE_SUPERADMIN and role != ROLE_SUPERADMIN:
            left = self.mgdDB.db_user.count_documents({
                "is_deleted": False, "role": ROLE_SUPERADMIN
            })
            if left <= 1:
                return {"status": "ERROR", "desc": "Superadmin terakhir tidak bisa diubah perannya"}
            # end if
        # end if
        fields = {
            "username": username,
            "role": role,
            "name": (params.get("name") or "").strip(),
            "status": status
        }
        if password != "":
            fields["password"] = generate_password_hash(password)
        # end if
        self.mgdDB.db_user.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": fields}
        )
        return {"status": "SUCCESS", "desc": "Pengguna diperbarui"}
    # end def

    def delete_user(self, user_id, actor_id):
        if (user_id or "") == (actor_id or ""):
            return {"status": "ERROR", "desc": "Tidak bisa menghapus akun yang sedang dipakai"}
        # end if
        current = self.get_user(user_id)
        if current == None:
            return {"status": "ERROR", "desc": "Pengguna tidak ditemukan"}
        # end if
        if current.get("role") == ROLE_SUPERADMIN:
            left = self.mgdDB.db_user.count_documents({
                "is_deleted": False, "role": ROLE_SUPERADMIN
            })
            if left <= 1:
                return {"status": "ERROR", "desc": "Superadmin terakhir tidak bisa dihapus"}
            # end if
        # end if
        self.mgdDB.db_user.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Pengguna dihapus"}
    # end def

    def get_users_map(self, user_ids):
        # {str(_id): username} for rendering "updated_by" in tracking logs.
        oids = []
        for uid in user_ids:
            if uid == "" or uid == None:
                continue
            # end if
            try:
                oids.append(ObjectId(uid))
            except Exception:
                pass
            # end try
        # end for
        out = {}
        if len(oids) == 0:
            return out
        # end if
        recs = self.mgdDB.db_user.find({"_id": {"$in": oids}}, {"username": 1})
        for rec in recs:
            out[str(rec["_id"])] = rec.get("username", "")
        # end for
        return out
    # end def
# end class
