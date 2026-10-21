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

from contacts.contacts_proc import contacts_proc

# ---------------------------------------------------------------------------
# FLEET MODULE — business logic layer.
#
# Vehicles (internal + vendor units, unique plate numbers) and drivers
# (linked to a DRIVER-category contact), plus the Select2 autocomplete
# sources used when assigning fleet to a manifest.
# ---------------------------------------------------------------------------

VEHICLE_TYPES = ["CDD", "CDE", "Blind Van", "Fuso", "Wingbox", "Tronton", "Trailer 20ft", "Trailer 40ft"]
OWNERSHIPS = ["INTERNAL", "VENDOR"]
DRIVER_TYPES = ["INTERNAL", "VENDOR"]


class fleet_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _vehicle_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def search_vehicles(self, q, limit=20):
        # Select2 source: regex over plate_number OR vehicle_type.
        query = {"is_deleted": False}
        q = (q or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"plate_number": {"$regex": pattern, "$options": "i"}},
                {"vehicle_type": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = self.mgdDB.db_vehicle.find(query).sort("plate_number", 1).limit(limit)
        results = []
        for rec in recs:
            results.append({
                "id": str(rec["_id"]),
                "text": self.vehicle_label(rec),
                "ownership": rec.get("ownership", "")
            })
        # end for
        return {"results": results, "pagination": {"more": False}}
    # end def

    def vehicle_label(self, rec):
        text = rec.get("plate_number", "") + " — " + rec.get("vehicle_type", "")
        if rec.get("ownership", "") == "VENDOR" and rec.get("vendor_name", "") != "":
            text = text + " (VENDOR: " + rec.get("vendor_name", "") + ")"
        else:
            text = text + " (" + rec.get("ownership", "INTERNAL") + ")"
        # end if
        return text
    # end def

    def list_vehicles(self):
        recs = list(self.mgdDB.db_vehicle.find(
            {"is_deleted": False}
        ).sort("plate_number", 1))
        out = []
        for rec in recs:
            out.append(self._vehicle_public(rec))
        # end for
        return out
    # end def

    def create_vehicle(self, params):
        plate = (params.get("plate_number") or "").strip().upper()
        vehicle_type = (params.get("vehicle_type") or "").strip()
        ownership = (params.get("ownership") or "").strip().upper()
        if plate == "":
            return {"status": "ERROR", "desc": "Nomor polisi wajib diisi"}
        # end if
        if vehicle_type == "":
            return {"status": "ERROR", "desc": "Jenis kendaraan wajib diisi"}
        # end if
        if ownership not in OWNERSHIPS:
            return {"status": "ERROR", "desc": "Kepemilikan harus Internal atau Vendor"}
        # end if
        duplicate = self.mgdDB.db_vehicle.find_one({
            "plate_number": {"$regex": "^" + re.escape(plate) + "$", "$options": "i"},
            "is_deleted": False
        })
        if duplicate != None:
            return {"status": "ERROR", "desc": "Nomor polisi sudah terdaftar"}
        # end if
        vendor_name = ""
        if ownership == "VENDOR":
            vendor_name = (params.get("vendor_name") or "").strip()
        # end if
        rec = database.new(self.mgdDB, "db_vehicle")
        rec.put("plate_number", plate)
        rec.put("vehicle_type", vehicle_type)
        rec.put("ownership", ownership)
        rec.put("vendor_name", vendor_name)
        rec.insert()
        return {"status": "SUCCESS", "desc": "Kendaraan dibuat"}
    # end def

    def update_vehicle(self, vehicle_id, params):
        current = self.get_vehicle(vehicle_id)
        if current == None:
            return {"status": "ERROR", "desc": "Kendaraan tidak ditemukan"}
        # end if
        plate = (params.get("plate_number") or "").strip().upper()
        vehicle_type = (params.get("vehicle_type") or "").strip()
        ownership = (params.get("ownership") or "").strip().upper()
        if plate == "":
            return {"status": "ERROR", "desc": "Nomor polisi wajib diisi"}
        # end if
        if vehicle_type == "":
            return {"status": "ERROR", "desc": "Jenis kendaraan wajib diisi"}
        # end if
        if ownership not in OWNERSHIPS:
            return {"status": "ERROR", "desc": "Kepemilikan harus Internal atau Vendor"}
        # end if
        duplicate = self.mgdDB.db_vehicle.find_one({
            "plate_number": {"$regex": "^" + re.escape(plate) + "$", "$options": "i"},
            "is_deleted": False
        })
        if duplicate != None and str(duplicate.get("_id", "")) != current["id"]:
            return {"status": "ERROR", "desc": "Nomor polisi sudah terdaftar"}
        # end if
        vendor_name = ""
        if ownership == "VENDOR":
            vendor_name = (params.get("vendor_name") or "").strip()
        # end if
        self.mgdDB.db_vehicle.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {
                "plate_number": plate,
                "vehicle_type": vehicle_type,
                "ownership": ownership,
                "vendor_name": vendor_name
            }}
        )
        return {"status": "SUCCESS", "desc": "Kendaraan diperbarui"}
    # end def

    def delete_vehicle(self, vehicle_id):
        current = self.get_vehicle(vehicle_id)
        if current == None:
            return {"status": "ERROR", "desc": "Kendaraan tidak ditemukan"}
        # end if
        self.mgdDB.db_vehicle.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Kendaraan dihapus"}
    # end def

    def get_vehicle(self, vehicle_id):
        try:
            oid = ObjectId(vehicle_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_vehicle.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        return self._vehicle_public(rec)
    # end def

    def get_vehicles_map(self, vehicle_ids):
        oids = []
        for vid in vehicle_ids:
            if vid == "" or vid == None:
                continue
            # end if
            try:
                oids.append(ObjectId(vid))
            except Exception:
                pass
            # end try
        # end for
        out = {}
        if len(oids) == 0:
            return out
        # end if
        recs = self.mgdDB.db_vehicle.find({"_id": {"$in": oids}})
        for rec in recs:
            key = str(rec["_id"])
            out[key] = self._vehicle_public(rec)
        # end for
        return out
    # end def

    def _driver_public(self, doc, contacts_map):
        doc["id"] = str(doc.pop("_id"))
        contact = contacts_map.get(doc.get("contact_id", ""), None)
        doc["contact_name"] = contact.get("name", "") if contact != None else ""
        doc["contact_phone"] = contact.get("phone", "") if contact != None else ""
        return doc
    # end def

    def _drivers_contacts_map(self, recs):
        cproc = contacts_proc()
        return cproc.get_contacts_map([rec.get("contact_id", "") for rec in recs])
    # end def

    def search_drivers(self, q, limit=20):
        # Select2 source: drivers joined with their DRIVER contact for the
        # display name; search matches contact name or license number.
        query = {"is_deleted": False}
        recs = list(self.mgdDB.db_driver.find(query).limit(100))
        contacts_map = self._drivers_contacts_map(recs)
        q = (q or "").strip().lower()
        results = []
        for rec in recs:
            label = self.driver_label(rec, contacts_map)
            if q != "" and q not in label.lower():
                continue
            # end if
            results.append({"id": str(rec["_id"]), "text": label})
            if len(results) >= limit:
                break
            # end if
        # end for
        return {"results": results, "pagination": {"more": False}}
    # end def

    def driver_label(self, rec, contacts_map):
        contact = contacts_map.get(rec.get("contact_id", ""), None)
        name = contact.get("name", "") if contact != None else "(contact missing)"
        text = name + " — SIM " + rec.get("license_number", "")
        text = text + " (" + rec.get("type", "INTERNAL") + ")"
        return text
    # end def

    def list_drivers(self):
        recs = list(self.mgdDB.db_driver.find(
            {"is_deleted": False}
        ).sort("license_number", 1))
        contacts_map = self._drivers_contacts_map(recs)
        out = []
        for rec in recs:
            out.append(self._driver_public(rec, contacts_map))
        # end for
        return out
    # end def

    def create_driver(self, params):
        contact_id = (params.get("contact_id") or "").strip()
        license_number = (params.get("license_number") or "").strip()
        driver_type = (params.get("type") or "").strip().upper()
        if contact_id == "":
            return {"status": "ERROR", "desc": "Kontak sopir wajib diisi"}
        # end if
        cproc = contacts_proc()
        contact = cproc.get_contact(contact_id)
        if contact == None:
            return {"status": "ERROR", "desc": "Kontak yang dipilih tidak ditemukan"}
        # end if
        if license_number == "":
            return {"status": "ERROR", "desc": "Nomor SIM wajib diisi"}
        # end if
        if driver_type not in DRIVER_TYPES:
            return {"status": "ERROR", "desc": "Tipe sopir harus Internal atau Vendor"}
        # end if
        rec = database.new(self.mgdDB, "db_driver")
        rec.put("contact_id", contact_id)
        rec.put("license_number", license_number)
        rec.put("type", driver_type)
        rec.insert()
        return {"status": "SUCCESS", "desc": "Sopir dibuat"}
    # end def

    def update_driver(self, driver_id, params):
        current = self.get_driver(driver_id)
        if current == None:
            return {"status": "ERROR", "desc": "Sopir tidak ditemukan"}
        # end if
        contact_id = (params.get("contact_id") or "").strip()
        license_number = (params.get("license_number") or "").strip()
        driver_type = (params.get("type") or "").strip().upper()
        if contact_id == "":
            return {"status": "ERROR", "desc": "Kontak sopir wajib diisi"}
        # end if
        if contacts_proc().get_contact(contact_id) == None:
            return {"status": "ERROR", "desc": "Kontak yang dipilih tidak ditemukan"}
        # end if
        if license_number == "":
            return {"status": "ERROR", "desc": "Nomor SIM wajib diisi"}
        # end if
        if driver_type not in DRIVER_TYPES:
            return {"status": "ERROR", "desc": "Tipe sopir harus Internal atau Vendor"}
        # end if
        self.mgdDB.db_driver.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {
                "contact_id": contact_id,
                "license_number": license_number,
                "type": driver_type
            }}
        )
        return {"status": "SUCCESS", "desc": "Sopir diperbarui"}
    # end def

    def delete_driver(self, driver_id):
        current = self.get_driver(driver_id)
        if current == None:
            return {"status": "ERROR", "desc": "Sopir tidak ditemukan"}
        # end if
        self.mgdDB.db_driver.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Sopir dihapus"}
    # end def

    def get_driver(self, driver_id):
        try:
            oid = ObjectId(driver_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_driver.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        return self._driver_public(rec, self._drivers_contacts_map([rec]))
    # end def

    def get_drivers_map(self, driver_ids):
        oids = []
        for did in driver_ids:
            if did == "" or did == None:
                continue
            # end if
            try:
                oids.append(ObjectId(did))
            except Exception:
                pass
            # end try
        # end for
        out = {}
        if len(oids) == 0:
            return out
        # end if
        recs = list(self.mgdDB.db_driver.find({"_id": {"$in": oids}}))
        contacts_map = self._drivers_contacts_map(recs)
        for rec in recs:
            key = str(rec["_id"])
            out[key] = self._driver_public(rec, contacts_map)
        # end for
        return out
    # end def
# end class
