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

from routes.routes_proc import routes_proc

STATUS_REGISTERED = "REGISTERED"
STATUS_IN_TRANSIT = "IN_TRANSIT"
STATUS_ARRIVED = "ARRIVED"
STATUS_DELIVERED = "DELIVERED"
ORDER_STATUSES = [
    STATUS_REGISTERED, STATUS_IN_TRANSIT, STATUS_ARRIVED, STATUS_DELIVERED
]
STOP_EVENT_LIST = [
    {"code": "BONGKAR_MUAT", "label": "Bongkar muat", "note": "Bongkar muat di "},
    {"code": "ISTIRAHAT", "label": "Istirahat", "note": "Istirahat di "},
    {"code": "TUNGGU_MUATAN", "label": "Tunggu muatan", "note": "Tunggu muatan di "}
]


class orders_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def now_str(self):
        now = database._get_current_datetime(hours=config.JKTA_TZ)
        return now.strftime("%Y-%m-%d %H:%M:%S")
    # end def

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

    def _public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def active_count(self):
        return self.mgdDB.db_order.count_documents({
            "is_deleted": False,
            "status": {"$ne": STATUS_DELIVERED}
        })
    # end def

    def list_orders(self, filters):
        query = {"is_deleted": False}
        status = (filters.get("status") or "").strip().upper()
        if status in ORDER_STATUSES:
            query["status"] = status
        # end if
        q = (filters.get("q") or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"tracking_code": {"$regex": pattern, "$options": "i"}},
                {"sender_name": {"$regex": pattern, "$options": "i"}},
                {"receiver_name": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = list(self.mgdDB.db_order.find(query).sort("rec_timestamp", -1).limit(300))
        out = []
        for rec in recs:
            out.append(self._public(rec))
        # end for
        return out
    # end def

    def get_by_code(self, tracking_code):
        tracking_code = (tracking_code or "").strip()
        if tracking_code == "":
            return None
        # end if
        rec = self.mgdDB.db_order.find_one(
            {"tracking_code": tracking_code, "is_deleted": False}
        )
        if rec == None:
            return None
        # end if
        return self._public(rec)
    # end def

    def _log(self, status, location, notes, updated_by, timestamp="", event="", stop_name=""):
        stamp = timestamp
        if stamp == "":
            stamp = self.now_str()
        # end if
        rec = {
            "milestone_status": status,
            "location": location,
            "notes": notes,
            "updated_by": updated_by,
            "timestamp": stamp
        }
        if event != "":
            rec["event"] = event
            rec["stop_name"] = stop_name or location
        # end if
        return rec
    # end def

    def _event_code(self, log):
        return ((log or {}).get("event") or "").strip().upper()
    # end def

    def _activity_hub(self, log):
        text = ((log or {}).get("stop_name") or "").strip()
        if text == "":
            text = ((log or {}).get("location") or "").strip()
        # end if
        return text
    # end def

    def _event_item(self, code):
        code = (code or "").strip().upper()
        for item in STOP_EVENT_LIST:
            if item["code"] == code:
                return item
            # end if
        # end for
        return None
    # end def

    def _route_logs_only(self, old_logs):
        out = []
        for log in old_logs or []:
            if self._event_code(log) == "":
                out.append(log)
            # end if
        # end for
        return out
    # end def

    def _kept_activities(self, old_logs, names, index):
        allowed = {}
        i = 0
        while i <= index and i < len(names):
            allowed[names[i].lower()] = True
            i = i + 1
        # end while
        kept = []
        for log in old_logs or []:
            if self._event_code(log) == "":
                continue
            # end if
            hub = self._activity_hub(log).lower()
            if hub in allowed:
                kept.append(log)
            # end if
        # end for
        return kept
    # end def

    def _merge_activities(self, route_logs, activities):
        unused = list(activities or [])
        out = []
        for log in route_logs:
            out.append(log)
            loc = (log.get("location") or "").strip()
            if loc == "" or loc.lower().startswith("menuju "):
                continue
            # end if
            leftover = []
            for act in unused:
                if self._activity_hub(act).lower() == loc.lower():
                    out.append(act)
                else:
                    leftover.append(act)
                # end if
            # end for
            unused = leftover
        # end for
        return out
    # end def

    def _stamp_at(self, old_logs, slot, updated_by):
        if isinstance(old_logs, list) and slot < len(old_logs):
            prev = old_logs[slot] or {}
            stamp = prev.get("timestamp") or self.now_str()
            who = prev.get("updated_by") or updated_by
            return stamp, who
        # end if
        return self.now_str(), updated_by
    # end def

    def _rebuild_logs(self, order, names, index, on_road, status, updated_by):
        # Riwayat follows the current hub list, so a sisip mid-trip
        # rewrites "menuju" / "tiba" to the route that is actually next.
        old_logs = order.get("tracking_logs") or []
        route_old = self._route_logs_only(old_logs)
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        last = len(names) - 1
        out = []
        slot = 0
        stamp, who = self._stamp_at(route_old, slot, updated_by)
        out.append(self._log(
            STATUS_REGISTERED, names[0],
            "Order diterima. Kiriman di " + names[0], who, stamp
        ))
        slot = slot + 1
        i = 0
        while i < index:
            nxt = names[i + 1]
            stamp, who = self._stamp_at(route_old, slot, updated_by)
            out.append(self._log(
                STATUS_IN_TRANSIT, "Menuju " + nxt,
                "Berangkat dari " + names[i] + " menuju " + nxt, who, stamp
            ))
            slot = slot + 1
            stamp, who = self._stamp_at(route_old, slot, updated_by)
            arrive_status = STATUS_IN_TRANSIT
            note = "Tiba di " + nxt
            if i + 1 >= last:
                arrive_status = STATUS_ARRIVED
                note = "Tiba di " + nxt
            # end if
            out.append(self._log(arrive_status, nxt, note, who, stamp))
            slot = slot + 1
            i = i + 1
        # end while
        if on_road and index < last:
            nxt = names[index + 1]
            stamp, who = self._stamp_at(route_old, slot, updated_by)
            out.append(self._log(
                STATUS_IN_TRANSIT, "Menuju " + nxt,
                "Berangkat dari " + names[index] + " menuju " + nxt, who, stamp
            ))
            slot = slot + 1
        # end if
        if status == STATUS_DELIVERED:
            stamp, who = self._stamp_at(route_old, slot, updated_by)
            out.append(self._log(
                STATUS_DELIVERED, names[last],
                "Kiriman diserahkan di " + names[last], who, stamp
            ))
        # end if
        return self._merge_activities(
            out, self._kept_activities(old_logs, names, index)
        )
    # end def

    def _location_now(self, names, index, on_road):
        last = len(names) - 1
        if on_road and index < last:
            return "Menuju " + names[index + 1]
        # end if
        if index < 0:
            index = 0
        # end if
        if index > last:
            index = last
        # end if
        return names[index]
    # end def

    def refresh_riwayat(self, tracking_code, updated_by):
        order = self.get_by_code(tracking_code)
        if order == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        names = self._stop_names(order)
        if len(names) < 1:
            return {"status": "ERROR", "desc": "Rute order kosong"}
        # end if
        index, on_road = self._position(order, len(names))
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        here = self._location_now(names, index, on_road)
        fields = {
            "current_location": here,
            "tracking_logs": self._rebuild_logs(
                order, names, index, on_road, status, updated_by
            )
        }
        self._save(order, fields)
        return {"status": "SUCCESS", "desc": "Riwayat disesuaikan dengan rute sekarang"}
    # end def

    def create_order(self, params, updated_by):
        sender_name = (params.get("sender_name") or "").strip()
        receiver_name = (params.get("receiver_name") or "").strip()
        route_id = (params.get("route_id") or "").strip()
        if sender_name == "":
            return {"status": "ERROR", "desc": "Nama pengirim wajib diisi"}
        # end if
        if receiver_name == "":
            return {"status": "ERROR", "desc": "Nama penerima wajib diisi"}
        # end if
        if route_id == "":
            return {"status": "ERROR", "desc": "Pilih rute dulu"}
        # end if
        route = routes_proc().get_route(route_id)
        if route == None:
            return {"status": "ERROR", "desc": "Rute tidak ditemukan"}
        # end if
        names = []
        for name in route.get("hub_names") or []:
            text = (name or "").strip()
            if text != "":
                names.append(text)
            # end if
        # end for
        if len(names) < 2:
            return {"status": "ERROR", "desc": "Rute ini belum punya dua hub"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        origin = names[0]
        destination = names[len(names) - 1]
        code = self.generate_tracking_code()
        rec = database.new(self.mgdDB, "db_order")
        rec.put("tracking_code", code)
        rec.put("sender_name", sender_name)
        rec.put("sender_phone", (params.get("sender_phone") or "").strip())
        rec.put("receiver_name", receiver_name)
        rec.put("receiver_phone", (params.get("receiver_phone") or "").strip())
        rec.put("receiver_address", (params.get("receiver_address") or "").strip())
        rec.put("origin", origin)
        rec.put("destination", destination)
        rec.put("route_id", route_id)
        rec.put("hub_names", names)
        rec.put("stop_index", 0)
        rec.put("on_road", False)
        rec.put("status", STATUS_REGISTERED)
        rec.put("current_location", origin)
        rec.put("tracking_logs", [
            self._log(
                STATUS_REGISTERED, origin,
                "Order diterima. Kiriman di " + origin, updated_by
            )
        ])
        rec.insert()
        return {"status": "SUCCESS", "desc": "Order dibuat", "tracking_code": code}
    # end def

    def delete_order(self, tracking_code):
        current = self.get_by_code(tracking_code)
        if current == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        if current.get("status") != STATUS_REGISTERED:
            return {"status": "ERROR", "desc": "Hanya order terdaftar yang bisa dihapus"}
        # end if
        self.mgdDB.db_order.update_one(
            {"_id": ObjectId(current["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Order dihapus"}
    # end def

    def _stop_names(self, order):
        clean = []
        names = order.get("hub_names")
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
        origin = (order.get("origin") or "").strip() or "Asal"
        destination = (order.get("destination") or "").strip() or "Tujuan"
        if destination == origin:
            destination = origin + " tujuan"
        # end if
        return [origin, destination]
    # end def

    def _position(self, order, stop_count):
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        last = stop_count - 1
        if last < 0:
            last = 0
        # end if
        if status == STATUS_DELIVERED or status == STATUS_ARRIVED:
            return last, False
        # end if
        if status == STATUS_REGISTERED:
            return 0, False
        # end if
        index = 0
        try:
            index = int(order.get("stop_index") or 0)
        except Exception:
            index = 0
        # end try
        if index < 0:
            index = 0
        # end if
        if index > last:
            index = last
        # end if
        on_road = order.get("on_road") == True
        if on_road and index >= last:
            on_road = False
        # end if
        return index, on_road
    # end def

    def journey(self, order):
        names = self._stop_names(order)
        index, on_road = self._position(order, len(names))
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        done = status == STATUS_DELIVERED
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
                "index": i,
                "cls": cls,
                "show_truck": here,
                "clickable": clickable,
                "back": back,
                "can_event": (not done) and (not on_road) and i == index,
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
                "target": names[i + 1],
                "after_index": i
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

    def _save(self, order, fields):
        fields["current_location"] = fields.get("current_location", order.get("current_location", ""))
        self.mgdDB.db_order.update_one(
            {"_id": ObjectId(order["id"])},
            {"$set": fields}
        )
    # end def

    def _push_log(self, order, status, location, notes, updated_by, extra):
        extra["current_location"] = location
        extra["tracking_logs"] = order.get("tracking_logs") or []
        extra["tracking_logs"] = list(extra["tracking_logs"])
        extra["tracking_logs"].append(self._log(status, location, notes, updated_by))
        self._save(order, extra)
    # end def

    def advance(self, tracking_code, updated_by):
        order = self.get_by_code(tracking_code)
        if order == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        names = self._stop_names(order)
        index, on_road = self._position(order, len(names))
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        if status == STATUS_DELIVERED:
            return {"status": "ERROR", "desc": "Perjalanan sudah selesai"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        last = len(names) - 1
        if on_road:
            hub = names[index + 1]
            fields = {
                "hub_names": names,
                "stop_index": index + 1,
                "on_road": False
            }
            if index + 1 >= last:
                fields["status"] = STATUS_ARRIVED
                self._push_log(
                    order, STATUS_ARRIVED, hub,
                    "Tiba di hub terakhir " + hub, updated_by, fields
                )
                return {"status": "SUCCESS", "desc": "Truk tiba di " + hub}
            # end if
            fields["status"] = STATUS_IN_TRANSIT
            self._push_log(
                order, STATUS_IN_TRANSIT, hub,
                "Tiba di " + hub, updated_by, fields
            )
            return {"status": "SUCCESS", "desc": "Truk tiba di " + hub}
        # end if
        if index >= last:
            if status != STATUS_ARRIVED:
                return {"status": "ERROR", "desc": "Truk belum tiba di hub terakhir"}
            # end if
            fields = {
                "hub_names": names,
                "stop_index": index,
                "on_road": False,
                "status": STATUS_DELIVERED
            }
            self._push_log(
                order, STATUS_DELIVERED, names[index],
                "Kiriman diserahkan di " + names[index], updated_by, fields
            )
            return {"status": "SUCCESS", "desc": "Perjalanan selesai di " + names[index]}
        # end if
        nxt = names[index + 1]
        location = "Menuju " + nxt
        fields = {
            "hub_names": names,
            "stop_index": index,
            "on_road": True,
            "status": STATUS_IN_TRANSIT
        }
        left = names[index]
        self._push_log(
            order, STATUS_IN_TRANSIT, location,
            "Berangkat dari " + left + " menuju " + nxt, updated_by, fields
        )
        return {"status": "SUCCESS", "desc": "Truk berangkat menuju " + nxt}
    # end def

    def retreat(self, tracking_code, updated_by):
        order = self.get_by_code(tracking_code)
        if order == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        names = self._stop_names(order)
        index, on_road = self._position(order, len(names))
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        if status == STATUS_REGISTERED and (not on_road) and index == 0:
            return {"status": "ERROR", "desc": "Truk masih di hub pertama"}
        # end if
        fields = {"hub_names": names}
        if status == STATUS_DELIVERED:
            fields["stop_index"] = index
            fields["on_road"] = False
            fields["status"] = STATUS_ARRIVED
            fields["current_location"] = names[index]
            fields["tracking_logs"] = self._rebuild_logs(
                order, names, index, False, STATUS_ARRIVED, updated_by
            )
            self._save(order, fields)
            return {"status": "SUCCESS", "desc": "Kembali ke hub " + names[index]}
        # end if
        if on_road:
            fields["stop_index"] = index
            fields["on_road"] = False
            if index == 0:
                fields["status"] = STATUS_REGISTERED
            else:
                fields["status"] = STATUS_IN_TRANSIT
            # end if
            fields["current_location"] = names[index]
            fields["tracking_logs"] = self._rebuild_logs(
                order, names, index, False, fields["status"], updated_by
            )
            self._save(order, fields)
            return {"status": "SUCCESS", "desc": "Kembali ke " + names[index]}
        # end if
        prev = index - 1
        if prev < 0:
            prev = 0
        # end if
        fields["stop_index"] = prev
        fields["on_road"] = True
        fields["status"] = STATUS_IN_TRANSIT
        fields["current_location"] = "Menuju " + names[index]
        fields["tracking_logs"] = self._rebuild_logs(
            order, names, prev, True, STATUS_IN_TRANSIT, updated_by
        )
        self._save(order, fields)
        return {"status": "SUCCESS", "desc": "Kembali ke jalur menuju " + names[index]}
    # end def

    def add_stop_event(self, tracking_code, stop_index, event_note, updated_by):
        order = self.get_by_code(tracking_code)
        if order == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        if status == STATUS_DELIVERED:
            return {"status": "ERROR", "desc": "Perjalanan sudah selesai"}
        # end if
        note = (event_note or "").strip()
        if note == "":
            return {"status": "ERROR", "desc": "Isi kegiatan dulu, contoh Bongkar muat"}
        # end if
        if len(note) > 120:
            return {"status": "ERROR", "desc": "Kegiatan terlalu panjang"}
        # end if
        names = self._stop_names(order)
        index, on_road = self._position(order, len(names))
        if on_road:
            return {"status": "ERROR", "desc": "Catat kegiatan saat truk berhenti di hub"}
        # end if
        try:
            stop_index = int(stop_index)
        except Exception:
            return {"status": "ERROR", "desc": "Posisi hub tidak valid"}
        # end try
        if stop_index != index:
            return {"status": "ERROR", "desc": "Kegiatan hanya di hub tempat truk berhenti"}
        # end if
        if updated_by == "" or updated_by == None:
            updated_by = "SYSTEM"
        # end if
        hub = names[index]
        item = None
        for ev in STOP_EVENT_LIST:
            if ev["label"].lower() == note.lower():
                item = ev
            # end if
        # end for
        if item != None:
            event = item["code"]
            text = item["note"] + hub
        else:
            event = "ACTIVITY"
            text = note
            if hub.lower() not in text.lower():
                text = text + " di " + hub
            # end if
        # end if
        extra = {
            "hub_names": names,
            "stop_index": index,
            "on_road": False,
            "status": status
        }
        extra["current_location"] = hub
        extra["tracking_logs"] = list(order.get("tracking_logs") or [])
        extra["tracking_logs"].append(self._log(
            status, hub, text, updated_by,
            event=event, stop_name=hub
        ))
        self._save(order, extra)
        return {"status": "SUCCESS", "desc": text}
    # end def

    def insert_hub(self, tracking_code, after_index, hub_name, updated_by):
        order = self.get_by_code(tracking_code)
        if order == None:
            return {"status": "ERROR", "desc": "Order tidak ditemukan"}
        # end if
        status = (order.get("status") or STATUS_REGISTERED).strip().upper()
        if status == STATUS_DELIVERED:
            return {"status": "ERROR", "desc": "Perjalanan sudah selesai"}
        # end if
        hub_name = (hub_name or "").strip()
        if hub_name == "":
            return {"status": "ERROR", "desc": "Nama hub wajib diisi"}
        # end if
        names = self._stop_names(order)
        try:
            after_index = int(after_index)
        except Exception:
            return {"status": "ERROR", "desc": "Posisi sisip tidak valid"}
        # end try
        if after_index < 0 or after_index >= (len(names) - 1):
            return {"status": "ERROR", "desc": "Hub hanya bisa disisip di antara rute yang ada"}
        # end if
        left = names[after_index]
        right = names[after_index + 1]
        key = hub_name.lower()
        if key == left.lower() or key == right.lower():
            return {"status": "ERROR", "desc": "Hub tidak boleh sama dengan yang di sampingnya"}
        # end if
        made = routes_proc().ensure_hub(hub_name)
        if made.get("status") != "SUCCESS":
            return made
        # end if
        saved_name = made["hub"].get("name", hub_name)
        index, on_road = self._position(order, len(names))
        names.insert(after_index + 1, saved_name)
        if after_index < index:
            index = index + 1
        # end if
        last = len(names) - 1
        here = self._location_now(names, index, on_road)
        fields = {
            "hub_names": names,
            "stop_index": index,
            "on_road": on_road,
            "origin": names[0],
            "destination": names[last],
            "current_location": here,
            "tracking_logs": self._rebuild_logs(
                order, names, index, on_road, status, updated_by
            )
        }
        self._save(order, fields)
        return {"status": "SUCCESS", "desc": "Hub " + saved_name + " ditambahkan"}
    # end def
# end class
