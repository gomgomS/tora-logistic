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
from slapz102_stdlib import paginate

from record_log.record_log_proc import record_log_proc
from accounting.accounting_proc import accounting_proc, rupiah, tax_rate

# ---------------------------------------------------------------------------
# PRODUK — business logic (db_product).
#
# One catalogue for both sides: Pelanggan > Produk lists products that can
# be sold (sale_ok), Vendor > Produk products that can be bought
# (purchase_ok). The same product opens under either route.
# ---------------------------------------------------------------------------

LOG_MODEL = "product"
SEQID_KEY = "SEQID:product"

PRODUCT_TYPES = {"goods": "Barang", "service": "Layanan", "combo": "Kombo"}
PRODUCT_FILTERS = {"sale": "Penjualan", "purchase": "Pembelian"}
FILTER_FIELDS = {"sale": "sale_ok", "purchase": "purchase_ok"}

NAME_MAX = 200
CODE_MAX = 40
TEXT_MAX = 120
NOTES_MAX = 5000
PICKING_MAX = 1000

# Every field the form saves, in log order.
LOG_LABELS = {
    "name": "Nama Produk",
    "is_favorite": "Favorit",
    "sale_ok": "Bisa Dijual",
    "purchase_ok": "Bisa Dibeli",
    "product_type": "Tipe Produk",
    "is_storable": "Lacak Inventaris",
    "list_price": "Harga Jual",
    "sale_tax": "Pajak Penjualan",
    "standard_price": "Modal",
    "purchase_tax": "Pajak Pembelian",
    "category": "Kategori",
    "default_code": "Referensi",
    "barcode": "Barcode",
    "label": "Label",
    "notes": "Catatan Internal",
    "weight": "Berat",
    "volume": "Volume",
    "sale_delay": "Waktu Tunggu Pelanggan",
    "description_pickingin": "Deskripsi Penerimaan",
    "description_pickingout": "Deskripsi Pengiriman"
}


def _number(value, default=0.0):
    text = str(value if value != None else "").strip().replace(",", ".")
    if text == "":
        return default
    # end if
    try:
        return float(text)
    except Exception:
        return None
    # end try
# end def


class products_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def tax_options(self, tax_use):
        # Picker options for Pajak Penjualan / Pembelian; rate lets the form
        # show the price including tax.
        out = [{"value": "", "label": "Tanpa pajak", "description": "", "rate": 0}]
        for tax in accounting_proc().line_taxes(None, tax_use):
            out.append({"value": tax["code"], "label": tax["name"], "description": tax.get("description", ""), "rate": tax["rate"]})
        # end for
        return out
    # end def

    def _public(self, doc, taxes=None):
        doc["id"] = str(doc.pop("_id"))
        code = doc.get("default_code", "")
        doc["display_name"] = ("[" + code + "] " if code else "") + doc.get("name", "")
        doc["type_label"] = PRODUCT_TYPES.get(doc.get("product_type", ""), "")
        doc["price_fmt"] = rupiah(doc.get("list_price", 0))
        doc["cost_fmt"] = rupiah(doc.get("standard_price", 0))
        taxes = taxes or {}
        sale_tax = taxes.get(doc.get("sale_tax", "")) or {}
        doc["sale_tax_name"] = sale_tax.get("name", "")
        doc["purchase_tax_name"] = (taxes.get(doc.get("purchase_tax", "")) or {}).get("name", "")
        doc["price_incl_fmt"] = rupiah(round((doc.get("list_price") or 0) * (1 + tax_rate(sale_tax)), 2)) if sale_tax else ""
        return doc
    # end def

    def _query(self, filter_key, q):
        query = {"is_deleted": False, "active": True}
        if filter_key in FILTER_FIELDS:
            query[FILTER_FIELDS[filter_key]] = True
        # end if
        q = (q or "").strip()
        if q != "":
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"default_code": {"$regex": pattern, "$options": "i"}},
                {"barcode": {"$regex": pattern, "$options": "i"}},
                {"category": {"$regex": pattern, "$options": "i"}}
            ]
        # end if
        return query
    # end def

    def page_products(self, filter_key, q="", page=1, per_page=paginate.DEFAULT_PAGE_SIZE):
        query = self._query(filter_key, q)
        projection = {"seq": 1, "name": 1, "default_code": 1, "list_price": 1, "standard_price": 1,
                      "product_type": 1, "is_favorite": 1, "sale_ok": 1, "purchase_ok": 1, "category": 1}
        total = self.mgdDB.db_product.count_documents(query)
        pager = paginate.build(total, page, per_page)
        recs = self.mgdDB.db_product.find(query, projection).sort(
            [("is_favorite", -1), ("name", 1), ("_id", 1)]
        ).skip(pager["offset"]).limit(pager["per_page"])
        out = []
        for rec in recs:
            out.append(self._public(rec))
        # end for
        pager["products"] = out
        return pager
    # end def

    def get_by_seq(self, seq):
        doc = self.mgdDB.db_product.find_one({"seq": seq, "is_deleted": False})
        if doc == None:
            return None
        # end if
        taxes = accounting_proc().tax_map([doc.get("sale_tax", ""), doc.get("purchase_tax", "")])
        return self._public(doc, taxes)
    # end def

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _next_seq(self):
        if self.mgdDB.db_code_counter.find_one({"counter_key": SEQID_KEY}, {"_id": 1}) == None:
            top = self.mgdDB.db_product.find_one({"seq": {"$gt": 0}}, {"seq": 1}, sort=[("seq", -1)])
            self.mgdDB.db_code_counter.update_one(
                {"counter_key": SEQID_KEY}, {"$max": {"seq": (top or {}).get("seq") or 0}}, upsert=True
            )
        # end if
        rec = self.mgdDB.db_code_counter.find_one_and_update(
            {"counter_key": SEQID_KEY}, {"$inc": {"seq": 1}},
            upsert=True, return_document=pymongo.ReturnDocument.AFTER
        )
        return rec["seq"]
    # end def

    def _taken(self, field, value, exclude_id):
        query = {field: value, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        # end if
        return self.mgdDB.db_product.find_one(query, {"_id": 1}) != None
    # end def

    def _fields(self, params, current=None):
        name = (params.get("name") or "").strip()
        if name == "":
            return None, {"status": "ERROR", "desc": "Nama produk wajib diisi"}
        # end if
        product_type = (params.get("product_type") or "service").strip()
        if product_type not in PRODUCT_TYPES:
            return None, {"status": "ERROR", "desc": "Tipe produk tidak valid"}
        # end if
        numbers = {}
        for key, label in [("list_price", "Harga jual"), ("standard_price", "Modal"), ("weight", "Berat"), ("volume", "Volume"), ("sale_delay", "Waktu tunggu")]:
            value = _number(params.get(key))
            if value == None or value < 0:
                return None, {"status": "ERROR", "desc": label + " harus angka 0 atau lebih"}
            # end if
            numbers[key] = round(value, 2)
        # end for
        acc = accounting_proc()
        sale_codes = [t["code"] for t in acc.line_taxes(None, "sale")]
        purchase_codes = [t["code"] for t in acc.line_taxes(None, "purchase")]
        sale_tax = (params.get("sale_tax") or "").strip()
        purchase_tax = (params.get("purchase_tax") or "").strip()
        keep_sale = (current or {}).get("sale_tax", "")
        keep_purchase = (current or {}).get("purchase_tax", "")
        if sale_tax != "" and sale_tax not in sale_codes and sale_tax != keep_sale:
            return None, {"status": "ERROR", "desc": "Pajak penjualan tidak valid atau tidak aktif"}
        # end if
        if purchase_tax != "" and purchase_tax not in purchase_codes and purchase_tax != keep_purchase:
            return None, {"status": "ERROR", "desc": "Pajak pembelian tidak valid atau tidak aktif"}
        # end if
        default_code = (params.get("default_code") or "").strip()[:CODE_MAX]
        barcode = (params.get("barcode") or "").strip()[:CODE_MAX]
        exclude_id = (current or {}).get("id", "")
        if default_code != "" and self._taken("default_code", default_code, exclude_id):
            return None, {"status": "ERROR", "desc": "Referensi " + default_code + " sudah dipakai produk lain"}
        # end if
        if barcode != "" and self._taken("barcode", barcode, exclude_id):
            return None, {"status": "ERROR", "desc": "Barcode " + barcode + " sudah dipakai produk lain"}
        # end if
        notes = (params.get("notes") or "").strip()
        if len(notes) > NOTES_MAX:
            return None, {"status": "ERROR", "desc": "Catatan internal maksimal " + str(NOTES_MAX) + " karakter"}
        # end if
        fields = {
            "name": name[:NAME_MAX],
            "is_favorite": params.get("is_favorite") == "1",
            "sale_ok": params.get("sale_ok") == "1",
            "purchase_ok": params.get("purchase_ok") == "1",
            "product_type": product_type,
            # Lacak Inventaris only applies to Barang.
            "is_storable": product_type == "goods" and params.get("is_storable") == "1",
            "list_price": numbers["list_price"],
            "sale_tax": sale_tax,
            "standard_price": numbers["standard_price"],
            "purchase_tax": purchase_tax,
            "category": (params.get("category") or "").strip()[:TEXT_MAX],
            "default_code": default_code,
            "barcode": barcode,
            "label": (params.get("label") or "").strip()[:TEXT_MAX],
            "notes": notes,
            "weight": numbers["weight"],
            "volume": numbers["volume"],
            "sale_delay": int(numbers["sale_delay"]),
            "description_pickingin": (params.get("description_pickingin") or "").strip()[:PICKING_MAX],
            "description_pickingout": (params.get("description_pickingout") or "").strip()[:PICKING_MAX]
        }
        return fields, None
    # end def

    def _log_values(self, doc, taxes):
        out = {}
        for key in LOG_LABELS:
            out[key] = doc.get(key, "")
        # end for
        for key in ["is_favorite", "sale_ok", "purchase_ok", "is_storable"]:
            out[key] = "Ya" if doc.get(key) else "Tidak"
        # end for
        out["product_type"] = PRODUCT_TYPES.get(doc.get("product_type", ""), "")
        out["list_price"] = rupiah(doc.get("list_price", 0))
        out["standard_price"] = rupiah(doc.get("standard_price", 0))
        out["sale_tax"] = (taxes.get(doc.get("sale_tax", "")) or {}).get("name", "") or "Tanpa pajak"
        out["purchase_tax"] = (taxes.get(doc.get("purchase_tax", "")) or {}).get("name", "") or "Tanpa pajak"
        out["weight"] = "{:g}".format(doc.get("weight") or 0) + " kg"
        out["volume"] = "{:g}".format(doc.get("volume") or 0) + " m³"
        out["sale_delay"] = str(doc.get("sale_delay") or 0) + " hari"
        return out
    # end def

    def create_product(self, params, actor=None):
        fields, err = self._fields(params)
        if err != None:
            return err
        # end if
        seq = self._next_seq()
        rec = database.new(self.mgdDB, "db_product")
        rec.put("seq", seq)
        rec.put("active", True)
        rec.put("uom", "Unit")
        for key in fields:
            rec.put(key, fields[key])
        # end for
        rec.insert()
        product_id = str(rec.get().get("_id", ""))
        record_log_proc().log_create(LOG_MODEL, product_id, actor, "Produk dibuat")
        return {"status": "SUCCESS", "desc": "Produk " + fields["name"] + " disimpan", "id": product_id, "seq": seq}
    # end def

    def update_product(self, seq, params, actor=None):
        product = self.get_by_seq(seq)
        if product == None:
            return {"status": "ERROR", "desc": "Produk tidak ditemukan"}
        # end if
        fields, err = self._fields(params, product)
        if err != None:
            return err
        # end if
        self.mgdDB.db_product.update_one({"_id": ObjectId(product["id"]), "is_deleted": False}, {"$set": fields})
        taxes = accounting_proc().tax_map([product.get("sale_tax", ""), product.get("purchase_tax", ""), fields["sale_tax"], fields["purchase_tax"]])
        record_log_proc().log_changes(LOG_MODEL, product["id"], self._log_values(product, taxes), self._log_values(fields, taxes), LOG_LABELS, actor)
        return {"status": "SUCCESS", "desc": "Produk disimpan"}
    # end def
# end class
