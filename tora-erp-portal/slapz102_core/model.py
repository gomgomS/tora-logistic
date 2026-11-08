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
        "status": "ENABLE",
        # Hak akses per area for role "admin": {"contacts": "full", ...}
        # (level keys in auth_proc.ACCESS_LEVELS; superadmin ignores this)
        "permissions": {},
        "last_login": ""
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
        "category": "CLIENT",
        # Contact form (header + address)
        "street2": "",
        "province": "",
        "postal_code": "",
        "country": "Indonesia",
        "tax_id": "",
        "job_title": "",
        "website": "",
        "tags": "",
        # Sales & Purchase tab
        "salesperson_id": "",
        "sale_payment_term": "",
        "sale_payment_method": "",
        "purchase_payment_term": "",
        "purchase_payment_method": "",
        "fiscal_position": "",
        "reference": "",
        "industry": "",
        # Catatan tab
        "notes": ""
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

    # Akuntansi — customer invoices (and later credit notes via move_type).
    #   seq        running number 1, 2, 3 ... used in the URL
    #              (/accounting/invoices/4), counter "SEQID:invoice"
    #   number     assigned on create from the sequence in Konfigurasi >
    #              Pengaturan (e.g. INV/2026/00004); shown to people
    #   state      DRAFT / POSTED (Terekam) / CANCEL (Batal)
    #   lines      [{product, account, quantity, price_unit, tax,
    #                subtotal, tax_amount}] — amounts recomputed server-side
    #   payments   [{date, amount, method, memo, author_name}] (Bayar)
    #   payment_state  not_paid / partial / paid
    "db_invoice": {
        "move_type": "out_invoice",
        "seq": 0,
        "number": "",
        "state": "DRAFT",
        "partner_id": "",
        "partner_name": "",
        "invoice_date": "",
        "payment_term": "",
        "due_date": "",
        "customer_ref": "",
        "payment_ref": "",
        "salesperson_id": "",
        "delivery_date": "",
        "efaktur_code": "",
        "fiscal_position": "",
        "notes": "",
        "lines": [],
        "amount_untaxed": 0,
        "amount_tax": 0,
        "amount_total": 0,
        "amount_residual": 0,
        "posted_at": "",
        "payments": [],
        "payment_state": "not_paid"
    },

    # Akuntansi > Konfigurasi > Pajak. Lines reference a tax by its code.
    #   amount       percent (12 = 12%)
    #   base         "full" or "dpp_11_12" (PPN on DPP Nilai Lain 11/12)
    #   tax_use      "sale" / "purchase"; scope "" / "goods" / "service"
    "db_tax": {
        "code": "",
        "name": "",
        "description": "",
        "tax_use": "sale",
        "scope": "",
        "amount": 0,
        "base": "full",
        "invoice_label": "",
        "active": True,
        "sequence": 0
    },

    # Activity log shown beside any record form (contacts today, other
    # modules later). One collection for every module:
    #   model      registry key from record_log_proc.LOG_MODELS ("contact")
    #   record_id  str(_id) of the record
    #   kind       CREATE / NOTE / CHANGE
    #   changes    [{"label", "old", "new"}] for CHANGE entries
    "db_record_log": {
        "model": "",
        "record_id": "",
        "kind": "NOTE",
        "body": "",
        "changes": [],
        "author_id": "",
        "author_name": ""
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
