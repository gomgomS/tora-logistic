import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import re

import pymongo

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

from contacts.contacts_proc import contacts_proc

# ---------------------------------------------------------------------------
# SHIPMENTS MODULE — business logic layer (Order Entry, LTL + FTL).
#
# A shipment is the customer-facing order. tracking_code (AWB-YYYYMMDD-XXXX)
# is generated from an atomic per-day counter (db_code_counter with
# find_one_and_update $inc), so concurrent order entry can never collide.
#
# status_utama lifecycle:
#   REGISTERED   -> order registered / goods received at origin warehouse
#   MANIFESTED   -> attached to a manifest (consolidated)
#   IN_TRANSIT   -> its manifest departed
#   ARRIVED_HUB  -> parked at a hub (feeder, or waiting for door delivery)
#   OUT_FOR_DELIVERY -> a driver left the hub for the receiver
#   DELIVERED    -> the receiver accepted it (POD)
#
# tracking_logs entries:
#   {milestone_status, location, notes, updated_by, timestamp}
# updated_by stores the str(_id) of the db_user responsible, "SYSTEM" when
# no user context applies.
# ---------------------------------------------------------------------------

SERVICE_TYPES = ["LTL", "FTL"]
SERVICE_CITIES = [
    "Jakarta", "Bandung", "Semarang", "Surabaya", "Malang", "Yogyakarta",
    "Solo", "Denpasar", "Medan", "Palembang", "Pekanbaru", "Makassar",
    "Balikpapan", "Banjarmasin", "Pontianak", "Lampung"
]

STATUS_REGISTERED = "REGISTERED"
STATUS_MANIFESTED = "MANIFESTED"
STATUS_IN_TRANSIT = "IN_TRANSIT"
STATUS_ARRIVED_HUB = "ARRIVED_HUB"
STATUS_OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
STATUS_DELIVERED = "DELIVERED"
SHIPMENT_STATUSES = [
    STATUS_REGISTERED, STATUS_MANIFESTED, STATUS_IN_TRANSIT,
    STATUS_ARRIVED_HUB, STATUS_OUT_FOR_DELIVERY, STATUS_DELIVERED
]

# Milestones available for manual tracking updates from the detail page
MANUAL_MILESTONES = [
    {"value": "IN_TRANSIT", "label": "Dalam Perjalanan"},
    {"value": "ARRIVED_HUB", "label": "Tiba di Hub / Gudang"},
    {"value": "OUT_FOR_DELIVERY", "label": "Diantar ke Penerima"},
    {"value": "DELIVERED", "label": "Terkirim (POD)"}
]


def _place_key(name):
    skip = ("gudang", "hub", "transit", "baru", "utama", "pusat", "cabang")
    words = []
    for word in (name or "").replace("-", " ").split():
        if word.lower() in skip:
            continue
        # end if
        words.append(word)
    # end for
    return " ".join(words).strip().lower()
# end def


def _at_destination_hub(rec):
    # Cargo parked in its own destination city is waiting for door
    # delivery, not another trunk manifest.
    if (rec.get("status_utama") or "") != STATUS_ARRIVED_HUB:
        return False
    # end if
    here = _place_key(rec.get("current_location") or "")
    dest = _place_key(rec.get("destination_city") or "")
    if here == "" or dest == "":
        return False
    # end if
    return here == dest
# end def


def _city_from_regency(regency):
    text = (regency or "").strip()
    prefixes = ("Kota ", "Kabupaten ", "Kab. ")
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip()
        # end if
    # end for
    return text
# end def


def _place_fields(params, side, label):
    # Full wilayah is optional for callers that only send the city (tests, AI).
    # The order form always posts the cascade and the street.
    values = {}
    touched = False
    for key in ("province", "regency", "district", "village", "postal_code", "address"):
        values[key] = (params.get(side + "_" + key) or "").strip()
        if values[key] != "":
            touched = True
        # end if
    # end for
    city = (params.get(side + "_city") or "").strip()
    if touched:
        if values["province"] == "" or values["regency"] == "" or values["district"] == "" or values["village"] == "" or values["address"] == "":
            return None, {"status": "ERROR", "desc": "Lengkapi alamat " + label + ": provinsi sampai kelurahan dan alamat detail"}
        # end if
        postal = values["postal_code"]
        if postal != "" and ((not postal.isdigit()) or len(postal) != 5):
            return None, {"status": "ERROR", "desc": "Kode pos " + label + " tidak valid"}
        # end if
        if city == "":
            city = _city_from_regency(values["regency"])
        # end if
    # end if
    if city == "":
        return None, {"status": "ERROR", "desc": "Alamat " + label + " wajib diisi"}
    # end if
    out = {}
    out[side + "_province"] = values["province"]
    out[side + "_regency"] = values["regency"]
    out[side + "_district"] = values["district"]
    out[side + "_village"] = values["village"]
    out[side + "_postal_code"] = values["postal_code"]
    out[side + "_address"] = values["address"]
    out[side + "_city"] = city
    return out, None
# end def


class shipments_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    # ------------------------------------------------------------------
    # Code generation — atomic, concurrency safe
    # ------------------------------------------------------------------

    def _next_code(self, prefix, date_key):
        counter_key = prefix + "-" + date_key
        rec = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": counter_key},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )
        return counter_key + "-" + str(rec["seq"]).zfill(4)
    # end def

    def generate_tracking_code(self):
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        return self._next_code("AWB", now.strftime("%Y%m%d"))
    # end def

    def now_str(self):
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        return now.strftime("%Y-%m-%d %H:%M:%S")
    # end def

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _shipment_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def list_shipments(self, filters):
        query = {"is_deleted": False}
        status = (filters.get("status") or "").strip().upper()
        if status in SHIPMENT_STATUSES:
            query["status_utama"] = status
        # end if
        service_type = (filters.get("service_type") or "").strip().upper()
        if service_type in SERVICE_TYPES:
            query["service_type"] = service_type
        # end if
        destination_city = (filters.get("destination_city") or "").strip()
        if destination_city != "":
            query["destination_city"] = {
                "$regex": "^" + re.escape(destination_city) + "$", "$options": "i"
            }
        # end if
        q = (filters.get("q") or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"tracking_code": {"$regex": pattern, "$options": "i"}},
                {"po_number": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = list(self.mgdDB.db_shipment.find(query).sort("rec_timestamp", -1).limit(300))
        out = []
        for rec in recs:
            out.append(self._shipment_public(rec))
        # end for
        return out
    # end def

    def get_by_code(self, tracking_code):
        tracking_code = (tracking_code or "").strip()
        if tracking_code == "":
            return None
        # end if
        rec = self.mgdDB.db_shipment.find_one(
            {"tracking_code": tracking_code, "is_deleted": False}
        )
        if rec == None:
            return None
        # end if
        return self._shipment_public(rec)
    # end def

    def get_by_id(self, shipment_id):
        try:
            oid = ObjectId(shipment_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_shipment.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        return self._shipment_public(rec)
    # end def

    def get_shipments_by_ids(self, shipment_ids):
        # Used by the manifest pages; preserves no particular order.
        oids = []
        for sid in shipment_ids:
            if sid == "" or sid == None:
                continue
            # end if
            try:
                oids.append(ObjectId(sid))
            except Exception:
                pass
            # end try
        # end for
        out = []
        if len(oids) == 0:
            return out
        # end if
        recs = self.mgdDB.db_shipment.find({"_id": {"$in": oids}, "is_deleted": False})
        for rec in recs:
            out.append(self._shipment_public(rec))
        # end for
        return out
    # end def

    def available_for_manifest(self):
        # Fresh orders and hub cargo that is free to load. A kiriman still
        # attached to a live manifest (planned, on the road, or arrived but
        # not finished) stays off this list until that manifest is done.
        recs = list(self.mgdDB.db_shipment.find({
            "is_deleted": False,
            "status_utama": {"$in": [STATUS_REGISTERED, STATUS_ARRIVED_HUB]}
        }).sort("rec_timestamp", -1).limit(300))
        codes = []
        for rec in recs:
            code = rec.get("active_manifest_code") or ""
            if not isinstance(code, str):
                code = ""
            # end if
            code = code.strip()
            if code != "" and code not in codes:
                codes.append(code)
            # end if
        # end for
        active_codes = []
        if len(codes) > 0:
            found = self.mgdDB.db_manifest.find({
                "is_deleted": False,
                "manifest_code": {"$in": codes},
                "status": {"$in": ["PLANNED", "IN_TRANSIT", "ARRIVED"]}
            }, {"manifest_code": 1})
            for doc in found:
                active_codes.append(doc.get("manifest_code", ""))
            # end for
        # end if
        out = []
        for rec in recs:
            code = rec.get("active_manifest_code") or ""
            if not isinstance(code, str):
                code = ""
            # end if
            code = code.strip()
            if code != "" and code in active_codes:
                continue
            # end if
            if _at_destination_hub(rec):
                continue
            # end if
            out.append(self._shipment_public(rec))
        # end for
        return out
    # end def

    def sorted_logs(self, shipment):
        logs = shipment.get("tracking_logs", [])
        return sorted(logs, key=lambda x: x.get("timestamp", ""))
    # end def

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_shipment(self, params, updated_by):
        fields, err = self._order_fields(params)
        if err != None:
            return err
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        tracking_code = self.generate_tracking_code()
        origin_city = fields.get("origin_city", "")
        initial_log = {
            "milestone_status": "ORDER_REGISTERED",
            "location": origin_city + " — Gudang Asal",
            "notes": "Order terdaftar / barang diterima di gudang asal",
            "updated_by": updated_by,
            "timestamp": self.now_str()
        }
        rec = database.new(self.mgdDB, "db_shipment")
        rec.put("tracking_code", tracking_code)
        rec.put("po_number", fields.get("po_number", ""))
        rec.put("service_type", fields.get("service_type", ""))
        rec.put("sender_id", fields.get("sender_id", ""))
        rec.put("receiver_id", fields.get("receiver_id", ""))
        rec.put("origin_city", origin_city)
        rec.put("origin_province", fields.get("origin_province", ""))
        rec.put("origin_regency", fields.get("origin_regency", ""))
        rec.put("origin_district", fields.get("origin_district", ""))
        rec.put("origin_village", fields.get("origin_village", ""))
        rec.put("origin_postal_code", fields.get("origin_postal_code", ""))
        rec.put("origin_address", fields.get("origin_address", ""))
        rec.put("destination_city", fields.get("destination_city", ""))
        rec.put("destination_province", fields.get("destination_province", ""))
        rec.put("destination_regency", fields.get("destination_regency", ""))
        rec.put("destination_district", fields.get("destination_district", ""))
        rec.put("destination_village", fields.get("destination_village", ""))
        rec.put("destination_postal_code", fields.get("destination_postal_code", ""))
        rec.put("destination_address", fields.get("destination_address", ""))
        rec.put("status_utama", STATUS_REGISTERED)
        rec.put("current_location", origin_city)
        rec.put("active_manifest_code", "")
        rec.put("active_delivery_code", "")
        rec.put("tracking_logs", [initial_log])
        rec.insert()
        return {"status": "SUCCESS", "desc": "Order dibuat", "tracking_code": tracking_code}
    # end def

    def _order_fields(self, params):
        service_type = (params.get("service_type") or "").strip().upper()
        sender_id = (params.get("sender_id") or "").strip()
        receiver_id = (params.get("receiver_id") or "").strip()
        po_number = (params.get("po_number") or "").strip()
        if service_type not in SERVICE_TYPES:
            return None, {"status": "ERROR", "desc": "Jenis layanan harus LTL atau FTL"}
        # end if
        if sender_id == "" or receiver_id == "":
            return None, {"status": "ERROR", "desc": "Pengirim dan penerima wajib diisi"}
        # end if
        cproc = contacts_proc()
        if cproc.get_contact(sender_id) == None or cproc.get_contact(receiver_id) == None:
            return None, {"status": "ERROR", "desc": "Pengirim dan penerima harus ada di data master kontak"}
        # end if
        origin, origin_err = _place_fields(params, "origin", "pengirim")
        if origin_err != None:
            return None, origin_err
        # end if
        destination, destination_err = _place_fields(params, "destination", "penerima")
        if destination_err != None:
            return None, destination_err
        # end if
        fields = {
            "service_type": service_type,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "po_number": po_number
        }
        fields.update(origin)
        fields.update(destination)
        return fields, None
    # end def

    def update_shipment(self, tracking_code, params):
        shipment = self.get_by_code(tracking_code)
        if shipment == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        if shipment.get("status_utama") != STATUS_REGISTERED:
            return {"status": "ERROR", "desc": "Order yang sudah masuk manifest tidak bisa diubah"}
        # end if
        fields, err = self._order_fields(params)
        if err != None:
            return err
        # end if
        fields["current_location"] = fields["origin_city"]
        self.mgdDB.db_shipment.update_one(
            {"_id": ObjectId(shipment["id"])},
            {"$set": fields}
        )
        return {"status": "SUCCESS", "desc": "Order diperbarui", "tracking_code": shipment.get("tracking_code", "")}
    # end def

    def delete_shipment(self, tracking_code):
        shipment = self.get_by_code(tracking_code)
        if shipment == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        if shipment.get("status_utama") != STATUS_REGISTERED:
            return {"status": "ERROR", "desc": "Order yang sudah masuk manifest tidak bisa dihapus"}
        # end if
        self.mgdDB.db_shipment.update_one(
            {"_id": ObjectId(shipment["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Order dihapus"}
    # end def

    def add_tracking_log(self, tracking_code, milestone_status, location, notes, updated_by):
        shipment = self.get_by_code(tracking_code)
        if shipment == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        milestone_status = (milestone_status or "").strip().upper()
        if milestone_status == "":
            return {"status": "ERROR", "desc": "Status milestone wajib diisi"}
        # end if
        location = (location or "").strip()
        if location == "":
            location = shipment.get("current_location", "")
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        log_entry = {
            "milestone_status": milestone_status,
            "location": location,
            "notes": (notes or "").strip(),
            "updated_by": updated_by,
            "timestamp": self.now_str()
        }
        set_fields = {"current_location": location}
        if milestone_status == "DELIVERED":
            set_fields["status_utama"] = STATUS_DELIVERED
            set_fields["active_manifest_code"] = ""
            set_fields["active_delivery_code"] = ""
        elif milestone_status == "OUT_FOR_DELIVERY":
            set_fields["status_utama"] = STATUS_OUT_FOR_DELIVERY
        elif milestone_status == "IN_TRANSIT":
            set_fields["status_utama"] = STATUS_IN_TRANSIT
        elif milestone_status == "ARRIVED_HUB":
            set_fields["status_utama"] = STATUS_ARRIVED_HUB
        # end if
        self.mgdDB.db_shipment.update_one(
            {"tracking_code": shipment["tracking_code"]},
            {"$set": set_fields, "$push": {"tracking_logs": log_entry}}
        )
        return {"status": "SUCCESS", "desc": "Catatan tracking ditambahkan"}
    # end def

    # ------------------------------------------------------------------
    # Public tracking + dashboard
    # ------------------------------------------------------------------

    def find_for_tracking(self, query):
        # Public search: exact match on tracking_code OR po_number.
        query = (query or "").strip()
        if query == "":
            return None
        # end if
        rec = self.mgdDB.db_shipment.find_one({
            "is_deleted": False,
            "$or": [
                {"tracking_code": query},
                {"po_number": query}
            ]
        })
        if rec == None:
            return None
        # end if
        return self._shipment_public(rec)
    # end def

    def dashboard_stats(self):
        active = self.mgdDB.db_shipment.count_documents({
            "is_deleted": False,
            "status_utama": {"$in": [
                STATUS_REGISTERED, STATUS_MANIFESTED, STATUS_IN_TRANSIT,
                STATUS_ARRIVED_HUB, STATUS_OUT_FOR_DELIVERY
            ]}
        })
        total = self.mgdDB.db_shipment.count_documents({"is_deleted": False})
        delivered = self.mgdDB.db_shipment.count_documents({
            "is_deleted": False, "status_utama": STATUS_DELIVERED
        })
        contacts = self.mgdDB.db_contact.count_documents({"is_deleted": False})
        vehicles = self.mgdDB.db_vehicle.count_documents({"is_deleted": False})
        drivers = self.mgdDB.db_driver.count_documents({"is_deleted": False})
        manifests = self.mgdDB.db_manifest.count_documents({
            "is_deleted": False, "status": {"$in": ["PLANNED", "IN_TRANSIT"]}
        })
        return {
            "shipments_total": total,
            "shipments_active": active,
            "shipments_delivered": delivered,
            "contacts": contacts,
            "vehicles": vehicles,
            "drivers": drivers,
            "manifests_open": manifests
        }
    # end def

    def sidebar_counts(self):
        # Live badges for the ERP sidebar navigation.
        active = self.mgdDB.db_shipment.count_documents({
            "is_deleted": False,
            "status_utama": {"$in": [
                STATUS_REGISTERED, STATUS_MANIFESTED, STATUS_IN_TRANSIT,
                STATUS_ARRIVED_HUB, STATUS_OUT_FOR_DELIVERY
            ]}
        })
        manifests = self.mgdDB.db_manifest.count_documents({
            "is_deleted": False, "status": {"$in": ["PLANNED", "IN_TRANSIT"]}
        })
        return {"shipments_active": active, "manifests_open": manifests}
    # end def

    def status_counts(self):
        # Shipment distribution per status_utama (dashboard bars).
        out = []
        for status in SHIPMENT_STATUSES:
            count = self.mgdDB.db_shipment.count_documents({
                "is_deleted": False, "status_utama": status
            })
            out.append({"status": status, "count": count})
        # end for
        return out
    # end def

    def recent_shipments(self, limit=6):
        recs = list(self.mgdDB.db_shipment.find(
            {"is_deleted": False}
        ).sort("rec_timestamp", -1).limit(limit))
        out = []
        for rec in recs:
            out.append(self._shipment_public(rec))
        # end for
        return out
    # end def
# end class
