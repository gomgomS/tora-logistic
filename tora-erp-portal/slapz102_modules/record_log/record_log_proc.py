import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import datetime

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# RECORD LOG MODULE — business logic layer.
#
# A per-record activity log (the panel beside a record form):
#   CREATE  "Membuat record baru"            written by the owning module
#   CHANGE  field changes "old -> new"        written by the owning module
#   NOTE    "Log catatan" typed by a user     written via record_log routes
#
#   EVENT   one-line system event ("Kata sandi diubah")
#
# Any module can use it: add one line to LOG_MODELS, then call
#   record_log_proc().log_create(model, record_id, actor)
#   record_log_proc().log_changes(model, record_id, before, after, labels, actor)
#   record_log_proc().log_event(model, record_id, body, actor)
#   record_log_proc().list_groups(model, record_id)
# and render templates/_record_log.html beside the form.
# ---------------------------------------------------------------------------

# model key -> {collection holding the records, access area (auth_proc
# ACCESS_SECTIONS) a user needs "read" on to see the log and add notes}
LOG_MODELS = {
    "contact": {"collection": "db_contact", "area": "contacts"},
    "user": {"collection": "db_user", "area": "users"},
    "invoice": {"collection": "db_invoice", "area": "accounting"}
}

KIND_CREATE = "CREATE"
KIND_NOTE = "NOTE"
KIND_CHANGE = "CHANGE"
KIND_EVENT = "EVENT"

NOTE_MAX = 5000
VALUE_MAX = 120
LIST_LIMIT = 200

MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"
]


def _actor_fields(actor):
    # actor = {"id": ..., "name": ...}; None means the system did it.
    if actor == None:
        return "SYSTEM", "Sistem"
    # end if
    return (actor.get("id") or "SYSTEM"), (actor.get("name") or "Sistem")
# end def


def _short(value):
    text = value
    if text == None:
        text = ""
    # end if
    if not isinstance(text, str):
        text = str(text)
    # end if
    text = text.strip()
    if len(text) > VALUE_MAX:
        text = text[:VALUE_MAX - 1] + "…"
    # end if
    return text
# end def


def _day_label(day, today):
    if day == today:
        return "Hari Ini"
    # end if
    if day == today - datetime.timedelta(days=1):
        return "Kemarin"
    # end if
    return str(day.day) + " " + MONTHS[day.month - 1] + " " + str(day.year)
# end def


class record_log_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def model_area(self, model):
        entry = LOG_MODELS.get(model)
        if entry == None:
            return None
        # end if
        return entry["area"]
    # end def

    def _record_exists(self, model, record_id):
        entry = LOG_MODELS.get(model)
        if entry == None:
            return False
        # end if
        collection = entry["collection"]
        try:
            oid = ObjectId(record_id)
        except Exception:
            return False
        # end try
        found = self.mgdDB[collection].find_one({"_id": oid, "is_deleted": False}, {"_id": 1})
        return found != None
    # end def

    def _write(self, model, record_id, kind, body, changes, actor):
        author_id, author_name = _actor_fields(actor)
        rec = database.new(self.mgdDB, "db_record_log")
        rec.put("model", model)
        rec.put("record_id", record_id)
        rec.put("kind", kind)
        rec.put("body", body)
        rec.put("changes", changes)
        rec.put("author_id", author_id)
        rec.put("author_name", author_name)
        rec.insert()
        return rec.get()
    # end def

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def log_create(self, model, record_id, actor, body="Membuat record baru"):
        if model not in LOG_MODELS:
            return None
        # end if
        return self._write(model, record_id, KIND_CREATE, body, [], actor)
    # end def

    def log_event(self, model, record_id, body, actor):
        # One-line system event, e.g. "Kata sandi diubah" (no values shown).
        if model not in LOG_MODELS:
            return None
        # end if
        return self._write(model, record_id, KIND_EVENT, body, [], actor)
    # end def

    def log_changes(self, model, record_id, before, after, labels, actor):
        # before / after hold display values; labels = {field: "Label"} in
        # the order the changes should be listed. Nothing is written when
        # no tracked field changed.
        if model not in LOG_MODELS:
            return None
        # end if
        changes = []
        for key in labels:
            old = _short(before.get(key, ""))
            new = _short(after.get(key, ""))
            if old != new:
                changes.append({"label": labels[key], "old": old, "new": new})
            # end if
        # end for
        if len(changes) == 0:
            return None
        # end if
        return self._write(model, record_id, KIND_CHANGE, "", changes, actor)
    # end def

    def add_note(self, model, record_id, body, actor):
        body = (body or "").strip()
        if model not in LOG_MODELS:
            return {"status": "ERROR", "desc": "Jenis data tidak dikenal"}
        # end if
        if body == "":
            return {"status": "ERROR", "desc": "Catatan tidak boleh kosong"}
        # end if
        if len(body) > NOTE_MAX:
            return {"status": "ERROR", "desc": "Catatan maksimal " + str(NOTE_MAX) + " karakter"}
        # end if
        if not self._record_exists(model, record_id):
            return {"status": "ERROR", "desc": "Data tidak ditemukan"}
        # end if
        saved = self._write(model, record_id, KIND_NOTE, body, [], actor)
        return {"status": "SUCCESS", "desc": "Catatan ditambahkan", "entry": self._entry_public(saved)}
    # end def

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _entry_public(self, doc):
        stamp = doc.get("rec_timestamp_str", "")
        return {
            "id": str(doc.get("_id", "")),
            "kind": doc.get("kind", KIND_NOTE),
            "body": doc.get("body", ""),
            "changes": doc.get("changes", []),
            "author_name": doc.get("author_name", ""),
            "time": stamp[11:16],
            "day": stamp[:10]
        }
    # end def

    def list_groups(self, model, record_id, limit=LIST_LIMIT):
        # Newest first, grouped by day: [{"label": "Hari Ini", "entries": [...]}]
        if model not in LOG_MODELS or (record_id or "") == "":
            return []
        # end if
        query = {"model": model, "record_id": record_id, "is_deleted": False}
        projection = {
            "kind": 1, "body": 1, "changes": 1, "author_name": 1, "rec_timestamp_str": 1
        }
        recs = self.mgdDB.db_record_log.find(query, projection).sort(
            [("rec_timestamp", -1), ("_id", -1)]
        ).limit(limit)
        today = database._get_current_datetime(hours=config.JKTA_TZ).date()
        groups = []
        current_day = None
        for rec in recs:
            entry = self._entry_public(rec)
            if entry["day"] != current_day:
                current_day = entry["day"]
                try:
                    day = datetime.datetime.strptime(current_day, "%Y-%m-%d").date()
                    label = _day_label(day, today)
                except Exception:
                    label = current_day
                # end try
                groups.append({"label": label, "entries": []})
            # end if
            groups[-1]["entries"].append(entry)
        # end for
        return groups
    # end def
# end class
