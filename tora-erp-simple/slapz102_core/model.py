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

    "db_code_counter": {
        "counter_key": "",
        "seq": 0
    },

    "db_hub": {
        "name": ""
    },

    "db_route": {
        "name": "",
        "hub_ids": [],
        "hub_names": []
    },

    "db_order": {
        "tracking_code": "",
        "sender_name": "",
        "sender_phone": "",
        "receiver_name": "",
        "receiver_phone": "",
        "receiver_address": "",
        "origin": "",
        "destination": "",
        "route_id": "",
        "hub_names": [],
        "stop_index": 0,
        "on_road": False,
        "status": "REGISTERED",
        "current_location": "",
        "tracking_logs": []
    }
}
