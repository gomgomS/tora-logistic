import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import datetime
import re

import pymongo

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config
from slapz102_stdlib import paginate

from contacts.contacts_proc import PAYMENT_METHODS
from record_log.record_log_proc import record_log_proc
from accounting.accounting_proc import accounting_proc, rupiah, short_date, today_iso, move_type_of
from accounting.accounting_proc import MOVE_INVOICE, MOVE_REFUND, MOVE_BILL, MOVE_BILL_REFUND, MOVE_TYPES
from accounting.accounting_proc import STATE_POSTED as INVOICE_POSTED
from accounting.accounting_proc import PAY_PAID, PAY_NOT_PAID, PAYMENT_STATE_LABELS

# ---------------------------------------------------------------------------
# PEMBAYARAN (Pelanggan / Vendor) — business logic (db_payment).
#
# A payment is money received (Terima) or sent (Kirim). Draft -> Lunas
# (Konfirmasi) -> back to Draft (Reset ke Draft), or Draft -> Batal.
# Konfirmasi may settle one Terekam document of the same partner:
#   Pelanggan: Terima -> faktur,   Kirim -> nota kredit (refund)
#   Vendor:    Kirim  -> tagihan,  Terima -> pengembalian vendor
# The settled amount is the smaller of the payment and what is still open;
# Reset ke Draft gives it back. The Bayar dialog on a document creates a
# payment and confirms it in one step (pay_document).
# Customer and vendor payments share everything except PARTNER_TYPES.
# ---------------------------------------------------------------------------

LOG_MODEL = "payment"

STATE_DRAFT = "DRAFT"
STATE_PAID = "PAID"
STATE_CANCEL = "CANCEL"
STATE_LABELS = {STATE_DRAFT: "Draft", STATE_PAID: "Lunas", STATE_CANCEL: "Batal"}

TYPE_INBOUND = "inbound"
TYPE_OUTBOUND = "outbound"
PAYMENT_TYPES = {TYPE_OUTBOUND: "Kirim", TYPE_INBOUND: "Terima"}

# Everything that differs between Pembayaran Pelanggan and Pembayaran
# Vendor: labels, partner side, numbering, endpoints, and which document
# each direction settles. A payment against the usual direction (refund)
# shows negative in the list.
PARTNER_CUSTOMER = "customer"
PARTNER_SUPPLIER = "supplier"
PARTNER_TYPES = {
    PARTNER_CUSTOMER: {
        "partner_type": PARTNER_CUSTOMER, "title": "Pembayaran Pelanggan",
        "partner_label": "Pelanggan", "partner_category": "CLIENT", "partner_placeholder": "Cari klien ...",
        "menu": "Pelanggan", "seq_key": "customer_payment", "seqid_key": "SEQID:payment",
        "ep": "customer_payment", "list_ep": "customer_payments", "slug": "client-payments",
        "default_type": TYPE_INBOUND, "documents": {TYPE_INBOUND: MOVE_INVOICE, TYPE_OUTBOUND: MOVE_REFUND},
        "empty_desc": "Catat uang masuk dari klien, atau klik Bayar di faktur yang sudah Terekam.",
        "memo_placeholder": "contoh: Pelunasan INV/2026/00001"
    },
    PARTNER_SUPPLIER: {
        "partner_type": PARTNER_SUPPLIER, "title": "Pembayaran Vendor",
        "partner_label": "Vendor", "partner_category": "VENDOR", "partner_placeholder": "Cari vendor ...",
        "menu": "Vendor", "seq_key": "vendor_payment", "seqid_key": "SEQID:vendor_payment",
        "ep": "vendor_payment", "list_ep": "vendor_payments", "slug": "vendor-payments",
        "default_type": TYPE_OUTBOUND, "documents": {TYPE_OUTBOUND: MOVE_BILL, TYPE_INBOUND: MOVE_BILL_REFUND},
        "empty_desc": "Catat uang keluar ke vendor, atau klik Bayar di tagihan yang sudah Terekam.",
        "memo_placeholder": "contoh: Pelunasan BILL/2026/11/0001"
    }
}

JOURNALS = [
    {"value": "BNK1", "label": "Bank", "description": "Rekening bank perusahaan"},
    {"value": "CSH1", "label": "Kas", "description": "Kas tunai di kantor"}
]
JOURNAL_LABELS = {}
for _journal in JOURNALS:
    JOURNAL_LABELS[_journal["value"]] = _journal["label"]
# end for

MEMO_MAX = 200
BANK_ACCOUNT_MAX = 80

# Every field the form saves, in log order ("partner_name" label comes
# from PARTNER_TYPES: Pelanggan / Vendor).
LOG_LABELS = {
    "number": "Nomor",
    "payment_type": "Tipe Pembayaran",
    "partner_name": "Pelanggan",
    "amount": "Jumlah",
    "date": "Tanggal",
    "memo": "Memo",
    "journal": "Jurnal",
    "method": "Metode Pembayaran",
    "bank_account": "Akun Bank Perusahaan",
    "invoice_number": "Dokumen"
}


def _parse_amount(value):
    try:
        return round(float(str(value).strip().replace(",", ".")), 2)
    except Exception:
        return None
    # end try
# end def


def partner_type_of(doc):
    # The PARTNER_TYPES entry of a payment (old ones: customer).
    return PARTNER_TYPES.get((doc or {}).get("partner_type") or PARTNER_CUSTOMER, PARTNER_TYPES[PARTNER_CUSTOMER])
# end def


class payments_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        pt = partner_type_of(doc)
        doc["pt"] = pt
        state = doc.get("state", STATE_DRAFT)
        doc["state_label"] = STATE_LABELS.get(state, state)
        doc["state_class"] = {STATE_DRAFT: "draft", STATE_PAID: "settled", STATE_CANCEL: "cancel"}.get(state, "draft")
        doc["type_label"] = PAYMENT_TYPES.get(doc.get("payment_type", ""), "")
        doc["journal_label"] = JOURNAL_LABELS.get(doc.get("journal", ""), doc.get("journal", ""))
        doc["number_display"] = doc.get("number") or "/"
        doc["date_short"] = short_date(doc.get("date", ""))
        sign = 1 if doc.get("payment_type", pt["default_type"]) == pt["default_type"] else -1
        doc["amount_fmt"] = rupiah(doc.get("amount", 0))
        doc["amount_signed_fmt"] = rupiah(sign * (doc.get("amount") or 0))
        doc["applied_fmt"] = rupiah(doc.get("applied", 0))
        doc["unapplied"] = 0
        if doc.get("state") == STATE_PAID and doc.get("invoice_id"):
            doc["unapplied"] = round((doc.get("amount") or 0) - (doc.get("applied") or 0), 2)
        # end if
        doc["unapplied_fmt"] = rupiah(doc["unapplied"])
        return doc
    # end def

    def _query(self, partner_type, state, q):
        query = {"is_deleted": False, "partner_type": partner_type}
        state = (state or "").strip().upper()
        if state in STATE_LABELS:
            query["state"] = state
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"number": {"$regex": pattern, "$options": "i"}},
                {"partner_name": {"$regex": pattern, "$options": "i"}},
                {"memo": {"$regex": pattern, "$options": "i"}},
                {"invoice_number": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def page_payments(self, state, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE, partner_type=PARTNER_CUSTOMER):
        pt = PARTNER_TYPES[partner_type]
        query = self._query(partner_type, state, q)
        projection = {
            "seq": 1, "number": 1, "state": 1, "payment_type": 1, "partner_type": 1, "partner_id": 1,
            "partner_name": 1, "amount": 1, "date": 1, "journal": 1, "memo": 1, "posted_at": 1
        }
        total = self.mgdDB.db_payment.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_payment.find(query, projection).sort(
            [("date", -1), ("rec_timestamp", -1), ("_id", -1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._public(rec))
        # end for
        signed = 0
        if total > 0:
            # Payments against the usual direction (refunds) count negative,
            # like the list rows.
            pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "amount": {"$sum": {
                    "$cond": [{"$eq": ["$payment_type", pt["default_type"]]}, "$amount", {"$multiply": ["$amount", -1]}]
                }}}}
            ]
            for row in self.mgdDB.db_payment.aggregate(pipeline):
                signed = row["amount"]
            # end for
        # end if
        pager["payments"] = out
        pager["sum_amount"] = rupiah(signed)
        return pager
    # end def

    def get_payment(self, payment_id):
        try:
            oid = ObjectId(payment_id)
        except Exception:
            return None
        # end try
        doc = self.mgdDB.db_payment.find_one({"_id": oid, "is_deleted": False})
        if doc == None:
            return None
        # end if
        return self._public(doc)
    # end def

    def get_by_seq(self, seq, partner_type=PARTNER_CUSTOMER):
        doc = self.mgdDB.db_payment.find_one({"seq": seq, "partner_type": partner_type, "is_deleted": False}, {"_id": 1})
        if doc == None:
            return None
        # end if
        return self.get_payment(str(doc["_id"]))
    # end def

    def document_options(self, partner_type=PARTNER_CUSTOMER, partner_id="", limit=300):
        # "Dokumen" picker: Terekam documents of this side that are still
        # open, oldest first. description carries the partner and what is
        # open; partner_id / residual / payment_type let the form prefill.
        pt = PARTNER_TYPES[partner_type]
        doc_types = {}
        for payment_type in pt["documents"]:
            doc_types[pt["documents"][payment_type]] = payment_type
        # end for
        query = {
            "is_deleted": False, "state": INVOICE_POSTED,
            "move_type": {"$in": list(doc_types.keys())}, "amount_residual": {"$gt": 0}
        }
        if partner_id:
            query["partner_id"] = partner_id
        # end if
        projection = {"number": 1, "move_type": 1, "partner_id": 1, "partner_name": 1, "amount_residual": 1, "invoice_date": 1}
        out = []
        for doc in self.mgdDB.db_invoice.find(query, projection).sort([("invoice_date", 1), ("_id", 1)]).limit(limit):
            label = MOVE_TYPES[doc["move_type"]]["label"]
            out.append({
                "value": str(doc["_id"]),
                "label": doc.get("number", ""),
                "description": label + " · " + doc.get("partner_name", "") + " · sisa " + rupiah(doc.get("amount_residual", 0)),
                "partner_id": doc.get("partner_id", ""),
                "partner_name": doc.get("partner_name", ""),
                "residual": doc.get("amount_residual", 0),
                "payment_type": doc_types[doc["move_type"]]
            })
        # end for
        return out
    # end def

    def document_of(self, pay):
        # The document this payment settles (for the link and the
        # "dipakai untuk" line), or None.
        if not pay.get("invoice_id") or not ObjectId.is_valid(pay["invoice_id"]):
            return None
        # end if
        doc = self.mgdDB.db_invoice.find_one(
            {"_id": ObjectId(pay["invoice_id"]), "is_deleted": False},
            {"seq": 1, "number": 1, "move_type": 1, "amount_residual": 1}
        )
        if doc == None or not doc.get("seq"):
            return None
        # end if
        move_type = move_type_of(doc)["move_type"]
        return {
            "id": str(doc["_id"]), "seq": doc["seq"], "number": doc.get("number", ""),
            "move_type": move_type, "label": MOVE_TYPES[move_type]["label"],
            "residual_fmt": rupiah(doc.get("amount_residual", 0))
        }
    # end def

    def preview_number(self, partner_type=PARTNER_CUSTOMER):
        return accounting_proc().preview_number(PARTNER_TYPES[partner_type]["seq_key"])
    # end def

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _next_seq(self, partner_type):
        # Running URL number 1, 2, 3 ... per side (atomic, seeded from the highest).
        seqid_key = PARTNER_TYPES[partner_type]["seqid_key"]
        if self.mgdDB.db_code_counter.find_one({"counter_key": seqid_key}, {"_id": 1}) == None:
            top = self.mgdDB.db_payment.find_one({"seq": {"$gt": 0}, "partner_type": partner_type}, {"seq": 1}, sort=[("seq", -1)])
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": seqid_key}, {"$max": {"seq": (top or {}).get("seq") or 0}}, upsert=True
            )
        # end if
        rec = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": seqid_key}, {"$inc": {"seq": 1}},
            upsert=True, return_document=pymongo.ReturnDocument.AFTER
        )
        return rec["seq"]
    # end def

    def _fields(self, params, partner_type):
        pt = PARTNER_TYPES[partner_type]
        payment_type = (params.get("payment_type") or pt["default_type"]).strip()
        if payment_type not in PAYMENT_TYPES:
            return None, {"status": "ERROR", "desc": "Tipe pembayaran harus Kirim atau Terima"}
        # end if
        partner_id = (params.get("partner_id") or "").strip()
        partner_name = ""
        if partner_id != "":
            if not ObjectId.is_valid(partner_id):
                return None, {"status": "ERROR", "desc": pt["partner_label"] + " tidak valid"}
            # end if
            partner = self.mgdDB.db_contact.find_one({"_id": ObjectId(partner_id), "is_deleted": False}, {"name": 1})
            if partner == None:
                return None, {"status": "ERROR", "desc": pt["partner_label"] + " tidak ditemukan"}
            # end if
            partner_name = partner.get("name", "")
        # end if
        amount = _parse_amount(params.get("amount") or "0")
        if amount == None or amount < 0:
            return None, {"status": "ERROR", "desc": "Jumlah pembayaran tidak valid"}
        # end if
        day = (params.get("date") or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", day) == None:
            day = today_iso()
        # end if
        journal = (params.get("journal") or JOURNALS[0]["value"]).strip()
        if journal not in JOURNAL_LABELS:
            return None, {"status": "ERROR", "desc": "Jurnal tidak valid"}
        # end if
        method = (params.get("method") or PAYMENT_METHODS[0]).strip()
        if method not in PAYMENT_METHODS:
            return None, {"status": "ERROR", "desc": "Metode pembayaran tidak valid"}
        # end if
        invoice_id = (params.get("invoice_id") or "").strip()
        invoice_number = ""
        if invoice_id != "":
            doc = accounting_proc().get_invoice(invoice_id)
            if doc == None:
                return None, {"status": "ERROR", "desc": "Dokumen yang dibayar tidak ditemukan"}
            # end if
            need_type = pt["documents"][payment_type]
            if doc.get("move_type") != need_type:
                need = MOVE_TYPES[need_type]["label"].lower()
                return None, {"status": "ERROR", "desc": "Pembayaran " + PAYMENT_TYPES[payment_type] + " hanya bisa untuk " + need}
            # end if
            if partner_id == "":
                partner_id = doc.get("partner_id", "")
                partner_name = doc.get("partner_name", "")
            # end if
            if doc.get("partner_id") != partner_id:
                return None, {"status": "ERROR", "desc": doc["number"] + " bukan milik " + pt["partner_label"].lower() + " ini"}
            # end if
            invoice_number = doc.get("number", "")
        # end if
        fields = {
            "payment_type": payment_type,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "amount": amount,
            "date": day,
            "memo": (params.get("memo") or "").strip()[:MEMO_MAX],
            "journal": journal,
            "method": method,
            "bank_account": (params.get("bank_account") or "").strip()[:BANK_ACCOUNT_MAX],
            "invoice_id": invoice_id,
            "invoice_number": invoice_number
        }
        return fields, None
    # end def

    def _log_values(self, doc):
        return {
            "number": doc.get("number", ""),
            "payment_type": PAYMENT_TYPES.get(doc.get("payment_type", ""), ""),
            "partner_name": doc.get("partner_name", ""),
            "amount": rupiah(doc.get("amount", 0)),
            "date": short_date(doc.get("date", "")),
            "memo": doc.get("memo", ""),
            "journal": JOURNAL_LABELS.get(doc.get("journal", ""), doc.get("journal", "")),
            "method": doc.get("method", ""),
            "bank_account": doc.get("bank_account", ""),
            "invoice_number": doc.get("invoice_number", "")
        }
    # end def

    def create_payment(self, params, actor=None, partner_type=PARTNER_CUSTOMER):
        pt = PARTNER_TYPES[partner_type]
        fields, err = self._fields(params, partner_type)
        if err != None:
            return err
        # end if
        number = accounting_proc().next_number(pt["seq_key"], _date_or_today(fields["date"]))
        seq = self._next_seq(partner_type)
        rec = database.new(self.mgdDB, "db_payment")
        rec.put("seq", seq)
        rec.put("number", number)
        rec.put("state", STATE_DRAFT)
        rec.put("partner_type", partner_type)
        rec.put("is_sent", False)
        rec.put("applied", 0)
        rec.put("posted_at", "")
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        payment_id = str(rec.get().get("_id", ""))
        record_log_proc().log_create(LOG_MODEL, payment_id, actor, "Pembayaran dibuat")
        return {"status": "SUCCESS", "desc": "Pembayaran " + number + " disimpan", "id": payment_id, "seq": seq, "number": number}
    # end def

    def update_payment(self, payment_id, params, actor=None):
        pay = self.get_payment(payment_id)
        if pay == None:
            return {"status": "ERROR", "desc": "Pembayaran tidak ditemukan"}
        # end if
        if pay.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya pembayaran Draft yang bisa diubah. Reset ke Draft terlebih dulu."}
        # end if
        fields, err = self._fields(params, pay["pt"]["partner_type"])
        if err != None:
            return err
        # end if
        result = self.mgdDB.db_payment.update_one(
            {"_id": ObjectId(pay["id"]), "state": STATE_DRAFT, "is_deleted": False}, {"$set": fields}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Pembayaran sudah tidak Draft, muat ulang halaman"}
        # end if
        labels = dict(LOG_LABELS)
        labels["partner_name"] = pay["pt"]["partner_label"]
        record_log_proc().log_changes(LOG_MODEL, pay["id"], self._log_values(pay), self._log_values(fields), labels, actor)
        return {"status": "SUCCESS", "desc": "Pembayaran disimpan"}
    # end def

    def confirm_payment(self, payment_id, actor=None):
        # Draft -> Lunas. With a Dokumen: settle min(amount, open) on it.
        pay = self.get_payment(payment_id)
        if pay == None:
            return {"status": "ERROR", "desc": "Pembayaran tidak ditemukan"}
        # end if
        if pay.get("state") != STATE_DRAFT:
            return {"status": "ERROR", "desc": "Hanya pembayaran Draft yang bisa dikonfirmasi"}
        # end if
        if pay.get("partner_id", "") == "":
            return {"status": "ERROR", "desc": "Pilih " + pay["pt"]["partner_label"].lower() + " sebelum konfirmasi"}
        # end if
        amount = round(pay.get("amount") or 0, 2)
        if amount <= 0:
            return {"status": "ERROR", "desc": "Jumlah pembayaran harus lebih dari 0"}
        # end if
        acc = accounting_proc()
        doc = None
        if pay.get("invoice_id"):
            doc = acc.get_invoice(pay["invoice_id"])
            if doc == None or doc.get("state") != INVOICE_POSTED:
                return {"status": "ERROR", "desc": "Dokumen " + pay.get("invoice_number", "") + " harus Terekam untuk dibayar"}
            # end if
            if round(doc.get("amount_residual") or 0, 2) <= 0:
                return {"status": "ERROR", "desc": doc["number"] + " sudah lunas, kosongkan Dokumen atau pilih yang lain"}
            # end if
        # end if
        now = database._get_current_datetime(hours=config.JKTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        result = self.mgdDB.db_payment.update_one(
            {"_id": ObjectId(pay["id"]), "state": STATE_DRAFT, "is_deleted": False},
            {"$set": {"state": STATE_PAID, "posted_at": now}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Pembayaran sudah dikonfirmasi"}
        # end if
        log = record_log_proc()
        applied = 0
        if doc != None:
            applied = round(min(amount, doc.get("amount_residual") or 0), 2)
            entry = {
                "date": pay.get("date", ""), "amount": applied, "method": pay.get("method", ""),
                "memo": pay.get("memo", "") or pay["number"], "author_name": (actor or {}).get("name") or "Sistem",
                "payment_id": pay["id"], "payment_number": pay["number"], "payment_seq": pay.get("seq"),
                "payment_ep": pay["pt"]["ep"]
            }
            if not acc.settle(doc["id"], applied, entry):
                self.mgdDB.db_payment.update_one({"_id": ObjectId(pay["id"])}, {"$set": {"state": STATE_DRAFT, "posted_at": ""}})
                return {"status": "ERROR", "desc": "Sisa " + doc["number"] + " sudah berubah, muat ulang halaman"}
            # end if
            self.mgdDB.db_payment.update_one({"_id": ObjectId(pay["id"])}, {"$set": {"applied": applied}})
            self._log_document(doc, applied, pay, actor, True)
        # end if
        log.log_changes(LOG_MODEL, pay["id"], {"state": STATE_LABELS[STATE_DRAFT]}, {"state": STATE_LABELS[STATE_PAID]}, {"state": "Status"}, actor)
        desc = "Pembayaran " + pay["number"] + " dikonfirmasi"
        if doc != None:
            desc = desc + " — " + rupiah(applied) + " dipakai untuk " + doc["number"]
            if applied < amount:
                desc = desc + "; sisa " + rupiah(round(amount - applied, 2)) + " belum terpakai"
            # end if
        # end if
        return {"status": "SUCCESS", "desc": desc}
    # end def

    def _log_document(self, doc, amount, pay, actor, paid):
        # Matching history on the document side.
        model = move_type_of(doc)["log_model"]
        fresh = self.mgdDB.db_invoice.find_one({"_id": ObjectId(doc["id"])}, {"amount_residual": 1, "payment_state": 1})
        if paid:
            verb = " diterima (" if pay.get("payment_type") == TYPE_INBOUND else " dibayarkan ("
            body = "Pembayaran " + rupiah(amount) + verb + pay["number"] + ", " + pay.get("method", "") + ")"
        else:
            body = "Pembayaran " + pay["number"] + " dibatalkan, " + rupiah(amount) + " dikembalikan ke sisa tagihan"
        # end if
        log = record_log_proc()
        log.log_event(model, doc["id"], body, actor)
        log.log_changes(
            model, doc["id"],
            {"residual": rupiah(doc.get("amount_residual", 0)), "pay": PAYMENT_STATE_LABELS.get(doc.get("payment_state") or PAY_NOT_PAID)},
            {"residual": rupiah(fresh.get("amount_residual", 0)), "pay": PAYMENT_STATE_LABELS.get(fresh.get("payment_state") or PAY_NOT_PAID)},
            {"residual": "Jumlah Belum Dibayar", "pay": "Status Pembayaran"}, actor
        )
    # end def

    def reset_payment(self, payment_id, actor=None):
        # Lunas / Batal -> Draft. Whatever this payment settled goes back
        # to the document's open amount.
        pay = self.get_payment(payment_id)
        if pay == None:
            return {"status": "ERROR", "desc": "Pembayaran tidak ditemukan"}
        # end if
        result = self.mgdDB.db_payment.update_one(
            {"_id": ObjectId(pay["id"]), "state": {"$in": [STATE_PAID, STATE_CANCEL]}, "is_deleted": False},
            {"$set": {"state": STATE_DRAFT, "applied": 0, "is_sent": False}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Pembayaran ini sudah Draft"}
        # end if
        if pay.get("invoice_id") and (pay.get("applied") or 0) > 0:
            acc = accounting_proc()
            doc = acc.get_invoice(pay["invoice_id"])
            given = acc.unsettle(pay["invoice_id"], pay["id"])
            if doc != None and given > 0:
                self._log_document(doc, given, pay, actor, False)
            # end if
        # end if
        record_log_proc().log_changes(LOG_MODEL, pay["id"], {"state": pay["state_label"]}, {"state": STATE_LABELS[STATE_DRAFT]}, {"state": "Status"}, actor)
        return {"status": "SUCCESS", "desc": "Pembayaran " + pay["number"] + " dikembalikan ke Draft"}
    # end def

    def cancel_payment(self, payment_id, actor=None):
        pay = self.get_payment(payment_id)
        if pay == None:
            return {"status": "ERROR", "desc": "Pembayaran tidak ditemukan"}
        # end if
        result = self.mgdDB.db_payment.update_one(
            {"_id": ObjectId(pay["id"]), "state": STATE_DRAFT, "is_deleted": False}, {"$set": {"state": STATE_CANCEL}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Hanya pembayaran Draft yang bisa dibatalkan"}
        # end if
        record_log_proc().log_changes(LOG_MODEL, pay["id"], {"state": pay["state_label"]}, {"state": STATE_LABELS[STATE_CANCEL]}, {"state": "Status"}, actor)
        return {"status": "SUCCESS", "desc": "Pembayaran " + pay["number"] + " dibatalkan"}
    # end def

    def mark_sent(self, payment_id, actor=None):
        pay = self.get_payment(payment_id)
        if pay == None:
            return {"status": "ERROR", "desc": "Pembayaran tidak ditemukan"}
        # end if
        result = self.mgdDB.db_payment.update_one(
            {"_id": ObjectId(pay["id"]), "state": STATE_PAID, "is_sent": {"$ne": True}, "is_deleted": False},
            {"$set": {"is_sent": True}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Hanya pembayaran Lunas yang belum terkirim yang bisa ditandai"}
        # end if
        record_log_proc().log_event(LOG_MODEL, pay["id"], "Ditandai sebagai terkirim", actor)
        return {"status": "SUCCESS", "desc": "Pembayaran " + pay["number"] + " ditandai sebagai terkirim"}
    # end def

    def pay_document(self, doc_id, params, actor=None):
        # Bayar dialog on a Terekam document: create the payment on the
        # document's side and confirm it right away. Never more than what is
        # still open.
        acc = accounting_proc()
        doc = acc.get_invoice(doc_id)
        if doc == None:
            return {"status": "ERROR", "desc": "Dokumen tidak ditemukan"}
        # end if
        meta = doc["doc"]
        label = meta["label"]
        if doc.get("state") != INVOICE_POSTED:
            return {"status": "ERROR", "desc": "Hanya " + label.lower() + " Terekam yang bisa dibayar"}
        # end if
        residual = round(doc.get("amount_residual") or 0, 2)
        if residual <= 0:
            return {"status": "ERROR", "desc": label + " ini sudah lunas"}
        # end if
        amount = _parse_amount(params.get("amount") or "")
        if amount == None or amount <= 0:
            return {"status": "ERROR", "desc": "Jumlah pembayaran harus lebih dari 0"}
        # end if
        if amount > residual:
            return {"status": "ERROR", "desc": "Jumlah pembayaran melebihi sisa tagihan " + rupiah(residual)}
        # end if
        method = (params.get("method") or "").strip()
        journal = JOURNALS[1]["value"] if method == "Tunai" else JOURNALS[0]["value"]
        created = self.create_payment({
            "payment_type": meta["payment_type"], "partner_id": doc.get("partner_id", ""), "amount": str(amount),
            "date": params.get("date") or "", "memo": (params.get("memo") or "").strip() or doc["number"],
            "journal": journal, "method": method, "bank_account": "", "invoice_id": doc["id"]
        }, actor, meta["partner_type"])
        if created.get("status") != "SUCCESS":
            return created
        # end if
        result = self.confirm_payment(created["id"], actor)
        if result.get("status") != "SUCCESS":
            return result
        # end if
        fresh = self.mgdDB.db_invoice.find_one({"_id": ObjectId(doc["id"])}, {"payment_state": 1})
        desc = "Pembayaran " + rupiah(amount) + " dicatat (" + created["number"] + ")"
        if fresh.get("payment_state") == PAY_PAID:
            desc = desc + " — " + label.lower() + " lunas"
        # end if
        return {"status": "SUCCESS", "desc": desc, "seq": created["seq"]}
    # end def

    def delete_payments(self, payment_ids, partner_type=PARTNER_CUSTOMER):
        # Only payments that were never confirmed can be deleted.
        oids = []
        for pid in payment_ids:
            if ObjectId.is_valid(pid):
                oids.append(ObjectId(pid))
            # end if
        # end for
        if len(oids) == 0:
            return {"status": "ERROR", "desc": "Pilih minimal satu pembayaran"}
        # end if
        result = self.mgdDB.db_payment.update_many(
            {"_id": {"$in": oids}, "is_deleted": False, "posted_at": "", "partner_type": partner_type,
             "state": {"$in": [STATE_DRAFT, STATE_CANCEL]}},
            {"$set": {"is_deleted": True}}
        )
        skipped = len(oids) - result.modified_count
        desc = str(result.modified_count) + " pembayaran dihapus"
        if skipped > 0:
            desc = desc + "; " + str(skipped) + " yang pernah dikonfirmasi tidak bisa dihapus (reset lalu batalkan saja)"
        # end if
        return {"status": "SUCCESS", "desc": desc}
    # end def
# end class


def _date_or_today(value):
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return datetime.datetime.strptime(today_iso(), "%Y-%m-%d").date()
    # end try
# end def
