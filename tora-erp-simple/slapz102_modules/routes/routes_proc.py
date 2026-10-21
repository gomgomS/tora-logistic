import sys
import re

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config


class routes_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def _oid(self, value):
        try:
            return ObjectId(value)
        except Exception:
            return None
        # end try
    # end def

    def list_hubs(self):
        recs = list(self.mgdDB.db_hub.find({"is_deleted": False}).sort("name", 1))
        out = []
        for rec in recs:
            out.append(self._public(rec))
        # end for
        return out
    # end def

    def find_hub_by_name(self, name):
        name = (name or "").strip()
        if name == "":
            return None
        # end if
        rec = self.mgdDB.db_hub.find_one({
            "is_deleted": False,
            "name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
        })
        if rec == None:
            return None
        # end if
        return self._public(rec)
    # end def

    def ensure_hub(self, name):
        name = (name or "").strip()
        if name == "":
            return {"status": "ERROR", "desc": "Nama hub wajib diisi"}
        # end if
        found = self.find_hub_by_name(name)
        if found != None:
            return {"status": "SUCCESS", "hub": found}
        # end if
        rec = database.new(self.mgdDB, "db_hub")
        rec.put("name", name)
        rec.insert()
        stored = rec.get()
        stored["id"] = str(stored["_id"])
        return {"status": "SUCCESS", "hub": stored}
    # end def

    def list_routes(self):
        recs = list(self.mgdDB.db_route.find({"is_deleted": False}).sort("name", 1))
        out = []
        for rec in recs:
            rec["label"] = rec.get("name") or ""
            out.append(self._public(rec))
        # end for
        return out
    # end def

    def get_route(self, route_id):
        oid = self._oid(route_id)
        if oid == None:
            return None
        # end if
        rec = self.mgdDB.db_route.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        rec["label"] = rec.get("name") or ""
        return self._public(rec)
    # end def

    def _clean_stops(self, names):
        out = []
        seen = []
        for raw in names:
            name = (raw or "").strip()
            if name == "":
                continue
            # end if
            key = name.lower()
            if key in seen:
                return {"status": "ERROR", "desc": "Hub tidak boleh berulang"}
            # end if
            seen.append(key)
            out.append(name)
        # end for
        if len(out) < 2:
            return {"status": "ERROR", "desc": "Rute butuh minimal dua hub"}
        # end if
        return {"status": "SUCCESS", "names": out}
    # end def

    def create_route(self, params):
        name = (params.get("name") or "").strip()
        if name == "":
            return {"status": "ERROR", "desc": "Nama rute wajib diisi"}
        # end if
        existing = self.mgdDB.db_route.find_one({"name": name, "is_deleted": False})
        if existing != None:
            return {"status": "ERROR", "desc": "Nama rute sudah ada"}
        # end if
        raw_names = params.get("hub_names")
        if not isinstance(raw_names, list):
            raw_names = []
        # end if
        cleaned = self._clean_stops(raw_names)
        if cleaned.get("status") != "SUCCESS":
            return cleaned
        # end if
        hub_ids = []
        hub_names = []
        for stop in cleaned["names"]:
            made = self.ensure_hub(stop)
            if made.get("status") != "SUCCESS":
                return made
            # end if
            hub = made["hub"]
            hub_ids.append(hub["id"])
            hub_names.append(hub.get("name", stop))
        # end for
        rec = database.new(self.mgdDB, "db_route")
        rec.put("name", name)
        rec.put("hub_ids", hub_ids)
        rec.put("hub_names", hub_names)
        rec.insert()
        stored = rec.get()
        return {
            "status": "SUCCESS",
            "desc": "Rute disimpan",
            "route_id": str(stored["_id"])
        }
    # end def

    def update_route(self, route_id, params):
        current = self.get_route(route_id)
        if current == None:
            return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
        # end if
        name = (params.get("name") or "").strip()
        if name == "":
            return {"status": "ERROR", "desc": "Nama rute wajib diisi"}
        # end if
        clash = self.mgdDB.db_route.find_one({"name": name, "is_deleted": False})
        if clash != None and str(clash.get("_id", "")) != current["id"]:
            return {"status": "ERROR", "desc": "Nama rute sudah ada"}
        # end if
        raw_names = params.get("hub_names")
        if not isinstance(raw_names, list):
            raw_names = []
        # end if
        cleaned = self._clean_stops(raw_names)
        if cleaned.get("status") != "SUCCESS":
            return cleaned
        # end if
        hub_ids = []
        hub_names = []
        for stop in cleaned["names"]:
            made = self.ensure_hub(stop)
            if made.get("status") != "SUCCESS":
                return made
            # end if
            hub = made["hub"]
            hub_ids.append(hub["id"])
            hub_names.append(hub.get("name", stop))
        # end for
        self.mgdDB.db_route.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"name": name, "hub_ids": hub_ids, "hub_names": hub_names}}
        )
        return {"status": "SUCCESS", "desc": "Rute diperbarui"}
    # end def

    def delete_route(self, route_id):
        current = self.get_route(route_id)
        if current == None:
            return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
        # end if
        self.mgdDB.db_route.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Rute dihapus"}
    # end def
# end class
