import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import re

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# CONTACTS MODULE — business logic layer.
#
# Master contact records (CLIENT / RECEIVER / DRIVER / VENDOR) plus the
# regex search backing the Select2 autocomplete dropdowns used across order
# entry and fleet assignment.
# ---------------------------------------------------------------------------

CATEGORIES = ["CLIENT", "RECEIVER", "DRIVER", "VENDOR"]


class contacts_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _contact_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def _result_text(self, name, company_name, city):
        text = name
        if company_name != "":
            text = text + " — " + company_name
        # end if
        if city != "":
            text = text + " (" + city + ")"
        # end if
        return text
    # end def

    def search_contacts(self, category, q, limit=20):
        # Select2 source: regex search over name OR company_name, optionally
        # restricted to one category. Returns the Select2 "results" payload.
        query = {"is_deleted": False}
        category = (category or "").strip().upper()
        if category in CATEGORIES:
            query["category"] = category
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"company_name": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = self.mgdDB.db_contact.find(query).sort("name", 1).limit(limit)
        results = []
        for rec in recs:
            text = self._result_text(
                rec.get("name", ""),
                rec.get("company_name", ""),
                rec.get("city", "")
            )
            results.append({
                "id": str(rec["_id"]),
                "text": text,
                "name": rec.get("name", ""),
                "company_name": rec.get("company_name", ""),
                "city": rec.get("city", ""),
                "category": rec.get("category", "")
            })
        # end for
        return {"results": results, "pagination": {"more": False}}
    # end def

    def list_contacts(self, category, q=""):
        query = {"is_deleted": False}
        category = (category or "").strip().upper()
        if category in CATEGORIES:
            query["category"] = category
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"company_name": {"$regex": pattern, "$options": "i"}},
                {"email": {"$regex": pattern, "$options": "i"}},
                {"phone": {"$regex": pattern, "$options": "i"}},
                {"city": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = list(self.mgdDB.db_contact.find(query).sort("name", 1))
        out = []
        for rec in recs:
            out.append(self._contact_public(rec))
        # end for
        return out
    # end def

    def get_contact(self, contact_id):
        try:
            oid = ObjectId(contact_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_contact.find_one(
            {"_id": oid, "is_deleted": False}
        )
        if rec == None:
            return None
        # end if
        return self._contact_public(rec)
    # end def

    def get_contacts_map(self, contact_ids):
        # {str(_id): contact doc} for resolving sender/receiver/driver refs.
        oids = []
        for cid in contact_ids:
            if cid == "" or cid == None:
                continue
            # end if
            try:
                oids.append(ObjectId(cid))
            except Exception:
                pass
            # end try
        # end for
        out = {}
        if len(oids) == 0:
            return out
        # end if
        recs = self.mgdDB.db_contact.find({"_id": {"$in": oids}})
        for rec in recs:
            key = str(rec["_id"])
            out[key] = self._contact_public(rec)
        # end for
        return out
    # end def

    def create_contact(self, params):
        name = (params.get("name") or "").strip()
        category = (params.get("category") or "").strip().upper()
        if name == "":
            return {"status": "ERROR", "desc": "Nama kontak wajib diisi"}
        # end if
        if category not in CATEGORIES:
            return {"status": "ERROR", "desc": "Kategori harus Klien, Penerima, Sopir, atau Vendor"}
        # end if
        rec = database.new(self.mgdDB, "db_contact")
        rec.put("name", name)
        rec.put("company_name", (params.get("company_name") or "").strip())
        rec.put("phone", (params.get("phone") or "").strip())
        rec.put("email", (params.get("email") or "").strip())
        rec.put("address", (params.get("address") or "").strip())
        rec.put("city", (params.get("city") or "").strip())
        rec.put("category", category)
        rec.insert()
        saved = rec.get()
        saved_name = saved.get("name", "")
        return {
            "status": "SUCCESS",
            "desc": "Kontak dibuat",
            "id": str(saved.get("_id", "")),
            "name": saved_name,
            "text": self._result_text(
                saved_name,
                saved.get("company_name", ""),
                saved.get("city", "")
            )
        }
    # end def

    def update_contact(self, contact_id, params):
        contact = self.get_contact(contact_id)
        if contact == None:
            return {"status": "ERROR", "desc": "Kontak tidak ditemukan"}
        # end if
        name = (params.get("name") or "").strip()
        category = (params.get("category") or "").strip().upper()
        if name == "":
            return {"status": "ERROR", "desc": "Nama kontak wajib diisi"}
        # end if
        if category not in CATEGORIES:
            return {"status": "ERROR", "desc": "Kategori harus Klien, Penerima, Sopir, atau Vendor"}
        # end if
        self.mgdDB.db_contact.update_one(
            {"_id": ObjectId(contact["id"])},
            {"$set": {
                "name": name,
                "company_name": (params.get("company_name") or "").strip(),
                "phone": (params.get("phone") or "").strip(),
                "email": (params.get("email") or "").strip(),
                "address": (params.get("address") or "").strip(),
                "city": (params.get("city") or "").strip(),
                "category": category
            }}
        )
        return {"status": "SUCCESS", "desc": "Kontak diperbarui"}
    # end def

    def delete_contact(self, contact_id):
        contact = self.get_contact(contact_id)
        if contact == None:
            return {"status": "ERROR", "desc": "Kontak tidak ditemukan"}
        # end if
        self.mgdDB.db_contact.update_one(
            {"_id": ObjectId(contact["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Kontak dihapus"}
    # end def
# end class
