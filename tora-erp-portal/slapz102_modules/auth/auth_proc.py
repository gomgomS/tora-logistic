import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import functools
import re

from flask import redirect, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config
from slapz102_stdlib import paginate

from record_log.record_log_proc import record_log_proc

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
ROLE_LABELS = {ROLE_SUPERADMIN: "Superadmin", ROLE_ADMIN: "Admin"}
STATUS_LABELS = {"ENABLE": "Aktif", "DISABLE": "Nonaktif"}

# ---------------------------------------------------------------------------
# Hak akses. Superadmin can do everything; an "admin" user gets one level
# per area. Each level is a set of actions:
#   read = lihat, create = tambah, update = ubah, delete = hapus
# Add an area here when a module gets access control (Operasional later).
# ---------------------------------------------------------------------------

ACCESS_LEVELS = [
    {"key": "none", "label": "Tidak ada akses", "actions": []},
    {"key": "read", "label": "Hanya lihat", "actions": ["read"]},
    {"key": "create", "label": "Lihat & tambah", "actions": ["read", "create"]},
    {"key": "update", "label": "Lihat, tambah & ubah", "actions": ["read", "create", "update"]},
    {"key": "full", "label": "Akses penuh (lihat, tambah, ubah & hapus)", "actions": ["read", "create", "update", "delete"]}
]
ACCESS_ACTIONS = {}
ACCESS_LEVEL_LABELS = {}
ACCESS_RANK = {}
for _rank, _level in enumerate(ACCESS_LEVELS):
    ACCESS_ACTIONS[_level["key"]] = _level["actions"]
    ACCESS_LEVEL_LABELS[_level["key"]] = _level["label"]
    ACCESS_RANK[_level["key"]] = _rank
# end for

ACCESS_SECTIONS = [
    {"title": "Pengaturan", "areas": [
        {"key": "users", "label": "Pengguna", "default": "none",
         "help": "Kelola akun pengguna dan hak aksesnya"}
    ]},
    {"title": "Kontak", "areas": [
        {"key": "contacts", "label": "Kontak", "default": "full",
         "help": "Data master klien, penerima, sopir, dan vendor"}
    ]},
    {"title": "Akuntansi", "areas": [
        {"key": "accounting", "label": "Akuntansi", "default": "none",
         "help": "Faktur, tagihan, pembayaran, produk, dan entri jurnal"}
    ]}
]
ACCESS_DEFAULTS = {}
ACCESS_AREA_LABELS = {}
for _section in ACCESS_SECTIONS:
    for _area in _section["areas"]:
        ACCESS_DEFAULTS[_area["key"]] = _area["default"]
        ACCESS_AREA_LABELS[_area["key"]] = _area["label"]
    # end for
# end for

ACTION_VERBS = {"read": "melihat", "create": "menambah", "update": "mengubah", "delete": "menghapus"}


def access_level(role, permissions, area):
    if role == ROLE_SUPERADMIN:
        return "full"
    # end if
    level = (permissions or {}).get(area) or ACCESS_DEFAULTS.get(area, "none")
    if level not in ACCESS_ACTIONS:
        level = "none"
    # end if
    return level
# end def


class erp_user(UserMixin):

    def __init__(self, doc):
        self.user_doc = doc
        self.id = str(doc["_id"])
        self.username = doc.get("username", "")
        self.role = doc.get("role", "")
        self.permissions = doc.get("permissions") or {}
    # end def

    def can(self, area, action):
        level = access_level(self.role, self.permissions, area)
        return action in ACCESS_ACTIONS.get(level, [])
    # end def

    def level(self, area):
        return access_level(self.role, self.permissions, area)
    # end def
# end class


def access_required(area, action):
    # Route guard: logged in AND allowed to <action> in <area>.
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth_blueprint.login"))
            # end if
            if not current_user.can(area, action):
                desc = "Anda tidak punya akses untuk " + ACTION_VERBS.get(action, action) + " " + ACCESS_AREA_LABELS.get(area, area)
                return redirect(url_for("auth_blueprint.dashboard", error=desc))
            # end if
            return view_func(*args, **kwargs)
        # end def
        return wrapper
    # end def
    return decorator
# end def


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
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        self.mgdDB.db_user.update_one(
            {"_id": doc["_id"]},
            {"$set": {"last_login": now.strftime("%Y-%m-%d %H:%M")}}
        )
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

    def list_user_options(self):
        # Dropdown source (Penjual on the contact form): no password hashes.
        recs = self.mgdDB.db_user.find(
            {"is_deleted": False},
            {"username": 1, "name": 1}
        ).sort("username", 1).limit(500)
        out = []
        for rec in recs:
            out.append({
                "id": str(rec["_id"]),
                "label": rec.get("name") or rec.get("username", "")
            })
        # end for
        return out
    # end def

    # ------------------------------------------------------------------
    # User management (Pengaturan > Pengguna)
    # ------------------------------------------------------------------

    def _list_query(self, role, status, q):
        query = {"is_deleted": False}
        role = (role or "").strip()
        if role in VALID_ROLES:
            query["role"] = role
        # end if
        status = (status or "").strip().upper()
        if status in STATUS_LABELS:
            query["status"] = status
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"username": {"$regex": pattern, "$options": "i"}},
                {"name": {"$regex": pattern, "$options": "i"}},
                {"email": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def page_users(self, role, status, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        query = self._list_query(role, status, q)
        projection = {
            "username": 1, "name": 1, "email": 1, "phone": 1, "role": 1,
            "status": 1, "last_login": 1, "rec_timestamp_str": 1
        }
        total = self.mgdDB.db_user.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_user.find(query, projection).sort(
            [("username", 1), ("_id", 1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._user_public(rec))
        # end for
        pager["users"] = out
        return pager
    # end def

    def count_active_users(self):
        return self.mgdDB.db_user.count_documents({"is_deleted": False, "status": "ENABLE"})
    # end def

    def get_user_form(self, user_id):
        # get_user without the password hash, for the form page.
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_user.find_one({"_id": oid, "is_deleted": False}, {"password": 0})
        if doc == None:
            return None
        # end if
        return self._user_public(doc)
    # end def

    def _superadmin_count(self):
        return self.mgdDB.db_user.count_documents({"is_deleted": False, "role": ROLE_SUPERADMIN})
    # end def

    def _user_fields(self, params, current, actor):
        # Shared by create and update: (fields, err). current = existing
        # user dict (None on create); actor = erp_user doing the change
        # (None = system, treated as superadmin).
        is_new = current == None
        actor_is_super = actor == None or actor.role == ROLE_SUPERADMIN
        is_self = (not is_new) and actor != None and actor.id == current["id"]
        username = (params.get("username") or "").strip()
        role = (params.get("role") or ROLE_ADMIN).strip()
        status = (params.get("status") or "ENABLE").strip().upper()
        if username == "" or len(username) < 3:
            return None, {"status": "ERROR", "desc": "Nama pengguna wajib diisi (minimal 3 karakter)"}
        # end if
        if role not in VALID_ROLES:
            return None, {"status": "ERROR", "desc": "Peran harus Superadmin atau Admin"}
        # end if
        if status not in STATUS_LABELS:
            return None, {"status": "ERROR", "desc": "Status tidak valid"}
        # end if
        existing = self.mgdDB.db_user.find_one({"username": username, "is_deleted": False}, {"_id": 1})
        if existing != None and (is_new or str(existing["_id"]) != current["id"]):
            return None, {"status": "ERROR", "desc": "Nama pengguna sudah ada"}
        # end if
        old_perms = {}
        if not is_new:
            old_perms = current.get("permissions") or {}
        # end if
        permissions = {}
        for area in ACCESS_DEFAULTS:
            level = (params.get("perm_" + area) or "").strip()
            if level == "":
                level = access_level(ROLE_ADMIN, old_perms, area)
            # end if
            if level not in ACCESS_ACTIONS:
                return None, {"status": "ERROR", "desc": "Hak akses " + ACCESS_AREA_LABELS[area] + " tidak valid"}
            # end if
            permissions[area] = level
        # end for
        if not actor_is_super:
            if role == ROLE_SUPERADMIN or ((not is_new) and current.get("role") == ROLE_SUPERADMIN):
                return None, {"status": "ERROR", "desc": "Hanya Superadmin yang bisa mengatur akun Superadmin"}
            # end if
            for area in permissions:
                if ACCESS_RANK[permissions[area]] > ACCESS_RANK[actor.level(area)]:
                    return None, {"status": "ERROR", "desc": "Hak akses " + ACCESS_AREA_LABELS[area] + " tidak boleh melebihi hak akses Anda"}
                # end if
            # end for
        # end if
        if is_self:
            if role != current.get("role"):
                return None, {"status": "ERROR", "desc": "Anda tidak bisa mengubah peran akun sendiri"}
            # end if
            for area in permissions:
                if permissions[area] != access_level(ROLE_ADMIN, old_perms, area):
                    return None, {"status": "ERROR", "desc": "Anda tidak bisa mengubah hak akses akun sendiri"}
                # end if
            # end for
            if status != "ENABLE":
                return None, {"status": "ERROR", "desc": "Anda tidak bisa menonaktifkan akun sendiri"}
            # end if
        # end if
        if (not is_new) and current.get("role") == ROLE_SUPERADMIN:
            if (role != ROLE_SUPERADMIN or status != "ENABLE") and self._superadmin_count() <= 1:
                return None, {"status": "ERROR", "desc": "Superadmin terakhir tidak bisa diubah peran atau statusnya"}
            # end if
        # end if
        fields = {
            "username": username,
            "name": (params.get("name") or "").strip(),
            "email": (params.get("email") or "").strip(),
            "phone": (params.get("phone") or "").strip(),
            "role": role,
            "status": status,
            "permissions": permissions
        }
        return fields, None
    # end def

    def _password_field(self, params, current, actor):
        # Keamanan > Ubah Sandi. ("", None) = keep the current password.
        is_new = current == None
        password = params.get("password") or ""
        confirm = params.get("password_confirm") or ""
        if password == "" and not is_new:
            return "", None
        # end if
        if len(password) < 8:
            return None, {"status": "ERROR", "desc": "Kata sandi minimal 8 karakter"}
        # end if
        if password != confirm:
            return None, {"status": "ERROR", "desc": "Konfirmasi kata sandi tidak sama"}
        # end if
        if (not is_new) and actor != None and actor.id == current["id"]:
            doc = self.mgdDB.db_user.find_one({"_id": ObjectId(current["id"])}, {"password": 1})
            if doc == None or not check_password_hash(doc.get("password", ""), params.get("current_password") or ""):
                return None, {"status": "ERROR", "desc": "Kata sandi saat ini salah"}
            # end if
        # end if
        return generate_password_hash(password), None
    # end def

    def _log_display(self, user):
        out = {
            "name": user.get("name", ""),
            "username": user.get("username", ""),
            "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "role": ROLE_LABELS.get(user.get("role", ""), user.get("role", "")),
            "status": STATUS_LABELS.get(user.get("status", ""), user.get("status", ""))
        }
        perms = user.get("permissions") or {}
        for area in ACCESS_DEFAULTS:
            out["perm_" + area] = ACCESS_LEVEL_LABELS[access_level(ROLE_ADMIN, perms, area)]
        # end for
        return out
    # end def

    def _log_labels(self):
        labels = {
            "name": "Nama", "username": "Login", "email": "Email", "phone": "Telepon",
            "role": "Peran", "status": "Status"
        }
        for area in ACCESS_DEFAULTS:
            labels["perm_" + area] = "Hak akses " + ACCESS_AREA_LABELS[area]
        # end for
        return labels
    # end def

    def _log_actor(self, actor):
        if actor == None:
            return None
        # end if
        return {"id": actor.id, "name": actor.username}
    # end def

    def create_user(self, params, actor=None):
        fields, err = self._user_fields(params, None, actor)
        if err != None:
            return err
        # end if
        password_hash, err = self._password_field(params, None, actor)
        if err != None:
            return err
        # end if
        rec = database.new(self.mgdDB, "db_user")
        rec.put("fk_user_id", "")
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.put("password", password_hash)
        rec.insert()
        saved = rec.get()
        user_id = str(saved.get("_id", ""))
        record_log_proc().log_create("user", user_id, self._log_actor(actor))
        return {"status": "SUCCESS", "desc": "Pengguna dibuat", "id": user_id}
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

    def update_user(self, user_id, params, actor=None):
        current = self.get_user_form(user_id)
        if current == None:
            return {"status": "ERROR", "desc": "Pengguna tidak ditemukan"}
        # end if
        fields, err = self._user_fields(params, current, actor)
        if err != None:
            return err
        # end if
        password_hash, err = self._password_field(params, current, actor)
        if err != None:
            return err
        # end if
        update = {}
        for key in fields:
            update[key] = fields[key]
        # end for
        if password_hash != "":
            update["password"] = password_hash
        # end if
        self.mgdDB.db_user.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": update}
        )
        log = record_log_proc()
        log.log_changes("user", current["id"], self._log_display(current), self._log_display(fields), self._log_labels(), self._log_actor(actor))
        if password_hash != "":
            log.log_event("user", current["id"], "Kata sandi diubah", self._log_actor(actor))
        # end if
        return {"status": "SUCCESS", "desc": "Pengguna diperbarui"}
    # end def

    def delete_user(self, user_id, actor_id):
        return self.delete_users([user_id], actor_id)
    # end def

    def delete_users(self, user_ids, actor_id, actor_is_super=True):
        # Soft delete for one or many users in one update_many. The current
        # account and the last superadmin are never deleted.
        oids = []
        for uid in user_ids:
            if (uid or "") == (actor_id or ""):
                return {"status": "ERROR", "desc": "Tidak bisa menghapus akun yang sedang dipakai"}
            # end if
            try:
                oids.append(ObjectId(uid))
            except Exception:
                pass
            # end try
        # end for
        if len(oids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu pengguna"}
        # end if
        targets = list(self.mgdDB.db_user.find({"_id": {"$in": oids}, "is_deleted": False}, {"role": 1}))
        if len(targets) == 0:
            return {"status": "ERROR", "desc": "Pengguna tidak ditemukan"}
        # end if
        supers = 0
        for rec in targets:
            if rec.get("role") == ROLE_SUPERADMIN:
                supers = supers + 1
            # end if
        # end for
        if supers > 0 and not actor_is_super:
            return {"status": "ERROR", "desc": "Hanya Superadmin yang bisa menghapus akun Superadmin"}
        # end if
        if supers > 0 and self._superadmin_count() - supers < 1:
            return {"status": "ERROR", "desc": "Superadmin terakhir tidak bisa dihapus"}
        # end if
        result = self.mgdDB.db_user.update_many(
            {"_id": {"$in": [rec["_id"] for rec in targets]}},
            {"$set": {"is_deleted": True}}
        )
        if result.modified_count == 1:
            return {"status": "SUCCESS", "desc": "Pengguna dihapus"}
        # end if
        return {"status": "SUCCESS", "desc": str(result.modified_count) + " pengguna dihapus"}
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
