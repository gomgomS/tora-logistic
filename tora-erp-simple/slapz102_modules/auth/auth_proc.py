import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

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


class auth_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def get_login_user(self, user_id):
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
# end class
