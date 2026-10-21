import copy

from bson.objectid import ObjectId

class mongo_model:

    def __init__(self, record, lookup, db_handle):
        self._mongo_record = copy.deepcopy(record)
        self._lookup_record = copy.deepcopy(lookup)
        self._db_handle = db_handle
    # end def

    def put(self, key, value):
        if not (key in self._lookup_record):
            raise ValueError("SETTING_NON_EXISTING_FIELD", key, value)
        # end if
        self._mongo_record[key] = value
    # end def

    def get(self):
        return self._mongo_record
    # end def

    def delete(self, query):
        collection_name = self._lookup_record["__db__name__"]
        self._db_handle[collection_name].delete_many(query)
    # end def

    def insert(self, lock=None):
        collection_name = self._lookup_record["__db__name__"]
        del self._mongo_record["__db__name__"]
        if lock == None:
            self._db_handle[collection_name].insert_one(
                self._mongo_record
            )
        else:
            self._db_handle[collection_name].insert_one(
                self._mongo_record,
                session=lock
            )
        # end if
    # end def

    def update(self, query):
        collection_name = self._lookup_record["__db__name__"]
        self._db_handle[collection_name].update_one(
            query,
            {"$set": self._mongo_record}
        )
    # end def
# end class

# ---------------------------------------------------------------------------
# Database schema registry.
#
# Every collection must be registered here with its full field list before
# the app can use it. `database.new()` / `database.load()` copy one of these
# templates to build a `mongo_model` record, and `mongo_model.put()` only
# accepts keys that exist in the template (unknown fields raise ValueError).
#
# Convention:
#   - collection names start with "db_"
#   - keep an empty default for every field ("" / 0 / [] / {} / False)
#   - framework-managed fields (pkey, ipkey, rec_timestamp,
#     rec_timestamp_str, is_deleted) are added automatically by
#     database.new() — do NOT declare them here
# ---------------------------------------------------------------------------

db = {

    "db_unique_counter": {
        "counter": 0,
    },

    "db_config": {
        "_id": ObjectId(),
        "name": "",
        "value": "",
        "desc": "",
        "config_type": "",
        "misc": "",
        "data": {}
    },

    "db_user": {
        "fk_user_id": "",
        "username": "",
        "password": "",
        "role": "MEMBER",
        "name": "",
        "phone": "",
        "email": "",
        "status": "ENABLE"
    },

    "db_sample_item": {
        "slug": "",
        "title": "",
        "body": "",
        "order": 0,
        "status": "PUBLISHED"
    },

    # -----------------------------------------------------------------------
    # Hybrid Logistics System (Phase 1)
    #
    # Collection  | Spec name   | Notes
    # -------------+-------------+-----------------------------------------
    # db_user     | users       | reused framework collection; "password"
    #             |             | stores the werkzeug hash; role holds
    #             |             | "superadmin" / "admin"
    # db_contact  | contacts    | master clients / receivers / drivers / vendors
    # db_vehicle  | vehicles    | fleet master (internal + vendor units)
    # db_driver   | drivers     | driver master, linked to db_contact
    # db_shipment | shipments   | LTL + FTL orders with embedded tracking_logs
    # db_manifest | manifests   | consolidation units (trunk + feeder legs)
    # db_code_counter | -       | atomic per-day AWB / manifest sequences
    #
    # Cross-document references store the 24-hex str(_id) of the target.
    # created_at is the framework-managed rec_timestamp / rec_timestamp_str.
    # -----------------------------------------------------------------------

    "db_contact": {
        "name": "",
        "company_name": "",
        "phone": "",
        "email": "",
        "address": "",
        "city": "",
        "category": "CLIENT"
    },

    "db_vehicle": {
        "plate_number": "",
        "vehicle_type": "",
        "ownership": "INTERNAL",
        "vendor_name": ""
    },

    "db_driver": {
        "contact_id": "",
        "license_number": "",
        "type": "INTERNAL"
    },

    "db_shipment": {
        "tracking_code": "",
        "po_number": "",
        "service_type": "LTL",
        "sender_id": "",
        "receiver_id": "",
        "origin_city": "",
        "origin_province": "",
        "origin_regency": "",
        "origin_district": "",
        "origin_village": "",
        "origin_postal_code": "",
        "origin_address": "",
        "destination_city": "",
        "destination_province": "",
        "destination_regency": "",
        "destination_district": "",
        "destination_village": "",
        "destination_postal_code": "",
        "destination_address": "",
        "status_utama": "REGISTERED",
        "current_location": "",
        "active_manifest_code": "",
        "active_delivery_code": "",
        "tracking_logs": []
    },

    "db_hub": {
        "name": "",
        "province": "",
        "regency": "",
        "district": "",
        "village": "",
        "postal_code": "",
        "address": "",
        "lat": "",
        "lng": "",
        "place_id": ""
    },

    "db_route": {
        "name": "",
        "origin_hub_id": "",
        "destination_hub_id": "",
        "origin_name": "",
        "destination_name": "",
        "hub_ids": [],
        "hub_names": [],
        "vehicle_id": "",
        "driver_id": ""
    },

    "db_manifest": {
        "manifest_code": "",
        "vehicle_id": "",
        "driver_id": "",
        "client_id": "",
        "origin": "",
        "destination": "",
        "route_id": "",
        "hub_names": [],
        "stop_index": 0,
        "on_road": False,
        "status": "PLANNED",
        "shipment_ids": [],
        "last_location": "",
        "last_update": ""
    },

    "db_code_counter": {
        "counter_key": "",
        "seq": 0
    },

    "db_delivery": {
        "delivery_code": "",
        "hub_name": "",
        "vehicle_id": "",
        "driver_id": "",
        "shipment_ids": [],
        "status": "OPEN"
    }
}
