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
from slapz102_stdlib import paginate

from record_log.record_log_proc import record_log_proc

# ---------------------------------------------------------------------------
# CONTACTS MODULE — business logic layer.
#
# Master contact records (CLIENT / RECEIVER / DRIVER / VENDOR) plus the
# regex search backing the Select2 autocomplete dropdowns used across order
# entry and fleet assignment.
# ---------------------------------------------------------------------------

CATEGORIES = ["CLIENT", "RECEIVER", "DRIVER", "VENDOR"]

# Sales & Purchase tab choices ("" = not set)
PAYMENT_TERMS = ["Langsung", "7 Hari", "15 Hari", "30 Hari", "45 Hari", "60 Hari"]
PAYMENT_METHODS = ["Transfer Bank", "Tunai", "Giro", "Cek", "Kartu Kredit"]
FISCAL_POSITIONS = ["PKP", "Non-PKP", "Bebas Pajak"]
INDUSTRIES = [
    "Logistik & Transportasi", "Manufaktur", "Perdagangan / Retail",
    "Distribusi", "Konstruksi", "Pertanian", "Pertambangan",
    "Makanan & Minuman", "Jasa", "Pemerintahan"
]

# Free-text fields saved as-is (trimmed) from the contact form.
TEXT_FIELDS = [
    "company_name", "phone", "email", "address", "street2", "city",
    "province", "postal_code", "country", "tax_id", "job_title", "website",
    "tags", "reference", "industry", "notes"
]
NOTES_MAX = 5000

CATEGORY_LABELS = {"CLIENT": "Klien", "RECEIVER": "Penerima", "DRIVER": "Sopir", "VENDOR": "Vendor"}

# Fields tracked in the activity log, in display order.
LOG_LABELS = {
    "name": "Nama",
    "company_name": "Perusahaan",
    "email": "Email",
    "phone": "Telepon",
    "category": "Kategori",
    "address": "Jalan",
    "street2": "Tambahan nama jalan",
    "city": "Kota",
    "province": "Provinsi",
    "postal_code": "Kode Pos",
    "country": "Negara",
    "tax_id": "NPWP/NIK",
    "job_title": "Jabatan Kerja",
    "website": "Website",
    "tags": "Label",
    "salesperson_id": "Penjual",
    "sale_payment_term": "Termin Pembayaran (Penjualan)",
    "sale_payment_method": "Metode Pembayaran (Penjualan)",
    "purchase_payment_term": "Termin Pembayaran (Pembelian)",
    "purchase_payment_method": "Metode Pembayaran (Pembelian)",
    "fiscal_position": "Posisi Fiskal",
    "reference": "Referensi",
    "industry": "Industri",
    "notes": "Catatan"
}
LOG_MODEL = "contact"


class contacts_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _contact_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def _result_text(self, name, company_name, city):
        text = name
        if company_name != "":
            text = text + " — " + company_name
        # end if
        if city != "":
            text = text + " (" + city + ")"
        # end if
        return text
    # end def

    def search_contacts(self, category, q, limit=20):
        # Select2 source: regex search over name OR company_name, optionally
        # restricted to one category. Returns the Select2 "results" payload.
        query = {"is_deleted": False}
        category = (category or "").strip().upper()
        if category in CATEGORIES:
            query["category"] = category
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = ".*" + re.escape(q) + ".*"
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"company_name": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        recs = self.mgdDB.db_contact.find(query).sort("name", 1).limit(limit)
        results = []
        for rec in recs:
            text = self._result_text(
                rec.get("name", ""),
                rec.get("company_name", ""),
                rec.get("city", "")
            )
            # value / label / description feed the _combobox.html picker.
            description = " · ".join([part for part in [rec.get("company_name", ""), rec.get("city", "")] if part])
            results.append({
                "id": str(rec["_id"]),
                "text": text,
                "value": str(rec["_id"]),
                "label": rec.get("name", ""),
                "description": description,
                "name": rec.get("name", ""),
                "company_name": rec.get("company_name", ""),
                "city": rec.get("city", ""),
                "category": rec.get("category", "")
            })
        # end for
        return {"results": results, "pagination": {"more": False}}
    # end def

    def _list_query(self, category, q):
        query = {"is_deleted": False}
        category = (category or "").strip().upper()
        if category in CATEGORIES:
            query["category"] = category
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"company_name": {"$regex": pattern, "$options": "i"}},
                {"email": {"$regex": pattern, "$options": "i"}},
                {"phone": {"$regex": pattern, "$options": "i"}},
                {"city": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def list_contacts(self, category, q=""):
        query = self._list_query(category, q)
        recs = self.mgdDB.db_contact.find(query).sort("name", 1)
        out = []
        for rec in recs:
            out.append(self._contact_public(rec))
        # end for
        return out
    # end def

    def page_contacts(self, category, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        # One page of the list view. MongoDB returns only this page's rows;
        # _id breaks ties so rows never repeat or vanish between pages.
        query = self._list_query(category, q)
        projection = {
            "name": 1, "company_name": 1, "email": 1, "phone": 1,
            "address": 1, "city": 1, "category": 1, "rec_timestamp_str": 1
        }
        total = self.mgdDB.db_contact.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_contact.find(query, projection).sort(
            [("name", 1), ("_id", 1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._contact_public(rec))
        # end for
        pager["contacts"] = out
        return pager
    # end def

    def get_contact(self, contact_id):
        try:
            oid = ObjectId(contact_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_contact.find_one(
            {"_id": oid, "is_deleted": False}
        )
        if rec == None:
            return None
        # end if
        return self._contact_public(rec)
    # end def

    def get_contacts_map(self, contact_ids):
        # {str(_id): contact doc} for resolving sender/receiver/driver refs.
        oids = []
        for cid in contact_ids:
            if cid == "" or cid == None:
                continue
            # end if
            try:
                oids.append(ObjectId(cid))
            except Exception:
                pass
            # end try
        # end for
        out = {}
        if len(oids) == 0:
            return out
        # end if
        recs = self.mgdDB.db_contact.find({"_id": {"$in": oids}})
        for rec in recs:
            key = str(rec["_id"])
            out[key] = self._contact_public(rec)
        # end for
        return out
    # end def

    def _contact_fields(self, params):
        # Shared by create and update: (fields, err). Callers that send only
        # a few fields (order-entry quick create) get "" for the rest.
        name = (params.get("name") or "").strip()
        category = (params.get("category") or "").strip().upper()
        if name == "":
            return None, {"status": "ERROR", "desc": "Nama kontak wajib diisi"}
        # end if
        if category not in CATEGORIES:
            return None, {"status": "ERROR", "desc": "Kategori harus Klien, Penerima, Sopir, atau Vendor"}
        # end if
        fields = {"name": name, "category": category}
        for key in TEXT_FIELDS:
            fields[key] = (params.get(key) or "").strip()
        # end for
        if fields["country"] == "":
            fields["country"] = "Indonesia"
        # end if
        postal = fields["postal_code"]
        if postal != "" and ((not postal.isdigit()) or len(postal) != 5):
            return None, {"status": "ERROR", "desc": "Kode pos harus 5 angka"}
        # end if
        if len(fields["notes"]) > NOTES_MAX:
            return None, {"status": "ERROR", "desc": "Catatan maksimal " + str(NOTES_MAX) + " karakter"}
        # end if
        choices = [
            ("sale_payment_term", PAYMENT_TERMS, "Termin pembayaran penjualan"),
            ("sale_payment_method", PAYMENT_METHODS, "Metode pembayaran penjualan"),
            ("purchase_payment_term", PAYMENT_TERMS, "Termin pembayaran pembelian"),
            ("purchase_payment_method", PAYMENT_METHODS, "Metode pembayaran pembelian"),
            ("fiscal_position", FISCAL_POSITIONS, "Posisi fiskal")
        ]
        for key, allowed, label in choices:
            value = (params.get(key) or "").strip()
            if value != "" and value not in allowed:
                return None, {"status": "ERROR", "desc": label + " tidak valid"}
            # end if
            fields[key] = value
        # end for
        salesperson_id = (params.get("salesperson_id") or "").strip()
        if salesperson_id != "":
            try:
                oid = ObjectId(salesperson_id)
            except Exception:
                return None, {"status": "ERROR", "desc": "Penjual tidak valid"}
            # end try
            found = self.mgdDB.db_user.find_one({"_id": oid, "is_deleted": False}, {"_id": 1})
            if found == None:
                return None, {"status": "ERROR", "desc": "Penjual tidak ditemukan"}
            # end if
        # end if
        fields["salesperson_id"] = salesperson_id
        return fields, None
    # end def

    def related_contacts(self, contact, limit=20):
        # Kontak tab: people at the same company as this contact, plus
        # contacts whose company is this contact (when it is a company).
        names = []
        if contact.get("company_name", "") != "":
            names.append(contact["company_name"])
        # end if
        if contact.get("name", "") != "" and contact["name"] not in names:
            names.append(contact["name"])
        # end if
        if len(names) == 0:
            return []
        # end if
        query = {
            "is_deleted": False,
            "company_name": {"$in": names},
            "_id": {"$ne": ObjectId(contact["id"])}
        }
        projection = {"name": 1, "job_title": 1, "email": 1, "phone": 1, "category": 1}
        recs = self.mgdDB.db_contact.find(query, projection).sort([("name", 1), ("_id", 1)]).limit(limit)
        out = []
        for rec in recs:
            out.append(self._contact_public(rec))
        # end for
        return out
    # end def

    def _log_display(self, before, after):
        # Values as people read them: category label, salesperson name.
        old = {}
        new = {}
        for key in LOG_LABELS:
            old[key] = before.get(key, "") or ""
            new[key] = after.get(key, "") or ""
        # end for
        old["category"] = CATEGORY_LABELS.get(old["category"], old["category"])
        new["category"] = CATEGORY_LABELS.get(new["category"], new["category"])
        if old["salesperson_id"] != new["salesperson_id"]:
            oids = []
            for value in [old["salesperson_id"], new["salesperson_id"]]:
                try:
                    oids.append(ObjectId(value))
                except Exception:
                    pass
                # end try
            # end for
            names = {}
            if len(oids) > 0:
                for user in self.mgdDB.db_user.find({"_id": {"$in": oids}}, {"username": 1, "name": 1}):
                    names[str(user["_id"])] = user.get("name") or user.get("username", "")
                # end for
            # end if
            old["salesperson_id"] = names.get(old["salesperson_id"], old["salesperson_id"])
            new["salesperson_id"] = names.get(new["salesperson_id"], new["salesperson_id"])
        # end if
        return old, new
    # end def

    def create_contact(self, params, actor=None):
        fields, err = self._contact_fields(params)
        if err != None:
            return err
        # end if
        rec = database.new(self.mgdDB, "db_contact")
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        saved = rec.get()
        record_log_proc().log_create(LOG_MODEL, str(saved.get("_id", "")), actor)
        saved_name = saved.get("name", "")
        return {
            "status": "SUCCESS",
            "desc": "Kontak dibuat",
            "id": str(saved.get("_id", "")),
            "name": saved_name,
            "text": self._result_text(
                saved_name,
                saved.get("company_name", ""),
                saved.get("city", "")
            )
        }
    # end def

    def update_contact(self, contact_id, params, actor=None):
        contact = self.get_contact(contact_id)
        if contact == None:
            return {"status": "ERROR", "desc": "Kontak tidak ditemukan"}
        # end if
        fields, err = self._contact_fields(params)
        if err != None:
            return err
        # end if
        self.mgdDB.db_contact.update_one(
            {"_id": ObjectId(contact["id"])},
            {"$set": fields}
        )
        old, new = self._log_display(contact, fields)
        record_log_proc().log_changes(LOG_MODEL, contact["id"], old, new, LOG_LABELS, actor)
        return {"status": "SUCCESS", "desc": "Kontak diperbarui"}
    # end def

    def delete_contact(self, contact_id):
        contact = self.get_contact(contact_id)
        if contact == None:
            return {"status": "ERROR", "desc": "Kontak tidak ditemukan"}
        # end if
        self.mgdDB.db_contact.update_one(
            {"_id": ObjectId(contact["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Kontak dihapus"}
    # end def

    def delete_contacts(self, contact_ids):
        # Bulk soft delete for the list view selection: one update_many.
        oids = []
        for cid in contact_ids:
            try:
                oids.append(ObjectId(cid))
            except Exception:
                pass
            # end try
        # end for
        if len(oids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu kontak"}
        # end if
        result = self.mgdDB.db_contact.update_many(
            {"_id": {"$in": oids}, "is_deleted": False},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": str(result.modified_count) + " kontak dihapus"}
    # end def
# end class
