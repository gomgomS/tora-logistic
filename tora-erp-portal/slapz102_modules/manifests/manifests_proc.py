import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import json
import random
import re
import urllib.error
import urllib.request

import pymongo

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

from shipments.shipments_proc import shipments_proc
from fleet.fleet_proc import fleet_proc
from shipments.shipments_proc import (
    STATUS_REGISTERED, STATUS_MANIFESTED, STATUS_IN_TRANSIT, STATUS_ARRIVED_HUB,
    STATUS_OUT_FOR_DELIVERY, STATUS_DELIVERED
)

# ---------------------------------------------------------------------------
# MANIFESTS MODULE — business logic layer (Consolidated Manifest System).
#
# A manifest consolidates one or many shipments onto one vehicle + driver:
#   - LTL trunk leg   : many shipments, one truck (Jakarta -> Surabaya)
#   - LTL feeder leg  : deconsolidated at the hub, re-manifested (Surabaya
#                       -> Malang) via the transit-hub sorting page
#   - FTL dedicated   : single shipment, optional client_id recorded
#
# THE CORE MECHANISM (bulk tracking update):
#   updating a manifest's status/location executes ONE MongoDB update_many()
#   targeting {_id: {$in: manifest.shipment_ids}} that both $set's the new
#   shipment status and $push'es the same milestone into every shipment's
#   embedded tracking_logs array — one statement, N customer trackings.
#
# Manifest status: PLANNED -> IN_TRANSIT -> ARRIVED -> COMPLETED (forward
# only). On COMPLETED every shipment stays ARRIVED_HUB at the last hub.
# Cargo for another city waits for a feeder manifest. Cargo already in its
# destination city waits on /hub for door delivery (antar).
# ---------------------------------------------------------------------------

STATUS_PLANNED = "PLANNED"
STATUS_IN_TRANSIT = "IN_TRANSIT"
STATUS_ARRIVED = "ARRIVED"
STATUS_COMPLETED = "COMPLETED"
MANIFEST_STATUSES = [STATUS_PLANNED, STATUS_IN_TRANSIT, STATUS_ARRIVED, STATUS_COMPLETED]
def _clip(value, limit):
    text = (value or "").strip()
    if len(text) > limit:
        text = text[:limit]
    # end if
    return text
# end def

def _city_name(regency):
    text = (regency or "").strip()
    prefixes = ("Kota ", "Kabupaten ", "Kab. ")
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip()
        # end if
    # end for
    return text
# end def

def _region_id(value):
    text = (value or "").strip()
    if text == "" or len(text) > 24:
        return ""
    # end if
    for ch in text:
        if ch != "." and (not ch.isdigit()):
            return ""
        # end if
    # end for
    return text
# end def

def _guess_city(name):
    skip = ("gudang", "hub", "transit", "baru", "utama", "pusat", "cabang")
    words = []
    for word in (name or "").replace("-", " ").split():
        if word.lower() in skip:
            continue
        # end if
        words.append(word)
    # end for
    return " ".join(words).strip()
# end def

STATUS_ORDER = {
    STATUS_PLANNED: 0,
    STATUS_IN_TRANSIT: 1,
    STATUS_ARRIVED: 2,
    STATUS_COMPLETED: 3
}


class manifests_proc:

    mgdDB = database.get_db_conn(config.mainDB)
    _place_index = None
    _place_seen = None

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _manifest_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def _to_object_ids(self, ref_ids):
        oids = []
        for ref_id in ref_ids:
            if ref_id == "" or ref_id == None:
                continue
            # end if
            try:
                oids.append(ObjectId(ref_id))
            except Exception:
                pass
            # end try
        # end for
        return oids
    # end def

    # ------------------------------------------------------------------
    # Code generation — atomic, concurrency safe
    # ------------------------------------------------------------------

    def generate_manifest_code(self):
        sproc = shipments_proc()
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        return sproc._next_code("MAN", now.strftime("%Y%m%d"))
    # end def

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_manifests(self, status):
        query = {"is_deleted": False}
        status = (status or "").strip().upper()
        if status in MANIFEST_STATUSES:
            query["status"] = status
        # end if
        recs = list(self.mgdDB.db_manifest.find(query).sort("rec_timestamp", -1).limit(200))
        out = []
        for rec in recs:
            out.append(self._manifest_public(rec))
        # end for
        return out
    # end def

    def get_by_code(self, manifest_code):
        manifest_code = (manifest_code or "").strip()
        if manifest_code == "":
            return None
        # end if
        rec = self.mgdDB.db_manifest.find_one(
            {"manifest_code": manifest_code, "is_deleted": False}
        )
        if rec == None:
            return None
        # end if
        return self._manifest_public(rec)
    # end def

    def next_statuses(self, current_status):
        out = []
        for status in MANIFEST_STATUSES:
            if STATUS_ORDER[status] > STATUS_ORDER.get(current_status, -1):
                out.append(status)
            # end if
        # end for
        return out
    # end def

    def list_hubs(self):
        recs = list(self.mgdDB.db_hub.find({"is_deleted": False}).sort("name", 1))
        out = []
        for rec in recs:
            rec["id"] = str(rec.pop("_id"))
            out.append(rec)
        # end for
        return out
    # end def

    def wilayah(self, kind, params):
        # Static Indonesian region files from emsifa (Kepmendagri + kode pos).
        # Proxied so the browser does not depend on that site allowing this origin.
        # https://www.emsifa.com/api-wilayah-indonesia/
        kind = (kind or "").strip()
        base = "https://www.emsifa.com/api-wilayah-indonesia/v2"
        url = ""
        if kind == "provinsi":
            url = base + "/provinces.json"
        elif kind == "kabkota":
            pid = _region_id(params.get("provinsi_id"))
            if pid == "":
                return {"status": "ERROR", "desc": "Pilih provinsi", "results": []}
            # end if
            url = base + "/regencies/" + pid + ".json"
        elif kind == "kecamatan":
            kid = _region_id(params.get("kabkota_id"))
            if kid == "":
                return {"status": "ERROR", "desc": "Pilih kabupaten", "results": []}
            # end if
            url = base + "/districts/" + kid + ".json"
        elif kind == "kelurahan":
            did = _region_id(params.get("kecamatan_id"))
            if did == "":
                return {"status": "ERROR", "desc": "Pilih kecamatan", "results": []}
            # end if
            url = base + "/villages/" + did + ".json"
        elif kind == "kodepos":
            vid = _region_id(params.get("kelurahan_id"))
            if vid == "":
                return {"status": "ERROR", "desc": "Pilih kelurahan", "results": []}
            # end if
            url = base + "/villages/" + vid + ".json"
        else:
            return {"status": "ERROR", "desc": "Wilayah tidak dikenal", "results": []}
        # end if
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ToraERP/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            # end with
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {"status": "ERROR", "desc": "Data wilayah sedang tidak bisa dihubungi", "results": []}
        # end try
        raw = payload.get("data")
        rows = []
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            rows = [raw]
        # end if
        results = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # end if
            if kind == "kodepos":
                code = str(row.get("postal_code") or "").strip()
                if code == "":
                    continue
                # end if
                results.append({"id": code, "text": code})
                continue
            # end if
            rid = str(row.get("id") or "").strip()
            text = str(row.get("name") or "").strip()
            if rid == "" or text == "":
                continue
            # end if
            item = {"id": rid, "text": text}
            if kind == "kelurahan":
                item["postal_code"] = str(row.get("postal_code") or "").strip()
            # end if
            results.append(item)
        # end for
        return {"status": "SUCCESS", "results": results}
    # end def

    def _match_regency(self, city):
        key = (city or "").strip().lower()
        aliases = {
            "solo": "surakarta",
            "jogja": "yogyakarta",
            "yogya": "yogyakarta",
            "bali": "denpasar"
        }
        key = aliases.get(key, key)
        if key == "":
            return None
        # end if
        if manifests_proc._place_index == None:
            manifests_proc._place_index = {}
        # end if
        if manifests_proc._place_seen == None:
            manifests_proc._place_seen = []
        # end if
        cached = manifests_proc._place_index.get(key)
        if cached != None:
            return cached
        # end if
        provinces = self.wilayah("provinsi", {}).get("results") or []
        for province in provinces:
            pid = province.get("id", "")
            if pid in manifests_proc._place_seen:
                continue
            # end if
            regencies = self.wilayah("kabkota", {"provinsi_id": pid}).get("results") or []
            manifests_proc._place_seen.append(pid)
            for regency in regencies:
                label = _city_name(regency.get("text", "")).lower()
                if label == "":
                    continue
                # end if
                current = manifests_proc._place_index.get(label)
                text = regency.get("text", "")
                if current != None and text.lower().startswith("kabupaten"):
                    continue
                # end if
                manifests_proc._place_index[label] = {
                    "province": province.get("text", ""),
                    "regency": text,
                    "id": regency.get("id", "")
                }
            # end for
            if key in manifests_proc._place_index:
                return manifests_proc._place_index.get(key)
            # end if
        # end for
        return None
    # end def

    def _regency_options(self, city):
        # Exact city first. "Jakarta" is not a single kabupaten, so also
        # accept Kota Jakarta Pusat, Kota Jakarta Barat, and the rest.
        key = (city or "").strip().lower()
        aliases = {
            "solo": "surakarta",
            "jogja": "yogyakarta",
            "yogya": "yogyakarta"
        }
        key = aliases.get(key, key)
        exact = self._match_regency(key)
        if exact != None:
            return [exact]
        # end if
        if manifests_proc._place_index == None:
            return []
        # end if
        options = []
        kota = []
        for label in manifests_proc._place_index:
            row = manifests_proc._place_index.get(label)
            if label == key or label.startswith(key + " ") or (" " + key + " ") in (" " + label + " ") or label.endswith(" " + key):
                text = (row.get("regency") or "").lower()
                if text.startswith("kota"):
                    kota.append(row)
                else:
                    options.append(row)
                # end if
            # end if
        # end for
        if len(kota) > 0:
            return kota
        # end if
        return options
    # end def

    def suggest_party_place(self, city):
        # A full pengirim / penerima address from the emsifa wilayah list.
        city = _city_name((city or "").strip())
        options = self._regency_options(city)
        if len(options) == 0:
            return None
        # end if
        match = options[random.randrange(len(options))]
        districts = self.wilayah("kecamatan", {"kabkota_id": match.get("id", "")}).get("results") or []
        if len(districts) == 0:
            return None
        # end if
        district = districts[random.randrange(len(districts))]
        villages = self.wilayah("kelurahan", {"kecamatan_id": district.get("id", "")}).get("results") or []
        if len(villages) == 0:
            return None
        # end if
        village = villages[random.randrange(len(villages))]
        number = str(random.randint(1, 180))
        street = village.get("text") or city
        return {
            "province": match.get("province", ""),
            "regency": match.get("regency", ""),
            "district": district.get("text", ""),
            "village": village.get("text", ""),
            "postal_code": village.get("postal_code") or "",
            "address": "Jl. " + street + " No. " + number,
            "city": _city_name(match.get("regency", "")) or city
        }
    # end def

    def suggest_hub_place(self, params):
        # Fills a blank hub address from the emsifa wilayah list so the chat
        # can save province through kode pos, not only the hub name.
        params = dict(params or {})
        if _clip(params.get("province"), 80) != "" and _clip(params.get("village"), 80) != "" and _clip(params.get("address"), 240) != "":
            return params
        # end if
        city = _city_name(_clip(params.get("regency"), 80))
        if city == "":
            city = _guess_city(_clip(params.get("name"), 80))
        # end if
        if city == "":
            return params
        # end if
        match = self._match_regency(city)
        if match == None:
            return params
        # end if
        districts = self.wilayah("kecamatan", {"kabkota_id": match.get("id", "")}).get("results") or []
        if len(districts) == 0:
            return params
        # end if
        district = districts[0]
        villages = self.wilayah("kelurahan", {"kecamatan_id": district.get("id", "")}).get("results") or []
        if len(villages) == 0:
            return params
        # end if
        village = villages[0]
        if _clip(params.get("province"), 80) == "":
            params["province"] = match.get("province", "")
        # end if
        if _clip(params.get("regency"), 80) == "":
            params["regency"] = match.get("regency", "")
        # end if
        if _clip(params.get("district"), 80) == "":
            params["district"] = district.get("text", "")
        # end if
        if _clip(params.get("village"), 80) == "":
            params["village"] = village.get("text", "")
        # end if
        if _clip(params.get("postal_code"), 10) == "":
            params["postal_code"] = village.get("postal_code") or ""
        # end if
        if _clip(params.get("address"), 240) == "":
            params["address"] = "Jl. " + (village.get("text") or city) + " No. 1"
        # end if
        return params
    # end def

    def prepare_hub_args(self, params):
        params = dict(params or {})
        needs_place = _clip(params.get("address"), 240) == "" or _clip(params.get("village"), 80) == ""
        if not needs_place:
            return params
        # end if
        existing = self._find_hub_by_name(params.get("name"))
        if existing != None and (existing.get("address") or "").strip() != "":
            return params
        # end if
        return self.suggest_hub_place(params)
    # end def

    def create_hub(self, params):
        province = _clip(params.get("province"), 80)
        regency = _clip(params.get("regency"), 80)
        district = _clip(params.get("district"), 80)
        village = _clip(params.get("village"), 80)
        postal = _clip(params.get("postal_code"), 10)
        address = _clip(params.get("address"), 240)
        name = _clip(params.get("name"), 80)
        has_region = province != "" or regency != "" or district != "" or village != "" or postal != ""
        if has_region:
            if province == "" or regency == "" or district == "" or village == "" or address == "":
                return {"status": "ERROR", "desc": "Lengkapi provinsi sampai kelurahan dan alamat detail"}
            # end if
            if postal != "" and ((not postal.isdigit()) or len(postal) != 5):
                return {"status": "ERROR", "desc": "Kode pos tidak valid"}
            # end if
            if name == "":
                name = _city_name(regency)
            # end if
        # end if
        if name == "":
            return {"status": "ERROR", "desc": "Nama hub wajib diisi"}
        # end if
        existing = self.mgdDB.db_hub.find_one({
            "is_deleted": False,
            "name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
        })
        if existing != None:
            if has_region or address != "":
                patch = {"name": existing.get("name", name)}
                for key in ("province", "regency", "district", "village", "postal_code", "address"):
                    if key in params and _clip(params.get(key), 240) != "":
                        patch[key] = params.get(key)
                    # end if
                # end for
                return self.update_hub(patch)
            # end if
            return {"status": "ERROR", "desc": "Hub sudah ada"}
        # end if
        rec = database.new(self.mgdDB, "db_hub")
        rec.put("name", name)
        rec.put("province", province)
        rec.put("regency", regency)
        rec.put("district", district)
        rec.put("village", village)
        rec.put("postal_code", postal)
        rec.put("address", address)
        rec.insert()
        return {"status": "SUCCESS", "desc": "Hub dibuat", "name": name}
    # end def

    def _find_hub_by_name(self, name):
        name = (name or "").strip()
        if name == "":
            return None
        # end if
        return self.mgdDB.db_hub.find_one({
            "is_deleted": False,
            "name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
        })
    # end def

    def _find_hub_for_stop(self, label):
        label = (label or "").strip()
        if label == "":
            return None
        # end if
        found = self._find_hub_by_name(label)
        if found != None:
            return found
        # end if
        city = _guess_city(label)
        names = []
        if city != "" and "hub" not in label.lower():
            names.append(city + " Hub")
        # end if
        mapped = {
            "bali": "Denpasar",
            "solo": "Surakarta",
            "jogja": "Yogyakarta",
            "yogya": "Yogyakarta"
        }.get(city.lower(), "")
        if mapped != "":
            names.append(mapped + " Hub")
        # end if
        for name in names:
            found = self._find_hub_by_name(name)
            if found != None:
                return found
            # end if
        # end for
        wanted = []
        if city != "":
            wanted.append(city.lower())
        # end if
        if mapped != "":
            wanted.append(mapped.lower())
        # end if
        if len(wanted) == 0:
            return None
        # end if
        for rec in self.mgdDB.db_hub.find({"is_deleted": False}):
            hub_city = _guess_city(rec.get("name", "")).lower()
            if hub_city in wanted:
                return rec
            # end if
        # end for
        return None
    # end def

    def ensure_hub(self, label):
        label = _clip(label, 80)
        found = self._find_hub_for_stop(label)
        if found != None:
            return found, None
        # end if
        city = _guess_city(label)
        mapped = {
            "bali": "Denpasar",
            "solo": "Surakarta",
            "jogja": "Yogyakarta",
            "yogya": "Yogyakarta"
        }.get(city.lower(), "")
        name = label
        if mapped != "":
            name = mapped + " Hub"
        elif city != "" and "hub" not in label.lower() and "gudang" not in label.lower():
            name = city + " Hub"
        # end if
        params = self.prepare_hub_args({"name": name})
        result = self.create_hub(params)
        if result.get("status") != "SUCCESS":
            return None, result
        # end if
        found = self._find_hub_by_name(result.get("name") or name)
        if found == None:
            return None, {"status": "ERROR", "desc": "Hub tidak ditemukan"}
        # end if
        return found, None
    # end def

    def _hub_with_exact_name(self, label):
        name = _clip(label, 80)
        city = _guess_city(name)
        if city != "" and "hub" not in name.lower() and "gudang" not in name.lower():
            name = city + " Hub"
        # end if
        found = self._find_hub_by_name(name)
        if found != None:
            return found, None
        # end if
        result = self.create_hub(self.prepare_hub_args({"name": name}))
        if result.get("status") != "SUCCESS":
            return None, result
        # end if
        found = self._find_hub_by_name(result.get("name") or name)
        if found == None:
            return None, {"status": "ERROR", "desc": "Hub tidak ditemukan"}
        # end if
        return found, None
    # end def

    def _default_fleet(self):
        fproc = fleet_proc()
        vehicles = fproc.list_vehicles()
        drivers = fproc.list_drivers()
        vehicle_id = ""
        driver_id = ""
        for vehicle in vehicles:
            if vehicle.get("ownership") == "INTERNAL":
                vehicle_id = vehicle.get("id", "")
                break
            # end if
        # end for
        if vehicle_id == "" and len(vehicles) > 0:
            vehicle_id = vehicles[0].get("id", "")
        # end if
        for driver in drivers:
            if driver.get("type") == "INTERNAL":
                driver_id = driver.get("id", "")
                break
            # end if
        # end for
        if driver_id == "" and len(drivers) > 0:
            driver_id = drivers[0].get("id", "")
        # end if
        if vehicle_id == "" or driver_id == "":
            return "", "", {"status": "ERROR", "desc": "Belum ada kendaraan atau sopir untuk rute ini"}
        # end if
        return vehicle_id, driver_id, None
    # end def

    def create_route_by_stops(self, params):
        raw = params.get("stops")
        if raw == None:
            raw = params.get("hub_names", [])
        # end if
        if isinstance(raw, str):
            raw = raw.replace("→", ",").replace("->", ",").split(",")
        # end if
        if not isinstance(raw, list):
            raw = []
        # end if
        stops = []
        for item in raw:
            text = ""
            if isinstance(item, str):
                text = _clip(item, 80)
            # end if
            if text != "":
                stops.append(text)
            # end if
        # end for
        if len(stops) < 2:
            return {"status": "ERROR", "desc": "Rute butuh minimal asal dan tujuan"}
        # end if
        ids = []
        names = []
        for stop in stops:
            hub, err = self.ensure_hub(stop)
            if err != None:
                return err
            # end if
            hub_id = str(hub.get("_id") or hub.get("id") or "")
            if hub_id in ids:
                # "Bali" can point at Denpasar. If that hub is already a stop,
                # keep the typed name as its own hub.
                hub, err = self._hub_with_exact_name(stop)
                if err != None:
                    return err
                # end if
                hub_id = str(hub.get("_id") or hub.get("id") or "")
            # end if
            if hub_id in ids:
                return {"status": "ERROR", "desc": "Hub tidak boleh berulang"}
            # end if
            ids.append(hub_id)
            names.append(hub.get("name", stop))
        # end for
        vehicle_id = (params.get("vehicle_id") or "").strip()
        driver_id = (params.get("driver_id") or "").strip()
        if vehicle_id == "" or driver_id == "":
            vehicle_id, driver_id, fleet_err = self._default_fleet()
            if fleet_err != None:
                return fleet_err
            # end if
        # end if
        route_name = _clip(params.get("name"), 80)
        if route_name == "":
            route_name = _guess_city(names[0]) + " ke " + _guess_city(names[-1])
            route_name = _clip(route_name, 80)
        # end if
        result = self.create_route({
            "name": route_name,
            "hub_ids": ids,
            "vehicle_id": vehicle_id,
            "driver_id": driver_id
        })
        if result.get("status") == "SUCCESS":
            result["name"] = route_name
            result["label"] = " → ".join(names)
            saved = self.mgdDB.db_route.find_one({
                "is_deleted": False,
                "name": {"$regex": "^" + re.escape(route_name) + "$", "$options": "i"}
            })
            if saved != None:
                result["id"] = str(saved.get("_id"))
            # end if
        # end if
        return result
    # end def

    def update_hub(self, params):
        name = _clip(params.get("name"), 80)
        if name == "":
            return {"status": "ERROR", "desc": "Nama hub wajib diisi"}
        # end if
        existing = self._find_hub_by_name(name)
        if existing == None:
            return {"status": "ERROR", "desc": "Hub tidak ditemukan"}
        # end if
        limits = {
            "province": 80,
            "regency": 80,
            "district": 80,
            "village": 80,
            "postal_code": 10,
            "address": 240
        }
        fields = {}
        for key in limits:
            if key in params:
                fields[key] = _clip(params.get(key), limits[key])
            # end if
        # end for
        new_name = _clip(params.get("new_name"), 80)
        if new_name != "" and new_name.lower() != (existing.get("name") or "").lower():
            taken = self._find_hub_by_name(new_name)
            if taken != None:
                return {"status": "ERROR", "desc": "Hub sudah ada"}
            # end if
            fields["name"] = new_name
        # end if
        postal = fields.get("postal_code", "")
        if postal != "" and ((not postal.isdigit()) or len(postal) != 5):
            return {"status": "ERROR", "desc": "Kode pos tidak valid"}
        # end if
        if len(fields) == 0:
            return {"status": "ERROR", "desc": "Tidak ada detail untuk diubah"}
        # end if
        self.mgdDB.db_hub.update_one(
            {"_id": existing["_id"]},
            {"$set": fields}
        )
        saved = fields.get("name") or existing.get("name") or name
        return {"status": "SUCCESS", "desc": "Hub diperbarui", "name": saved}
    # end def

    def delete_hub(self, hub_id):
        hub_id = (hub_id or "").strip()
        try:
            oid = ObjectId(hub_id)
        except Exception:
            return {"status": "ERROR", "desc": "Hub tidak ditemukan"}
        # end try
        existing = self.mgdDB.db_hub.find_one({"_id": oid, "is_deleted": False})
        if existing == None:
            return {"status": "ERROR", "desc": "Hub tidak ditemukan"}
        # end if
        self.mgdDB.db_hub.update_one(
            {"_id": oid},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Hub dihapus"}
    # end def

    def get_hub(self, hub_id):
        rec = self._hub_by_id(hub_id)
        if rec == None:
            return None
        # end if
        rec["id"] = str(rec.pop("_id"))
        return rec
    # end def

    def hub_cities(self):
        # Saved hubs plus cities cargo is currently parked at.
        names = []
        seen = []
        parked = self.mgdDB.db_shipment.distinct("current_location", {
            "is_deleted": False,
            "status_utama": STATUS_ARRIVED_HUB
        })
        saved = self.list_hubs()
        for name in parked:
            names.append(name)
        # end for
        for hub in saved:
            names.append(hub.get("name", ""))
        # end for
        out = []
        for name in names:
            key = (name or "").strip().lower()
            if key == "" or key in seen:
                continue
            # end if
            seen.append(key)
            out.append(name.strip())
        # end for
        out.sort()
        return out
    # end def

    def hub_shipments(self, hub, destination_city):
        # Transit-hub sorting view: cargo parked at <hub> after arrival,
        # optionally filtered by where it is actually bound (e.g. all goods
        # sitting in Surabaya bound for Malang -> feeder manifest SBY->MLG).
        query = {
            "is_deleted": False,
            "status_utama": STATUS_ARRIVED_HUB,
            "current_location": {"$regex": "^" + re.escape(hub) + "$", "$options": "i"}
        }
        destination_city = (destination_city or "").strip()
        if destination_city != "":
            query["destination_city"] = {
                "$regex": "^" + re.escape(destination_city) + "$", "$options": "i"
            }
        # end if
        recs = list(self.mgdDB.db_shipment.find(query).sort("destination_city", 1).limit(300))
        sproc = shipments_proc()
        out = []
        for rec in recs:
            out.append(sproc._shipment_public(rec))
        # end for
        return out
    # end def

    def ready_for_antar(self, hub, shipment):
        if shipment.get("status_utama") != STATUS_ARRIVED_HUB:
            return False
        # end if
        hub_city = _guess_city(hub).lower()
        dest_city = _guess_city(shipment.get("destination_city") or "").lower()
        if hub_city == "" or dest_city == "":
            return False
        # end if
        return hub_city == dest_city
    # end def

    def generate_delivery_code(self):
        sproc = shipments_proc()
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        return sproc._next_code("ANT", now.strftime("%Y%m%d"))
    # end def

    def open_deliveries(self, hub):
        hub = (hub or "").strip()
        if hub == "":
            return []
        # end if
        recs = list(self.mgdDB.db_delivery.find({
            "is_deleted": False,
            "status": "OPEN",
            "hub_name": {"$regex": "^" + re.escape(hub) + "$", "$options": "i"}
        }).sort("rec_timestamp", -1))
        sproc = shipments_proc()
        fproc = fleet_proc()
        out = []
        for rec in recs:
            rec["id"] = str(rec.pop("_id"))
            code = rec.get("delivery_code", "")
            shipments = sproc.get_shipments_by_ids(rec.get("shipment_ids") or [])
            active = []
            for shipment in shipments:
                if shipment.get("status_utama") != STATUS_OUT_FOR_DELIVERY:
                    continue
                # end if
                if (shipment.get("active_delivery_code") or "") != code:
                    continue
                # end if
                active.append(shipment)
            # end for
            if len(active) == 0:
                continue
            # end if
            rec["shipments"] = active
            vehicle = fproc.get_vehicle(rec.get("vehicle_id", ""))
            driver = fproc.get_driver(rec.get("driver_id", ""))
            rec["vehicle_label"] = ""
            rec["driver_label"] = ""
            if vehicle != None:
                rec["vehicle_label"] = fproc.vehicle_label(vehicle)
            # end if
            if driver != None:
                rec["driver_label"] = driver.get("contact_name", "") + " — SIM " + driver.get("license_number", "")
            # end if
            out.append(rec)
        # end for
        return out
    # end def

    def start_delivery(self, hub, shipment_ids, vehicle_id, driver_id, updated_by):
        hub = (hub or "").strip()
        if hub == "":
            return {"status": "ERROR", "desc": "Pilih hub dulu"}
        # end if
        if not isinstance(shipment_ids, list):
            shipment_ids = []
        # end if
        vehicle_id, driver_id, fleet_err = self._fleet_ids({
            "vehicle_id": vehicle_id,
            "driver_id": driver_id
        })
        if fleet_err != None:
            return fleet_err
        # end if
        sproc = shipments_proc()
        shipments = sproc.get_shipments_by_ids(shipment_ids)
        if len(shipments) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu kiriman"}
        # end if
        ids = []
        for rec in shipments:
            if not self.ready_for_antar(hub, rec):
                return {"status": "ERROR", "desc": "Kiriman ini masih perlu feeder, bukan antar"}
            # end if
            here = (rec.get("current_location") or "").strip().lower()
            if here != hub.lower():
                return {"status": "ERROR", "desc": "Kiriman tidak parkir di hub ini"}
            # end if
            ids.append(rec["id"])
        # end for
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        code = self.generate_delivery_code()
        now_str = sproc.now_str()
        saved = database.new(self.mgdDB, "db_delivery")
        saved.put("delivery_code", code)
        saved.put("hub_name", hub)
        saved.put("vehicle_id", vehicle_id)
        saved.put("driver_id", driver_id)
        saved.put("shipment_ids", ids)
        saved.put("status", "OPEN")
        saved.insert()
        oids = self._to_object_ids(ids)
        self.mgdDB.db_shipment.update_many(
            {"_id": {"$in": oids}, "is_deleted": False},
            {
                "$set": {
                    "status_utama": STATUS_OUT_FOR_DELIVERY,
                    "active_delivery_code": code
                },
                "$push": {
                    "tracking_logs": {
                        "milestone_status": "OUT_FOR_DELIVERY",
                        "location": hub,
                        "notes": "Kurir berangkat dari " + hub + " menuju penerima",
                        "updated_by": updated_by,
                        "timestamp": now_str
                    }
                }
            }
        )
        return {
            "status": "SUCCESS",
            "desc": "Antar " + code + " berangkat — " + str(len(ids)) + " kiriman",
            "delivery_code": code
        }
    # end def

    def _open_delivery(self, code):
        code = (code or "").strip()
        if code == "":
            return None
        # end if
        return self.mgdDB.db_delivery.find_one({
            "delivery_code": code,
            "is_deleted": False,
            "status": "OPEN"
        })
    # end def

    def _shipment_on_run(self, code, shipment_id):
        try:
            oid = ObjectId(shipment_id)
        except Exception:
            return None
        # end try
        return self.mgdDB.db_shipment.find_one({
            "_id": oid,
            "is_deleted": False,
            "active_delivery_code": code,
            "status_utama": STATUS_OUT_FOR_DELIVERY
        })
    # end def

    def _close_delivery_if_done(self, code):
        left = self.mgdDB.db_shipment.count_documents({
            "is_deleted": False,
            "active_delivery_code": code,
            "status_utama": STATUS_OUT_FOR_DELIVERY
        })
        if left > 0:
            return
        # end if
        self.mgdDB.db_delivery.update_one(
            {"delivery_code": code, "is_deleted": False},
            {"$set": {"status": "CLOSED"}}
        )
    # end def

    def deliver_shipment(self, code, shipment_id, received_by, updated_by):
        run = self._open_delivery(code)
        if run == None:
            return {"status": "ERROR", "desc": "Antar tidak ditemukan"}
        # end if
        received_by = _clip(received_by, 80)
        if received_by == "":
            return {"status": "ERROR", "desc": "Nama penerima wajib diisi"}
        # end if
        shipment = self._shipment_on_run(code, shipment_id)
        if shipment == None:
            return {"status": "ERROR", "desc": "Kiriman tidak ada di daftar antar ini"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        sproc = shipments_proc()
        place = shipment.get("destination_city") or run.get("hub_name") or ""
        self.mgdDB.db_shipment.update_one(
            {"_id": shipment["_id"]},
            {
                "$set": {
                    "status_utama": STATUS_DELIVERED,
                    "active_delivery_code": "",
                    "current_location": place
                },
                "$push": {
                    "tracking_logs": {
                        "milestone_status": "DELIVERED",
                        "location": place,
                        "notes": "Diterima oleh " + received_by,
                        "updated_by": updated_by,
                        "timestamp": sproc.now_str()
                    }
                }
            }
        )
        self._close_delivery_if_done(code)
        return {"status": "SUCCESS", "desc": "Kiriman diterima oleh " + received_by}
    # end def

    def fail_delivery(self, code, shipment_id, reason, updated_by):
        run = self._open_delivery(code)
        if run == None:
            return {"status": "ERROR", "desc": "Antar tidak ditemukan"}
        # end if
        reason = _clip(reason, 160)
        if reason == "":
            return {"status": "ERROR", "desc": "Alasan gagal wajib diisi"}
        # end if
        shipment = self._shipment_on_run(code, shipment_id)
        if shipment == None:
            return {"status": "ERROR", "desc": "Kiriman tidak ada di daftar antar ini"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        hub = run.get("hub_name") or shipment.get("current_location") or ""
        sproc = shipments_proc()
        self.mgdDB.db_shipment.update_one(
            {"_id": shipment["_id"]},
            {
                "$set": {
                    "status_utama": STATUS_ARRIVED_HUB,
                    "active_delivery_code": "",
                    "current_location": hub
                },
                "$push": {
                    "tracking_logs": {
                        "milestone_status": "ARRIVED_HUB",
                        "location": hub,
                        "notes": "Antar gagal: " + reason + ". Barang kembali di " + hub,
                        "updated_by": updated_by,
                        "timestamp": sproc.now_str()
                    }
                }
            }
        )
        self._close_delivery_if_done(code)
        return {"status": "SUCCESS", "desc": "Antar gagal. Kiriman kembali di " + hub}
    # end def

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _hub_by_id(self, hub_id):
        hub_id = (hub_id or "").strip()
        try:
            oid = ObjectId(hub_id)
        except Exception:
            return None
        # end try
        return self.mgdDB.db_hub.find_one({"_id": oid, "is_deleted": False})
    # end def

    def _route_row(self, rec):
        rec["id"] = str(rec.pop("_id"))
        names = rec.get("hub_names")
        if not isinstance(names, list) or len(names) == 0:
            names = []
            origin_name = (rec.get("origin_name") or "").strip()
            dest_name = (rec.get("destination_name") or "").strip()
            if origin_name != "":
                names.append(origin_name)
            # end if
            if dest_name != "" and dest_name != origin_name:
                names.append(dest_name)
            # end if
            rec["hub_names"] = names
        # end if
        chain = ""
        for hub_name in names:
            if chain != "":
                chain = chain + " → "
            # end if
            chain = chain + hub_name
        # end for
        title = (rec.get("name") or "").strip()
        rec["name"] = title
        rec["label"] = title if title != "" else chain
        return rec
    # end def

    def _attach_fleet(self, rows):
        fproc = fleet_proc()
        vmap = fproc.get_vehicles_map([row.get("vehicle_id", "") for row in rows])
        dmap = fproc.get_drivers_map([row.get("driver_id", "") for row in rows])
        for row in rows:
            vehicle = vmap.get(row.get("vehicle_id", ""), None)
            driver = dmap.get(row.get("driver_id", ""), None)
            row["vehicle_label"] = ""
            row["driver_label"] = ""
            if vehicle != None:
                row["vehicle_label"] = fproc.vehicle_label(vehicle)
            # end if
            if driver != None:
                row["driver_label"] = driver.get("contact_name", "") + " — SIM " + driver.get("license_number", "")
            # end if
        # end for
        return rows
    # end def

    def _fleet_ids(self, params):
        vehicle_id = (params.get("vehicle_id") or "").strip()
        driver_id = (params.get("driver_id") or "").strip()
        if vehicle_id == "" or driver_id == "":
            return "", "", {"status": "ERROR", "desc": "Pilih armada dan sopir default"}
        # end if
        fproc = fleet_proc()
        if fproc.get_vehicle(vehicle_id) == None:
            return "", "", {"status": "ERROR", "desc": "Kendaraan tidak ditemukan"}
        # end if
        if fproc.get_driver(driver_id) == None:
            return "", "", {"status": "ERROR", "desc": "Sopir tidak ditemukan"}
        # end if
        return vehicle_id, driver_id, None
    # end def

    def list_routes(self):
        recs = list(self.mgdDB.db_route.find({"is_deleted": False}).sort("name", 1))
        out = []
        for rec in recs:
            out.append(self._route_row(rec))
        # end for
        return self._attach_fleet(out)
    # end def

    def get_route(self, route_id):
        route_id = (route_id or "").strip()
        try:
            oid = ObjectId(route_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_route.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        row = self._route_row(rec)
        self._attach_fleet([row])
        return row
    # end def

    def _route_fields(self, params, ignore_id):
        raw = params.get("hub_ids", [])
        if isinstance(raw, str):
            raw = [raw] if raw.strip() != "" else []
        # end if
        if not isinstance(raw, list):
            raw = []
        # end if
        ids = []
        for item in raw:
            hub_id = (item or "").strip()
            if hub_id == "":
                continue
            # end if
            if hub_id in ids:
                return {"status": "ERROR", "desc": "Hub tidak boleh berulang"}
            # end if
            ids.append(hub_id)
        # end for
        if len(ids) < 2:
            return {"status": "ERROR", "desc": "Pilih minimal dua hub"}
        # end if
        names = []
        for hub_id in ids:
            hub = self._hub_by_id(hub_id)
            if hub == None:
                return {"status": "ERROR", "desc": "Hub tidak ditemukan"}
            # end if
            names.append(hub.get("name", ""))
        # end for
        existing = self.mgdDB.db_route.find_one({
            "is_deleted": False,
            "hub_ids": ids
        })
        if existing == None:
            existing = self.mgdDB.db_route.find_one({
                "is_deleted": False,
                "origin_hub_id": ids[0],
                "destination_hub_id": ids[-1],
                "hub_ids": {"$exists": False}
            })
        # end if
        if existing != None and str(existing.get("_id", "")) != ignore_id:
            return {"status": "ERROR", "desc": "Rute sudah ada"}
        # end if
        vehicle_id, driver_id, fleet_err = self._fleet_ids(params)
        if fleet_err != None:
            return fleet_err
        # end if
        route_name = (params.get("name") or "").strip()
        if len(route_name) > 80:
            route_name = route_name[:80]
        # end if
        if route_name == "":
            return {"status": "ERROR", "desc": "Nama rute wajib diisi"}
        # end if
        named = self.mgdDB.db_route.find_one({
            "is_deleted": False,
            "name": {"$regex": "^" + re.escape(route_name) + "$", "$options": "i"}
        })
        if named != None and str(named.get("_id", "")) != ignore_id:
            return {"status": "ERROR", "desc": "Nama rute sudah dipakai"}
        # end if
        return {
            "status": "OK",
            "fields": {
                "name": route_name,
                "hub_ids": ids,
                "hub_names": names,
                "origin_hub_id": ids[0],
                "destination_hub_id": ids[-1],
                "origin_name": names[0],
                "destination_name": names[-1],
                "vehicle_id": vehicle_id,
                "driver_id": driver_id
            }
        }
    # end def

    def create_route(self, params):
        built = self._route_fields(params, "")
        if built.get("status") != "OK":
            return built
        # end if
        fields = built.get("fields", {})
        rec = database.new(self.mgdDB, "db_route")
        rec.put("name", fields.get("name", ""))
        rec.put("hub_ids", fields.get("hub_ids", []))
        rec.put("hub_names", fields.get("hub_names", []))
        rec.put("origin_hub_id", fields.get("origin_hub_id", ""))
        rec.put("destination_hub_id", fields.get("destination_hub_id", ""))
        rec.put("origin_name", fields.get("origin_name", ""))
        rec.put("destination_name", fields.get("destination_name", ""))
        rec.put("vehicle_id", fields.get("vehicle_id", ""))
        rec.put("driver_id", fields.get("driver_id", ""))
        rec.insert()
        return {"status": "SUCCESS", "desc": "Rute dibuat"}
    # end def

    def update_route(self, route_id, params):
        route = self.get_route(route_id)
        if route == None:
            return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
        # end if
        built = self._route_fields(params, route["id"])
        if built.get("status") != "OK":
            return built
        # end if
        self.mgdDB.db_route.update_one(
            {"_id": ObjectId(route["id"])},
            {"$set": built.get("fields", {})}
        )
        return {"status": "SUCCESS", "desc": "Rute diperbarui"}
    # end def

    def delete_route(self, route_id):
        route = self.get_route(route_id)
        if route == None:
            return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
        # end if
        self.mgdDB.db_route.update_one(
            {"_id": ObjectId(route["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Rute dihapus"}
    # end def

    def create_manifest(self, params, updated_by):
        origin = (params.get("origin") or "").strip()
        destination = (params.get("destination") or "").strip()
        route_id = (params.get("route_id") or "").strip()
        route = None
        if route_id != "":
            route = self.get_route(route_id)
            if route == None:
                return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
            # end if
            origin = route.get("origin_name", "")
            destination = route.get("destination_name", "")
        # end if
        vehicle_id = (params.get("vehicle_id") or "").strip()
        driver_id = (params.get("driver_id") or "").strip()
        client_id = (params.get("client_id") or "").strip()
        shipment_ids = params.get("shipment_ids", [])
        if not isinstance(shipment_ids, list):
            shipment_ids = []
        # end if
        if origin == "" or destination == "":
            return {"status": "ERROR", "desc": "Asal dan tujuan wajib diisi"}
        # end if
        if vehicle_id == "" or driver_id == "":
            return {"status": "ERROR", "desc": "Kendaraan dan sopir wajib diisi"}
        # end if
        if len(shipment_ids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu kiriman"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        sproc = shipments_proc()
        shipments = sproc.get_shipments_by_ids(shipment_ids)
        if len(shipments) == 0:
            return {"status": "ERROR", "desc": "Tidak ada kiriman yang valid"}
        # end if
        valid_ids = []
        for rec in shipments:
            valid_ids.append(rec["id"])
        # end for
        manifest_code = self.generate_manifest_code()
        now_str = sproc.now_str()
        rec = database.new(self.mgdDB, "db_manifest")
        rec.put("manifest_code", manifest_code)
        rec.put("vehicle_id", vehicle_id)
        rec.put("driver_id", driver_id)
        rec.put("client_id", client_id)
        hub_names = []
        saved_route_id = ""
        if route != None:
            saved_route_id = route.get("id", "")
            for name in route.get("hub_names") or []:
                text = ""
                if isinstance(name, str):
                    text = name.strip()
                # end if
                if text != "":
                    hub_names.append(text)
                # end if
            # end for
        # end if
        if len(hub_names) < 2:
            hub_names = []
            if origin != "":
                hub_names.append(origin)
            # end if
            if destination != "" and destination != origin:
                hub_names.append(destination)
            # end if
        # end if
        rec.put("origin", origin)
        rec.put("destination", destination)
        rec.put("route_id", saved_route_id)
        rec.put("hub_names", hub_names)
        rec.put("stop_index", 0)
        rec.put("on_road", False)
        rec.put("status", STATUS_PLANNED)
        rec.put("shipment_ids", valid_ids)
        rec.put("last_location", origin)
        rec.put("last_update", now_str)
        rec.insert()
        # Attach every shipment to the manifest + push the consolidation
        # milestone into each tracking_logs array in one update_many().
        oids = self._to_object_ids(valid_ids)
        pushed = self.mgdDB.db_shipment.update_many(
            {"_id": {"$in": oids}, "is_deleted": False},
            {
                "$set": {
                    "status_utama": STATUS_MANIFESTED,
                    "active_manifest_code": manifest_code,
                    "current_location": origin
                },
                "$push": {
                    "tracking_logs": {
                        "milestone_status": "CONSOLIDATED",
                        "location": origin,
                        "notes": "Dikonsolidasi ke manifest " + manifest_code
                                 + " (" + origin + " -> " + destination + ")",
                        "updated_by": updated_by,
                        "timestamp": now_str
                    }
                }
            }
        )
        return {
            "status": "SUCCESS",
            "desc": "Manifest dibuat — " + str(pushed.modified_count) + " kiriman terpasang",
            "manifest_code": manifest_code
        }
    # end def

    def update_manifest_fleet(self, manifest_code, params):
        manifest = self.get_by_code(manifest_code)
        if manifest == None:
            return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
        # end if
        if manifest.get("status") != STATUS_PLANNED:
            return {"status": "ERROR", "desc": "Manifest yang sudah berangkat tidak bisa diubah"}
        # end if
        vehicle_id, driver_id, fleet_err = self._fleet_ids(params)
        if fleet_err != None:
            return fleet_err
        # end if
        client_id = (params.get("client_id") or "").strip()
        self.mgdDB.db_manifest.update_one(
            {"_id": ObjectId(manifest["id"])},
            {"$set": {
                "vehicle_id": vehicle_id,
                "driver_id": driver_id,
                "client_id": client_id
            }}
        )
        return {"status": "SUCCESS", "desc": "Manifest diperbarui"}
    # end def

    def delete_manifest(self, manifest_code):
        manifest = self.get_by_code(manifest_code)
        if manifest == None:
            return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
        # end if
        code = manifest.get("manifest_code", "")
        oids = self._to_object_ids(manifest.get("shipment_ids", []))
        if len(oids) > 0 and code != "":
            # Orders still on this manifest, including ones already marked
            # delivered, go back to Terdaftar. An order that has since been
            # loaded onto a newer manifest is left alone.
            self.mgdDB.db_shipment.update_many(
                {
                    "_id": {"$in": oids},
                    "is_deleted": False,
                    "$or": [
                        {"active_manifest_code": code},
                        {"active_manifest_code": ""},
                        {"active_manifest_code": {"$exists": False}}
                    ]
                },
                [{"$set": {
                    "status_utama": STATUS_REGISTERED,
                    "active_manifest_code": "",
                    "current_location": "$origin_city",
                    "tracking_logs": {
                        "$filter": {
                            "input": {"$ifNull": ["$tracking_logs", []]},
                            "as": "log",
                            "cond": {
                                "$eq": [
                                    {"$indexOfCP": [
                                        {"$toString": {"$ifNull": ["$$log.notes", ""]}},
                                        code
                                    ]},
                                    -1
                                ]
                            }
                        }
                    }
                }}]
            )
        # end if
        self.mgdDB.db_manifest.update_one(
            {"_id": ObjectId(manifest["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Manifest dihapus. Kiriman kembali ke status Terdaftar."}
    # end def

    def _matching_route(self, origin, destination):
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        if origin == "" or destination == "":
            return None
        # end if
        rec = self.mgdDB.db_route.find_one({
            "is_deleted": False,
            "origin_name": {"$regex": "^" + re.escape(origin) + "$", "$options": "i"},
            "destination_name": {"$regex": "^" + re.escape(destination) + "$", "$options": "i"}
        })
        if rec == None:
            return None
        # end if
        return self._route_row(rec)
    # end def

    def _stop_names(self, manifest):
        clean = []
        names = manifest.get("hub_names")
        if isinstance(names, list):
            for name in names:
                text = ""
                if isinstance(name, str):
                    text = name.strip()
                # end if
                if text != "":
                    clean.append(text)
                # end if
            # end for
        # end if
        if len(clean) >= 2:
            return clean
        # end if
        origin = (manifest.get("origin") or "").strip()
        destination = (manifest.get("destination") or "").strip()
        route = self._matching_route(origin, destination)
        if route != None:
            routed = []
            for name in route.get("hub_names") or []:
                text = ""
                if isinstance(name, str):
                    text = name.strip()
                # end if
                if text != "":
                    routed.append(text)
                # end if
            # end for
            if len(routed) >= 2:
                return routed
            # end if
        # end if
        fallback = []
        if origin != "":
            fallback.append(origin)
        # end if
        if destination != "" and destination != origin:
            fallback.append(destination)
        # end if
        if len(fallback) < 2 and origin != "":
            fallback = [origin, destination or origin]
        # end if
        if len(fallback) < 2:
            fallback = ["Asal", "Tujuan"]
        # end if
        return fallback
    # end def

    def _position(self, manifest, stop_count):
        status = (manifest.get("status") or STATUS_PLANNED).strip().upper()
        last = stop_count - 1
        if last < 0:
            last = 0
        # end if
        if status == STATUS_COMPLETED or status == STATUS_ARRIVED:
            return last, False
        # end if
        if status == STATUS_PLANNED:
            return 0, False
        # end if
        raw = manifest.get("stop_index", None)
        if raw == None and manifest.get("on_road", None) == None:
            return 0, True
        # end if
        index = 0
        try:
            index = int(raw or 0)
        except Exception:
            index = 0
        # end try
        if index < 0:
            index = 0
        # end if
        if index > last:
            index = last
        # end if
        on_road = manifest.get("on_road") == True
        if on_road and index >= last:
            on_road = False
        # end if
        return index, on_road
    # end def

    def journey(self, manifest):
        # Stops the truck can sit on, plus the one click that moves it forward.
        names = self._stop_names(manifest)
        index, on_road = self._position(manifest, len(names))
        status = (manifest.get("status") or STATUS_PLANNED).strip().upper()
        done = status == STATUS_COMPLETED
        last = len(names) - 1
        stops = []
        i = 0
        for name in names:
            here = (not on_road) and i == index
            if done and i == last:
                here = True
            # end if
            passed = (i < index) or (done and i < last)
            clickable = (not done) and on_road and i == (index + 1)
            back = (not done) and on_road and i == index
            meta = ""
            cls = "is-later"
            if back:
                cls = "is-back"
                meta = "Kembali"
            elif passed:
                cls = "is-done"
                meta = "Sudah lewat"
            # end if
            if here and done:
                cls = "is-here"
                meta = "Selesai"
            elif here:
                cls = "is-here"
                meta = "Truk di sini"
            elif clickable:
                cls = "is-next"
                meta = "Klik untuk tiba"
            # end if
            stops.append({
                "name": name,
                "cls": cls,
                "show_truck": here,
                "clickable": clickable,
                "back": back,
                "meta": meta
            })
            i += 1
        # end for
        legs = []
        i = 0
        while i < last:
            active = (not done) and on_road and i == index
            passed = done or (index > i)
            clickable = (not done) and (not on_road) and i == index and index < last
            back = (not done) and (not on_road) and index > 0 and i == (index - 1)
            cls = "is-later"
            if back:
                cls = "is-back"
            elif passed:
                cls = "is-done"
            # end if
            if active:
                cls = "is-here"
            # end if
            if clickable:
                cls = "is-next"
            # end if
            legs.append({
                "cls": cls,
                "here": active,
                "clickable": clickable,
                "back": back,
                "target": names[i + 1]
            })
            i += 1
        # end while
        where = "Di " + names[index]
        if done:
            where = "Perjalanan selesai di " + names[index]
        elif on_road and (index + 1) <= last:
            where = "Dalam perjalanan menuju " + names[index + 1]
        # end if
        can_finish = (not done) and (not on_road) and index >= last and status == STATUS_ARRIVED
        return {
            "stops": stops,
            "legs": legs,
            "where": where,
            "can_finish": can_finish,
            "done": done
        }
    # end def

    def _save_progress(self, manifest, names, index, on_road, location):
        sproc = shipments_proc()
        fields = {
            "hub_names": names,
            "stop_index": index,
            "on_road": on_road,
            "last_update": sproc.now_str(),
            "status": STATUS_IN_TRANSIT
        }
        if location != "":
            fields["last_location"] = location
        # end if
        self.mgdDB.db_manifest.update_one(
            {"_id": ObjectId(manifest["id"])},
            {"$set": fields}
        )
    # end def

    def _push_leg(self, manifest, milestone, location, notes, updated_by, set_status):
        sproc = shipments_proc()
        oids = self._to_object_ids(manifest.get("shipment_ids", []))
        if len(oids) == 0:
            return 0
        # end if
        shipment_set = {"current_location": location}
        if set_status != "":
            shipment_set["status_utama"] = set_status
        # end if
        return self.mgdDB.db_shipment.update_many(
            {"_id": {"$in": oids}, "is_deleted": False},
            {
                "$set": shipment_set,
                "$push": {
                    "tracking_logs": {
                        "milestone_status": milestone,
                        "location": location,
                        "notes": notes,
                        "updated_by": updated_by,
                        "timestamp": sproc.now_str()
                    }
                }
            }
        ).modified_count
    # end def

    def advance(self, manifest_code, updated_by):
        # One click moves the truck a single step: leave a hub, or arrive
        # at the next one. The last arrival and the finish still use the
        # normal status update so delivery rules stay the same.
        manifest = self.get_by_code(manifest_code)
        if manifest == None:
            return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
        # end if
        names = self._stop_names(manifest)
        index, on_road = self._position(manifest, len(names))
        status = (manifest.get("status") or STATUS_PLANNED).strip().upper()
        if status == STATUS_COMPLETED:
            return {"status": "ERROR", "desc": "Perjalanan sudah selesai"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        last = len(names) - 1
        code = manifest.get("manifest_code", "")
        if on_road:
            hub = names[index + 1]
            if index + 1 >= last:
                result = self.update_status(
                    manifest_code, STATUS_ARRIVED, hub, "", updated_by
                )
                if result.get("status") == "SUCCESS":
                    result["desc"] = "Truk tiba di " + hub
                # end if
                return result
            # end if
            self._push_leg(
                manifest, "ARRIVED_HUB", hub,
                "Truk manifest " + code + " tiba di " + hub,
                updated_by, ""
            )
            self._save_progress(manifest, names, index + 1, False, hub)
            return {"status": "SUCCESS", "desc": "Truk tiba di " + hub}
        # end if
        if index >= last:
            if status != STATUS_ARRIVED:
                return {"status": "ERROR", "desc": "Truk belum tiba di hub terakhir"}
            # end if
            result = self.update_status(
                manifest_code, STATUS_COMPLETED, names[index], "", updated_by
            )
            if result.get("status") == "SUCCESS":
                result["desc"] = "Perjalanan selesai di " + names[index]
            # end if
            return result
        # end if
        nxt = names[index + 1]
        location = "Menuju " + nxt
        if status == STATUS_PLANNED:
            result = self.update_status(
                manifest_code, STATUS_IN_TRANSIT, location, "", updated_by
            )
            if result.get("status") == "SUCCESS":
                result["desc"] = "Truk berangkat menuju " + nxt
            # end if
            return result
        # end if
        left = names[index]
        self._push_leg(
            manifest, "IN_TRANSIT", location,
            "Berangkat dari " + left + " menuju " + nxt + " via manifest " + code,
            updated_by, STATUS_IN_TRANSIT
        )
        self._save_progress(manifest, names, index, True, location)
        return {"status": "SUCCESS", "desc": "Truk berangkat menuju " + nxt}
    # end def

    def _save_position(self, manifest, names, index, on_road, location, status):
        sproc = shipments_proc()
        fields = {
            "hub_names": names,
            "stop_index": index,
            "on_road": on_road,
            "last_update": sproc.now_str(),
            "status": status,
            "last_location": location
        }
        self.mgdDB.db_manifest.update_one(
            {"_id": ObjectId(manifest["id"])},
            {"$set": fields}
        )
    # end def

    def _rewind_shipments(self, manifest, milestones, shipment_set):
        # Drop the last tracking row only when it is the step being undone.
        oids = self._to_object_ids(manifest.get("shipment_ids", []))
        if len(oids) == 0:
            return
        # end if
        matched = {
            "$in": [
                {"$arrayElemAt": ["$tracking_logs.milestone_status", -1]},
                milestones
            ]
        }
        fields = {
            "tracking_logs": {
                "$cond": [
                    matched,
                    {"$slice": [
                        "$tracking_logs",
                        {"$subtract": [{"$size": "$tracking_logs"}, 1]}
                    ]},
                    "$tracking_logs"
                ]
            }
        }
        for key in shipment_set:
            fields[key] = shipment_set[key]
        # end for
        self.mgdDB.db_shipment.update_many(
            {"_id": {"$in": oids}, "is_deleted": False},
            [{"$set": fields}]
        )
    # end def

    def _road_cargo_location(self, names, index):
        # The first departure leaves cargo at the origin hub. Later
        # departures record the road itself.
        if index <= 0:
            return names[0]
        # end if
        return "Menuju " + names[index + 1]
    # end def

    def retreat(self, manifest_code, updated_by):
        # One click puts the truck back on the previous hub or road and
        # removes the tracking row that step added.
        manifest = self.get_by_code(manifest_code)
        if manifest == None:
            return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
        # end if
        names = self._stop_names(manifest)
        index, on_road = self._position(manifest, len(names))
        status = (manifest.get("status") or STATUS_PLANNED).strip().upper()
        last = len(names) - 1
        code = manifest.get("manifest_code", "")
        if status == STATUS_COMPLETED:
            hub = names[index]
            self._rewind_shipments(manifest, ["DELIVERED", "ARRIVED_HUB"], {
                "status_utama": STATUS_ARRIVED_HUB,
                "active_manifest_code": code,
                "current_location": hub
            })
            self._save_position(manifest, names, index, False, hub, STATUS_ARRIVED)
            return {"status": "SUCCESS", "desc": "Truk kembali di " + hub}
        # end if
        if status == STATUS_PLANNED and (not on_road) and index <= 0:
            return {"status": "ERROR", "desc": "Truk sudah di hub awal"}
        # end if
        if on_road:
            hub = names[index]
            if index <= 0:
                self._rewind_shipments(manifest, ["IN_TRANSIT"], {
                    "status_utama": STATUS_MANIFESTED,
                    "current_location": hub
                })
                self._save_position(manifest, names, 0, False, hub, STATUS_PLANNED)
                return {"status": "SUCCESS", "desc": "Truk kembali di " + hub}
            # end if
            self._rewind_shipments(manifest, ["IN_TRANSIT"], {
                "status_utama": STATUS_IN_TRANSIT,
                "current_location": hub
            })
            self._save_position(manifest, names, index, False, hub, STATUS_IN_TRANSIT)
            return {"status": "SUCCESS", "desc": "Truk kembali di " + hub}
        # end if
        if index <= 0:
            return {"status": "ERROR", "desc": "Truk sudah di hub awal"}
        # end if
        road_index = index - 1
        hub = names[index]
        self._rewind_shipments(manifest, ["ARRIVED_HUB"], {
            "status_utama": STATUS_IN_TRANSIT,
            "current_location": self._road_cargo_location(names, road_index)
        })
        self._save_position(
            manifest, names, road_index, True, "Menuju " + hub, STATUS_IN_TRANSIT
        )
        return {"status": "SUCCESS", "desc": "Truk kembali menuju " + hub}
    # end def

    def update_status(self, manifest_code, new_status, location, notes, updated_by):
        # =================================================================
        # THE BULK TRACKING UPDATE (LTL consolidation core logic):
        # 1. update the manifest document itself
        # 2. ONE update_many() on {_id: {$in: manifest.shipment_ids}} using
        #    $push to append the milestone into every shipment's
        #    tracking_logs array (plus $set of the new status_utama)
        # =================================================================
        manifest = self.get_by_code(manifest_code)
        if manifest == None:
            return {"status": "ERROR", "desc": "Manifest tidak ditemukan"}
        # end if
        new_status = (new_status or "").strip().upper()
        if new_status not in MANIFEST_STATUSES:
            return {"status": "ERROR", "desc": "Status manifest tidak valid"}
        # end if
        current = manifest.get("status", STATUS_PLANNED)
        if STATUS_ORDER[new_status] <= STATUS_ORDER.get(current, 0):
            return {"status": "ERROR", "desc": "Status harus maju (" + current + " -> ...)"}
        # end if
        location = (location or "").strip()
        if location == "":
            location = manifest.get("last_location", manifest.get("origin", ""))
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        sproc = shipments_proc()
        now_str = sproc.now_str()
        origin = manifest.get("origin", "")
        destination = manifest.get("destination", "")
        oids = self._to_object_ids(manifest.get("shipment_ids", []))
        base_filter = {"_id": {"$in": oids}, "is_deleted": False}

        updated_count = 0
        if new_status == STATUS_IN_TRANSIT:
            updated_count = self.mgdDB.db_shipment.update_many(
                base_filter,
                {
                    "$set": {"status_utama": STATUS_IN_TRANSIT},
                    "$push": {
                        "tracking_logs": {
                            "milestone_status": "IN_TRANSIT",
                            "location": location,
                            "notes": "Berangkat dari " + origin + " via manifest "
                                     + manifest_code + " menuju " + destination,
                            "updated_by": updated_by,
                            "timestamp": now_str
                        }
                    }
                }
            ).modified_count
        elif new_status == STATUS_ARRIVED:
            updated_count = self.mgdDB.db_shipment.update_many(
                base_filter,
                {
                    "$set": {
                        "status_utama": STATUS_ARRIVED_HUB,
                        "current_location": location
                    },
                    "$push": {
                        "tracking_logs": {
                            "milestone_status": "ARRIVED_HUB",
                            "location": location,
                            "notes": "Manifest " + manifest_code + " tiba di " + location
                                     + " — kargo diterima untuk sorting",
                            "updated_by": updated_by,
                            "timestamp": now_str
                        }
                    }
                }
            ).modified_count
        elif new_status == STATUS_COMPLETED:
            # The truck is done. Nothing is delivered to a receiver yet.
            # Cargo for this city waits for antar; the rest waits for a feeder.
            dest_regex = re.compile(
                "^" + re.escape(destination) + "$", re.IGNORECASE
            )
            delivered_count = self.mgdDB.db_shipment.update_many(
                {
                    "_id": {"$in": oids},
                    "is_deleted": False,
                    "destination_city": dest_regex
                },
                {
                    "$set": {
                        "status_utama": STATUS_ARRIVED_HUB,
                        "active_manifest_code": "",
                        "current_location": location
                    },
                    "$push": {
                        "tracking_logs": {
                            "milestone_status": "ARRIVED_HUB",
                            "location": location,
                            "notes": "Manifest " + manifest_code + " selesai di " + location
                                     + ". Kiriman siap diantar ke penerima.",
                            "updated_by": updated_by,
                            "timestamp": now_str
                        }
                    }
                }
            ).modified_count
            held_count = self.mgdDB.db_shipment.update_many(
                {
                    "_id": {"$in": oids},
                    "is_deleted": False,
                    "destination_city": {"$not": dest_regex}
                },
                {
                    "$set": {
                        "status_utama": STATUS_ARRIVED_HUB,
                        "active_manifest_code": "",
                        "current_location": location
                    },
                    "$push": {
                        "tracking_logs": {
                            "milestone_status": "ARRIVED_HUB",
                            "location": location,
                            "notes": "Manifest " + manifest_code + " selesai — kargo ditahan di hub "
                                     + location + ", menunggu feeder ke tujuan akhir",
                            "updated_by": updated_by,
                            "timestamp": now_str
                        }
                    }
                }
            ).modified_count
            updated_count = delivered_count + held_count
        # end if

        names = self._stop_names(manifest)
        last_index = 0
        if len(names) > 0:
            last_index = len(names) - 1
        # end if
        on_road = False
        stop_index = last_index
        if new_status == STATUS_IN_TRANSIT:
            on_road = True
            stop_index = 0
        # end if
        self.mgdDB.db_manifest.update_one(
            {"manifest_code": manifest_code},
            {"$set": {
                "status": new_status,
                "last_location": location,
                "last_update": now_str,
                "hub_names": names,
                "stop_index": stop_index,
                "on_road": on_road
            }}
        )
        return {
            "status": "SUCCESS",
            "desc": "Status manifest diperbarui — tracking diubah pada "
                    + str(updated_count) + " kiriman"
        }
    # end def
# end class
