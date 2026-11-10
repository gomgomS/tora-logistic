import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config
from slapz102_stdlib import paginate

from record_log.record_log_proc import record_log_proc
from accounting.accounting_proc import MOVE_TYPES, STATE_DRAFT, move_type_of
from accounting.payments_proc import partner_type_of

# ---------------------------------------------------------------------------
# KONTROL > LOG CATATAN — audit trail of every accounting record: the
# db_record_log entries of the accounting models, each with the record's
# readable name and where it opens.
# ---------------------------------------------------------------------------

# Log model -> label in the filter.
AUDIT_MODELS = {
    "invoice": "Faktur",
    "credit_note": "Nota Kredit",
    "bill": "Tagihan",
    "vendor_refund": "Pengembalian",
    "payment": "Pembayaran",
    "product": "Produk",
    "account": "Akun",
    "tax": "Pajak"
}
DOCUMENT_MODELS = ["invoice", "credit_note", "bill", "vendor_refund"]


class audit_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _ids(self, entries, models):
        oids = []
        for entry in entries:
            if entry["model"] in models and ObjectId.is_valid(entry["record_id"]):
                oids.append(ObjectId(entry["record_id"]))
            # end if
        # end for
        return oids
    # end def

    def _records(self, entries):
        # (model, record_id) -> {"name", "ep", "args"}; one $in query per
        # collection for the whole page.
        out = {}
        oids = self._ids(entries, DOCUMENT_MODELS)
        if len(oids) > 0:
            projection = {"number": 1, "customer_ref": 1, "seq": 1, "move_type": 1, "state": 1}
            for doc in self.mgdDB.db_invoice.find({"_id": {"$in": oids}}, projection):
                meta = move_type_of(doc)
                name = ("Draft " if doc.get("state") == STATE_DRAFT else "") + meta["label"] + " " + doc.get("number", "")
                if doc.get("customer_ref"):
                    name = name + " (" + doc["customer_ref"] + ")"
                # end if
                out[meta["log_model"] + ":" + str(doc["_id"])] = {"name": name, "ep": meta["ep"] + "_edit", "args": {"seq": doc.get("seq")}}
            # end for
        # end if
        oids = self._ids(entries, ["payment"])
        if len(oids) > 0:
            for doc in self.mgdDB.db_payment.find({"_id": {"$in": oids}}, {"number": 1, "seq": 1, "partner_type": 1, "partner_name": 1}):
                pt = partner_type_of(doc)
                out["payment:" + str(doc["_id"])] = {"name": pt["title"] + " " + doc.get("number", "") + " (" + doc.get("partner_name", "") + ")",
                                                     "ep": pt["ep"] + "_edit", "args": {"seq": doc.get("seq")}}
            # end for
        # end if
        oids = self._ids(entries, ["product"])
        if len(oids) > 0:
            for doc in self.mgdDB.db_product.find({"_id": {"$in": oids}}, {"name": 1, "default_code": 1, "seq": 1}):
                code = doc.get("default_code", "")
                out["product:" + str(doc["_id"])] = {"name": "Produk " + ("[" + code + "] " if code else "") + doc.get("name", ""),
                                                     "ep": "client_product_edit", "args": {"seq": doc.get("seq")}}
            # end for
        # end if
        oids = self._ids(entries, ["account"])
        if len(oids) > 0:
            for doc in self.mgdDB.db_account.find({"_id": {"$in": oids}}, {"code": 1, "name": 1}):
                out["account:" + str(doc["_id"])] = {"name": "Akun " + doc.get("code", "") + " " + doc.get("name", ""),
                                                     "ep": "account_edit", "args": {"code": doc.get("code", "")}}
            # end for
        # end if
        oids = self._ids(entries, ["tax"])
        if len(oids) > 0:
            for doc in self.mgdDB.db_tax.find({"_id": {"$in": oids}}, {"code": 1, "name": 1}):
                out["tax:" + str(doc["_id"])] = {"name": "Pajak " + doc.get("name", ""), "ep": "tax_edit", "args": {"code": doc.get("code", "")}}
            # end for
        # end if
        return out
    # end def

    def page_audit(self, model="", q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        models = [model] if model in AUDIT_MODELS else list(AUDIT_MODELS.keys())
        pager = record_log_proc().page_entries(models, q, page, per_page)
        records = self._records(pager["entries"])
        for entry in pager["entries"]:
            record = records.get(entry["model"] + ":" + entry["record_id"])
            entry["record"] = record
            entry["model_label"] = AUDIT_MODELS.get(entry["model"], entry["model"])
        # end for
        return pager
    # end def
# end class
