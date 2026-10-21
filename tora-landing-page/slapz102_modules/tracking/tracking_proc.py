import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# TRACKING MODULE (public) — business logic layer.
#
# Self-contained on purpose: the ERP portal ships an identical copy of this
# proc so both apps can serve /track against the same MongoDB (config
# mainDB must match on both sides) without importing each other's modules.
#
# Search accepts either the tracking_code (AWB-YYYYMMDD-XXXX) or the B2B
# client po_number. The response exposes only customer-safe fields — the
# internal updated_by reference is stripped from every log entry.
# ---------------------------------------------------------------------------


class tracking_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _contact_name(self, contact_id):
        # Refs are stored as 24-hex strings; _id is an ObjectId.
        try:
            oid = ObjectId(contact_id)
        except Exception:
            return ""
        # end try
        contact = self.mgdDB.db_contact.find_one({"_id": oid}, {"name": 1})
        if contact == None:
            return ""
        # end if
        return contact.get("name", "")
    # end def

    def track(self, query):
        query = (query or "").strip()
        if query == "":
            return None
        # end if
        shipment = self.mgdDB.db_shipment.find_one({
            "is_deleted": False,
            "$or": [
                {"tracking_code": query},
                {"po_number": query}
            ]
        })
        if shipment == None:
            return None
        # end if
        sender = self._contact_name(shipment.get("sender_id", ""))
        receiver = self._contact_name(shipment.get("receiver_id", ""))
        logs = []
        for log in sorted(
            shipment.get("tracking_logs", []),
            key=lambda x: x.get("timestamp", "")
        ):
            logs.append({
                "milestone_status": log.get("milestone_status", ""),
                "location": log.get("location", ""),
                "notes": log.get("notes", ""),
                "timestamp": log.get("timestamp", "")
            })
        # end for
        return {
            "tracking_code": shipment.get("tracking_code", ""),
            "po_number": shipment.get("po_number", ""),
            "service_type": shipment.get("service_type", ""),
            "origin_city": shipment.get("origin_city", ""),
            "destination_city": shipment.get("destination_city", ""),
            "status_utama": shipment.get("status_utama", ""),
            "current_location": shipment.get("current_location", ""),
            "sender_name": sender,
            "receiver_name": receiver,
            "created_at": shipment.get("rec_timestamp_str", ""),
            "tracking_logs": logs
        }
    # end def
# end class
