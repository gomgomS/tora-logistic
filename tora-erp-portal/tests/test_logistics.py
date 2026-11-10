import os
import re

# Tests run against a scratch database so local data is never touched
os.environ["MONGO_DB_NAME"] = "slapz_test"

import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import pytest

from slapz102_core import config
from slapz102_core import database
import server


@pytest.fixture()
def client():
    db = database.get_db_conn(config.mainDB)
    db.client.drop_database(config.mainDB)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client
    # end with
# end def


@pytest.fixture()
def logged_in(client):
    # GET /login bootstraps the default superadmin and exposes a CSRF token
    html = client.get("/login").data.decode("utf-8")
    marker = 'name="csrf_token" value="'
    start = html.find(marker) + len(marker)
    end = html.find('"', start)
    token = html[start:end]
    res = client.post("/login", data={
        "csrf_token": token,
        "username": config.G_SUPERADMIN_USERNAME,
        "password": config.G_SUPERADMIN_PASSWORD
    })
    assert res.status_code == 302
    return {"client": client, "token": token}
# end def


def _db():
    return database.get_db_conn(config.mainDB)
# end def


def _contact_id(name):
    return str(_db().db_contact.find_one({"name": name})["_id"])
# end def


def _vehicle_id(plate):
    return str(_db().db_vehicle.find_one({"plate_number": plate})["_id"])
# end def


def _driver_id(license_number):
    return str(_db().db_driver.find_one({"license_number": license_number})["_id"])
# end def


def _seed(logged_in):
    # Master data: client, receiver, driver contact, vehicle, driver
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "PT Sumber Makmur", "company_name": "Sumber Makmur",
        "category": "CLIENT", "city": "Jakarta", "phone": "021-555"
    })
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "Toko Jaya Malang", "company_name": "Jaya",
        "category": "RECEIVER", "city": "Malang", "phone": "0341-555"
    })
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "UD Sidoarjo", "category": "RECEIVER", "city": "Surabaya"
    })
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "Budi Santoso", "category": "DRIVER", "city": "Jakarta",
        "phone": "0812-111"
    })
    client.post("/fleet/vehicle/create", data={
        "csrf_token": token, "plate_number": "B 9111 UYZ",
        "vehicle_type": "Wingbox", "ownership": "INTERNAL"
    })
    client.post("/fleet/vehicle/create", data={
        "csrf_token": token, "plate_number": "L 8888 AB",
        "vehicle_type": "CDD", "ownership": "VENDOR", "vendor_name": "CV Trans"
    })
    client.post("/fleet/driver/create", data={
        "csrf_token": token, "contact_id": _contact_id("Budi Santoso"),
        "license_number": "SIM-JIH-991", "type": "INTERNAL"
    })
# end def


def _create_shipment(logged_in, destination, service="LTL", po_number=""):
    client = logged_in["client"]
    res = client.post("/shipments/create", data={
        "csrf_token": logged_in["token"],
        "service_type": service,
        "sender_id": _contact_id("PT Sumber Makmur"),
        "receiver_id": _contact_id("Toko Jaya Malang") if destination == "Malang"
                       else _contact_id("UD Sidoarjo"),
        "origin_city": "Jakarta",
        "destination_city": destination,
        "po_number": po_number
    })
    assert res.status_code == 302
# end def


def _shipment_doc(tracking_code):
    return _db().db_shipment.find_one({"tracking_code": tracking_code})
# end def


# ---------------------------------------------------------------------------
# Auth / RBAC
# ---------------------------------------------------------------------------

def test_requires_login(client):
    for path in ["/", "/operations", "/shipments", "/manifests", "/hub", "/contacts", "/fleet"]:
        res = client.get(path)
        assert res.status_code == 302
        assert "/login" in res.headers.get("Location", "")
    # end for
# end def


def test_login_and_dashboard(logged_in):
    res = logged_in["client"].get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Dasbor" in html
    assert "Operasional" in html
    assert "Kontak" in html
    assert "Pengaturan" in html
# end def


def test_operations_overview(logged_in):
    res = logged_in["client"].get("/operations")
    assert res.status_code == 200
    assert "Ringkasan Operasional" in res.data.decode("utf-8")
# end def


def test_users_page_is_superadmin_only(logged_in):
    res = logged_in["client"].get("/users")
    assert res.status_code == 200
    assert config.G_SUPERADMIN_USERNAME in res.data.decode("utf-8")
# end def


def _login_as(username, password):
    # Separate browser session for a second user.
    other = server.app.test_client()
    html = other.get("/login").data.decode("utf-8")
    marker = 'name="csrf_token" value="'
    start = html.find(marker) + len(marker)
    token = html[start:html.find('"', start)]
    res = other.post("/login", data={"csrf_token": token, "username": username, "password": password})
    assert res.status_code == 302
    return {"client": other, "token": token}
# end def


def _create_user(logged_in, username, extra):
    data = {
        "csrf_token": logged_in["token"], "username": username, "name": username.title(),
        "role": "admin", "password": "Rahasia123", "password_confirm": "Rahasia123"
    }
    data.update(extra)
    return logged_in["client"].post("/users/create", data=data)
# end def


def test_settings_and_user_pages_render(logged_in):
    client = logged_in["client"]
    assert client.get("/settings").status_code == 200
    html = client.get("/users").data.decode("utf-8")
    assert config.G_SUPERADMIN_USERNAME in html
    assert client.get("/users/new").status_code == 200
    me = str(_db().db_user.find_one({"username": config.G_SUPERADMIN_USERNAME})["_id"])
    html = client.get("/users/" + me + "/edit").data.decode("utf-8")
    assert "Hak Akses" in html
    assert "Keamanan" in html
    assert "Ubah Sandi" in html
# end def


def test_user_access_levels_are_enforced(logged_in):
    res = _create_user(logged_in, "staf_lihat", {"perm_contacts": "read", "perm_users": "none"})
    assert res.status_code == 302
    doc = _db().db_user.find_one({"username": "staf_lihat"})
    assert doc["permissions"]["contacts"] == "read"
    assert _db().db_record_log.find_one({"model": "user", "record_id": str(doc["_id"]), "kind": "CREATE"}) != None
    staf = _login_as("staf_lihat", "Rahasia123")
    client = staf["client"]
    assert client.get("/contacts").status_code == 200
    res = client.get("/contacts/new")
    assert res.status_code == 302
    client.post("/contacts/create", data={"csrf_token": staf["token"], "name": "Tidak Boleh", "category": "CLIENT"})
    assert _db().db_contact.find_one({"name": "Tidak Boleh"}) == None
    assert client.get("/users").status_code == 302
    assert client.get("/settings").status_code == 302
    home = client.get("/").data.decode("utf-8")
    assert "Pengaturan" not in home
    assert "Kontak" in home
# end def


def test_user_password_confirmation(logged_in):
    res = _create_user(logged_in, "staf_salah", {"password_confirm": "BedaSandi99"})
    assert res.status_code == 302
    assert _db().db_user.find_one({"username": "staf_salah"}) == None
# end def


def test_user_admin_cannot_escalate(logged_in):
    _create_user(logged_in, "manajer", {"perm_users": "full", "perm_contacts": "read"})
    mgr = _login_as("manajer", "Rahasia123")
    client = mgr["client"]
    base = {"csrf_token": mgr["token"], "password": "Rahasia123", "password_confirm": "Rahasia123"}
    over = dict(base, username="lebih_tinggi", role="admin", perm_contacts="full", perm_users="none")
    client.post("/users/create", data=over)
    assert _db().db_user.find_one({"username": "lebih_tinggi"}) == None
    boss = dict(base, username="jadi_super", role="superadmin")
    client.post("/users/create", data=boss)
    assert _db().db_user.find_one({"username": "jadi_super"}) == None
    ok = dict(base, username="staf_baru", role="admin", perm_contacts="read", perm_users="none")
    client.post("/users/create", data=ok)
    assert _db().db_user.find_one({"username": "staf_baru"}) != None
    me = str(_db().db_user.find_one({"username": "manajer"})["_id"])
    client.post("/users/" + me + "/update", data={
        "csrf_token": mgr["token"], "username": "manajer", "role": "admin",
        "status": "ENABLE", "perm_contacts": "full", "perm_users": "full"
    })
    assert _db().db_user.find_one({"username": "manajer"})["permissions"]["contacts"] == "read"
# end def


def test_user_bulk_delete_protects_self(logged_in):
    client = logged_in["client"]
    me = str(_db().db_user.find_one({"username": config.G_SUPERADMIN_USERNAME})["_id"])
    _create_user(logged_in, "staf_hapus", {})
    other = str(_db().db_user.find_one({"username": "staf_hapus"})["_id"])
    client.post("/users/bulk-delete", data={"csrf_token": logged_in["token"], "ids": [me, other]})
    assert _db().db_user.find_one({"_id": _db().db_user.find_one({"username": "staf_hapus"})["_id"]})["is_deleted"] == False
    client.post("/users/bulk-delete", data={"csrf_token": logged_in["token"], "ids": [other]})
    assert _db().db_user.find_one({"username": "staf_hapus"})["is_deleted"] == True
    assert _db().db_user.find_one({"username": config.G_SUPERADMIN_USERNAME})["is_deleted"] == False
# end def


def test_user_update_is_logged(logged_in):
    client = logged_in["client"]
    _create_user(logged_in, "staf_log", {"perm_contacts": "read"})
    uid = str(_db().db_user.find_one({"username": "staf_log"})["_id"])
    res = client.post("/users/" + uid + "/update", data={
        "csrf_token": logged_in["token"], "username": "staf_log", "name": "Staf Gudang",
        "role": "admin", "status": "ENABLE", "perm_contacts": "update", "perm_users": "none",
        "password": "SandiBaru123", "password_confirm": "SandiBaru123"
    })
    assert res.status_code == 302
    change = _db().db_record_log.find_one({"model": "user", "record_id": uid, "kind": "CHANGE"})
    labels = [ch["label"] for ch in change["changes"]]
    assert "Nama" in labels
    assert "Hak akses Kontak" in labels
    assert _db().db_record_log.find_one({"model": "user", "record_id": uid, "kind": "EVENT"}) != None
    _login_as("staf_log", "SandiBaru123")
# end def


def test_accounting_dashboard_and_menus(logged_in):
    client = logged_in["client"]
    assert "Akuntansi" in client.get("/").data.decode("utf-8")
    html = client.get("/accounting").data.decode("utf-8")
    for text in ["Dasbor Akuntansi", "Faktur Pelanggan", "Tagihan Vendor", "Bank", "Kas",
                 "Nota Kredit", "Pengembalian", "Entri Jurnal", "Rp 0,00"]:
        assert text in html, text
    assert client.get("/accounting/client-invoices").status_code == 200
    assert client.get("/accounting/client-invoices/new").status_code == 200
    assert client.get("/accounting/tidak-ada").status_code == 302
# end def


def _invoice_payload(logged_in, partner_id, extra=None):
    data = {
        "csrf_token": logged_in["token"],
        "partner_id": partner_id,
        "invoice_date": "2026-11-06",
        "payment_term": "30 Hari",
        "customer_ref": "SP/SLN/2026/088",
        "line_product": ["Jasa Trucking Jakarta - Surabaya", "Pallet kayu"],
        "line_account": ["41000020", "41000010"],
        "line_quantity": ["1", "2"],
        "line_price": ["40000000", "1000000"],
        "line_tax": ["ppn12_dpp", ""]
    }
    if extra != None:
        data.update(extra)
    # end if
    return data
# end def


def _invoices():
    return _db().db_invoice
# end def


def test_invoice_create_computes_totals_and_lists(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    res = client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur")))
    assert res.status_code == 302
    inv = _invoices().find_one({"customer_ref": "SP/SLN/2026/088"})
    assert inv["state"] == "DRAFT"
    assert inv["number"] == "INV/2026/00001"
    assert inv["seq"] == 1
    assert "/accounting/client-invoices/1?" in res.headers["Location"]
    assert inv["partner_name"] == "PT Sumber Makmur"
    assert inv["amount_untaxed"] == 42000000
    assert inv["amount_tax"] == 4400000
    assert inv["amount_total"] == 46400000
    assert inv["due_date"] == "2026-12-06"
    assert len(inv["lines"]) == 2
    html = client.get("/accounting/client-invoices").data.decode("utf-8")
    assert "PT Sumber Makmur" in html
    assert "Rp 46.400.000,00" in html
    html = client.get("/accounting/client-invoices/1").data.decode("utf-8")
    assert "Baris Faktur" in html
    assert "Piutang Dagang" in html
    assert "PPN Keluaran" in html
    assert "Simpan" in html
    assert "Rancangan" not in html
    assert _db().db_record_log.find_one({"model": "invoice", "record_id": str(inv["_id"]), "kind": "CREATE"}) != None
    # old links (internal id or invoice number) redirect to the running number
    res = client.get("/accounting/client-invoices/" + str(inv["_id"]))
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/accounting/client-invoices/1")
    res = client.get("/accounting/client-invoices/INV/2026/00001")
    assert res.headers["Location"].endswith("/accounting/client-invoices/1")
    # a draft stays editable: change a line and the totals follow
    client.post("/accounting/client-invoices/1/update", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "line_quantity": ["2", "2"]
    }))
    assert _invoices().find_one({"_id": inv["_id"]})["amount_untaxed"] == 82000000
    # every saved field lands in the log, including each changed line
    client.post("/accounting/client-invoices/1/update", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "line_quantity": ["2", "2"], "payment_ref": "TRF-001", "notes": "Bayar 30 hari",
        "fiscal_position": "PKP", "delivery_date": "2026-11-07", "efaktur_code": "04"
    }))
    change = _db().db_record_log.find({"model": "invoice", "record_id": str(inv["_id"]), "kind": "CHANGE"}).sort("_id", -1).limit(1)[0]
    labels = [ch["label"] for ch in change["changes"]]
    for label in ["Referensi Pembayaran", "Syarat dan Ketentuan", "Posisi Fiskal", "Tanggal Pengiriman", "Kode Transaksi"]:
        assert label in labels, label
    client.post("/accounting/client-invoices/1/update", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "line_quantity": ["2", "3"], "payment_ref": "TRF-001", "notes": "Bayar 30 hari",
        "fiscal_position": "PKP", "delivery_date": "2026-11-07", "efaktur_code": "04"
    }))
    change = _db().db_record_log.find({"model": "invoice", "record_id": str(inv["_id"]), "kind": "CHANGE"}).sort("_id", -1).limit(1)[0]
    labels = [ch["label"] for ch in change["changes"]]
    # only the edited field of the edited row, plus the totals it moved
    assert "Kuantitas (Baris 2)" in labels
    assert "Produk (Baris 2)" not in labels
    assert not any("Baris 1" in label for label in labels)
    assert "Jumlah Sebelum Pajak" in labels
    qty = [ch for ch in change["changes"] if ch["label"] == "Kuantitas (Baris 2)"][0]
    assert qty["old"] == "2"
    assert qty["new"] == "3"
    client.post("/accounting/client-invoices/1/update", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "line_product": ["Jasa Trucking Jakarta - Surabaya"], "line_account": ["41000020"],
        "line_quantity": ["2"], "line_price": ["40000000"], "line_tax": ["ppn12_dpp"],
        "payment_ref": "TRF-001", "notes": "Bayar 30 hari",
        "fiscal_position": "PKP", "delivery_date": "2026-11-07", "efaktur_code": "04"
    }))
    change = _db().db_record_log.find({"model": "invoice", "record_id": str(inv["_id"]), "kind": "CHANGE"}).sort("_id", -1).limit(1)[0]
    assert "Baris 2 dihapus" in [ch["label"] for ch in change["changes"]]
# end def


def test_invoice_confirm_numbering_and_lock(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "A1", "action": "confirm"}))
    first = _invoices().find_one({"customer_ref": "A1"})
    assert first["state"] == "POSTED"
    assert first["number"] == "INV/2026/00001"
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "A2"}))
    second = _invoices().find_one({"customer_ref": "A2"})
    assert second["number"] == "INV/2026/00002"
    assert second["state"] == "DRAFT"
    client.post("/accounting/client-invoices/" + str(second["seq"]) + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "A2", "action": "confirm"}))
    confirmed = _invoices().find_one({"_id": second["_id"]})
    assert confirmed["state"] == "POSTED"
    assert confirmed["number"] == "INV/2026/00002"
    # posted invoices cannot be edited
    client.post("/accounting/client-invoices/" + str(first["seq"]) + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "DIUBAH"}))
    assert _invoices().find_one({"_id": first["_id"]})["customer_ref"] == "A1"
    # invoices that were ever confirmed are never deleted, reset keeps the number
    client.post("/accounting/client-invoices/bulk-delete", data={"csrf_token": logged_in["token"], "ids": [str(first["_id"])]})
    assert _invoices().find_one({"_id": first["_id"]})["is_deleted"] == False
    client.post("/accounting/client-invoices/" + str(first["seq"]) + "/state", data={"csrf_token": logged_in["token"], "action": "reset"})
    reset = _invoices().find_one({"_id": first["_id"]})
    assert reset["state"] == "DRAFT"
    assert reset["number"] == "INV/2026/00001"
    assert "Rp 46.400.000,00" in client.get("/accounting").data.decode("utf-8")
    events = _db().db_record_log.find_one({"model": "invoice", "record_id": str(first["_id"]), "kind": "EVENT"})
    assert events["body"] == "Faktur telah divalidasi"
# end def


def test_invoice_payment_print_and_buttons(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "BAYAR", "action": "confirm"}))
    inv = _invoices().find_one({"customer_ref": "BAYAR"})
    url = "/accounting/client-invoices/" + str(inv["seq"])
    html = client.get(url).data.decode("utf-8")
    for label in ["Kirim", "Cetak", "Bayar", "Pratinjau", "Nota Kredit", "Reset ke Draft"]:
        assert label in html, label
    assert client.get(url + "/print").status_code == 200
    # overpaying is refused
    client.post(url + "/pay", data={"csrf_token": logged_in["token"], "amount": "99999999999", "method": "Transfer Bank"})
    assert _invoices().find_one({"_id": inv["_id"]})["amount_residual"] == 46400000
    # partial, then the rest
    client.post(url + "/pay", data={"csrf_token": logged_in["token"], "amount": "6400000", "method": "Transfer Bank", "date": "2026-11-10"})
    part = _invoices().find_one({"_id": inv["_id"]})
    assert part["amount_residual"] == 40000000
    assert part["payment_state"] == "partial"
    client.post(url + "/pay", data={"csrf_token": logged_in["token"], "amount": "40000000", "method": "Tunai"})
    paid = _invoices().find_one({"_id": inv["_id"]})
    assert paid["amount_residual"] == 0
    assert paid["payment_state"] == "paid"
    assert len(paid["payments"]) == 2
    assert "Lunas" in client.get("/accounting/client-invoices").data.decode("utf-8")
    html = client.get(url).data.decode("utf-8")
    assert "LUNAS" in html
    # a paid invoice cannot go back to Draft
    client.post(url + "/state", data={"csrf_token": logged_in["token"], "action": "reset"})
    assert _invoices().find_one({"_id": inv["_id"]})["state"] == "POSTED"
    # every Bayar is a Pembayaran record (PAY00001, PAY00002), Lunas
    pays = list(_db().db_payment.find({"invoice_id": str(inv["_id"])}).sort("seq", 1))
    assert [p["number"] for p in pays] == ["PAY00001", "PAY00002"]
    assert pays[0]["state"] == "PAID"
    assert pays[1]["journal"] == "CSH1"
    assert paid["payments"][0]["payment_id"] == str(pays[0]["_id"])
# end def


def test_customer_payment_flow(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "PAY-FLOW", "action": "confirm"}))
    inv = _invoices().find_one({"customer_ref": "PAY-FLOW"})
    assert client.get("/accounting/client-payments").status_code == 200
    html = client.get("/accounting/client-payments/new?invoice=" + str(inv["_id"])).data.decode("utf-8")
    assert inv["number"] in html
    assert "PAY00001" in html
    # Draft first: nothing is settled yet
    client.post("/accounting/client-payments/create", data={
        "csrf_token": token, "payment_type": "inbound", "partner_id": partner, "amount": "10000000",
        "date": "2026-11-06", "memo": "Pelunasan sebagian", "journal": "BNK1", "method": "Transfer Bank",
        "bank_account": "BCA 123", "invoice_id": str(inv["_id"])
    })
    pay = _db().db_payment.find_one({"memo": "Pelunasan sebagian"})
    assert pay["state"] == "DRAFT"
    assert pay["seq"] == 1
    assert _invoices().find_one({"_id": inv["_id"]})["amount_residual"] == 46400000
    # edit the draft: change is logged
    client.post("/accounting/client-payments/1/update", data={
        "csrf_token": token, "payment_type": "inbound", "partner_id": partner, "amount": "12000000",
        "date": "2026-11-06", "memo": "Pelunasan sebagian", "journal": "BNK1", "method": "Transfer Bank",
        "bank_account": "BCA 123", "invoice_id": str(inv["_id"]), "action": "confirm"
    })
    change = _db().db_record_log.find_one({"model": "payment", "record_id": str(pay["_id"]), "kind": "CHANGE"})
    assert "Jumlah" in [ch["label"] for ch in change["changes"]]
    # Konfirmasi settles the faktur
    pay = _db().db_payment.find_one({"_id": pay["_id"]})
    assert pay["state"] == "PAID"
    assert pay["applied"] == 12000000
    after = _invoices().find_one({"_id": inv["_id"]})
    assert after["amount_residual"] == 34400000
    assert after["payment_state"] == "partial"
    html = client.get("/accounting/client-payments").data.decode("utf-8")
    assert "Lunas" in html
    assert "Rp 12.000.000,00" in html
    # Tandai sebagai Terkirim, then Reset ke Draft gives the amount back
    client.post("/accounting/client-payments/1/state", data={"csrf_token": token, "action": "sent"})
    assert _db().db_payment.find_one({"_id": pay["_id"]})["is_sent"] == True
    client.post("/accounting/client-payments/1/state", data={"csrf_token": token, "action": "reset"})
    back = _invoices().find_one({"_id": inv["_id"]})
    assert back["amount_residual"] == 46400000
    assert back["payment_state"] == "not_paid"
    assert back["payments"] == []
    assert _db().db_payment.find_one({"_id": pay["_id"]})["state"] == "DRAFT"
    # a payment for another customer's faktur is refused
    client.post("/accounting/client-payments/create", data={
        "csrf_token": token, "payment_type": "inbound", "partner_id": _contact_id("Toko Jaya Malang"), "amount": "1000",
        "memo": "SALAH", "journal": "BNK1", "method": "Tunai", "invoice_id": str(inv["_id"])
    })
    assert _db().db_payment.find_one({"memo": "SALAH"}) == None
# end def


def test_invoice_number_edit_on_draft(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "N1"}))
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "N2"}))
    second = _invoices().find_one({"customer_ref": "N2"})
    url = "/accounting/client-invoices/" + str(second["seq"])
    # live check warns about a number that is already used
    check = client.get(url + "/check-number?n=00001").get_json()
    assert check["exists"] == True
    assert check["number"] == "INV/2026/00001"
    # saving a duplicate is refused
    client.post(url + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "N2", "number_seq": "00001"}))
    assert _invoices().find_one({"_id": second["_id"]})["number"] == "INV/2026/00002"
    # a free number is accepted; short input is zero-padded, the prefix stays
    assert client.get(url + "/check-number?n=7").get_json()["exists"] == False
    client.post(url + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "N2", "number_seq": "7"}))
    assert _invoices().find_one({"_id": second["_id"]})["number"] == "INV/2026/00007"
    change = _db().db_record_log.find_one({"model": "invoice", "record_id": str(second["_id"]), "kind": "CHANGE"})
    assert "Nomor" in [ch["label"] for ch in change["changes"]]
    # once confirmed the number is fixed
    client.post(url + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "N2", "number_seq": "00007", "action": "confirm"}))
    client.post(url + "/update", data=_invoice_payload(logged_in, partner, {"customer_ref": "N2", "number_seq": "00009"}))
    assert _invoices().find_one({"_id": second["_id"]})["number"] == "INV/2026/00007"
# end def


def test_credit_note_from_invoice_and_apply(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "ASAL", "action": "confirm"}))
    inv = _invoices().find_one({"customer_ref": "ASAL"})
    assert client.get("/accounting/client-credit-notes").status_code == 200
    # the faktur's Nota Kredit button prefills customer + origin
    html = client.get("/accounting/client-credit-notes/new?invoice=" + str(inv["seq"])).data.decode("utf-8")
    assert inv["number"] in html
    assert "RINV/" in html
    client.post("/accounting/client-credit-notes/create", data={
        "csrf_token": token, "partner_id": partner, "invoice_date": "2026-11-08",
        "customer_ref": "Klaim kemasan", "reversed_entry_id": str(inv["_id"]),
        "line_product": ["Klaim ganti rugi kerusakan kemasan"], "line_account": ["41000010"],
        "line_quantity": ["1"], "line_price": ["2000000"], "line_tax": [""], "action": "confirm"
    })
    cn = _invoices().find_one({"customer_ref": "Klaim kemasan"})
    assert cn["move_type"] == "out_refund"
    assert cn["number"] == "RINV/2026/00001"
    assert cn["seq"] == 1
    assert cn["state"] == "POSTED"
    assert cn["reversed_entry_number"] == inv["number"]
    # lists stay separate; credit notes read negative
    assert "Klaim kemasan" not in client.get("/accounting/client-invoices?q=Klaim").data.decode("utf-8")
    assert "Rp -2.000.000,00" in client.get("/accounting/client-credit-notes").data.decode("utf-8")
    # form: reverse journal + open debit of the same customer
    html = client.get("/accounting/client-credit-notes/1").data.decode("utf-8")
    assert "Nota Kredit Pelanggan" in html
    assert "Debet belum lunas" in html
    assert inv["number"] in html
    # Tambah: settle the faktur with the credit note
    client.post("/accounting/client-credit-notes/1/apply", data={"csrf_token": token, "invoice_id": str(inv["_id"])})
    inv_after = _invoices().find_one({"_id": inv["_id"]})
    cn_after = _invoices().find_one({"_id": cn["_id"]})
    assert inv_after["amount_residual"] == 44400000
    assert inv_after["payment_state"] == "partial"
    assert cn_after["amount_residual"] == 0
    assert cn_after["payment_state"] == "paid"
    assert _db().db_record_log.find_one({"model": "credit_note", "record_id": str(cn["_id"]), "kind": "EVENT"}) != None
# end def


def test_invoice_draft_editable_with_create_access(logged_in):
    _seed(logged_in)
    _create_user(logged_in, "staf_faktur", {"perm_accounting": "create", "perm_contacts": "read"})
    staf = _login_as("staf_faktur", "Rahasia123")
    client = staf["client"]
    partner = _contact_id("PT Sumber Makmur")
    payload = _invoice_payload({"token": staf["token"]}, partner, {"customer_ref": "STAF"})
    client.post("/accounting/client-invoices/create", data=payload)
    inv = _invoices().find_one({"customer_ref": "STAF"})
    url = "/accounting/client-invoices/" + str(inv["seq"])
    client.post(url + "/update", data=dict(payload, customer_ref="STAF-2"))
    assert _invoices().find_one({"_id": inv["_id"]})["customer_ref"] == "STAF-2"
    # confirming needs "ubah"
    client.post(url + "/update", data=dict(payload, customer_ref="STAF-2", action="confirm"))
    assert _invoices().find_one({"_id": inv["_id"]})["state"] == "DRAFT"
# end def


def test_invoice_validation_and_draft_delete(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "PAJAK-SALAH", "line_tax": ["pajak-palsu", ""]}))
    assert _invoices().find_one({"customer_ref": "PAJAK-SALAH"}) == None
    client.post("/accounting/client-invoices/create", data={
        "csrf_token": logged_in["token"], "partner_id": partner, "customer_ref": "KOSONG", "action": "confirm"
    })
    empty = _invoices().find_one({"customer_ref": "KOSONG"})
    assert empty["state"] == "DRAFT"
    client.post("/accounting/client-invoices/bulk-delete", data={"csrf_token": logged_in["token"], "ids": [str(empty["_id"])]})
    assert _invoices().find_one({"_id": empty["_id"]})["is_deleted"] == True
# end def


def test_accounting_sequence_settings(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    html = client.get("/accounting/settings").data.decode("utf-8")
    assert "Nomor Dokumen" in html
    assert "Pajak" in html
    form = {
        "csrf_token": logged_in["token"],
        "prefix_out_invoice": "FK/{THN}/{BULAN}/", "padding_out_invoice": "4",
        "prefix_out_refund": "RINV/{TAHUN}/", "padding_out_refund": "5",
        "prefix_customer_payment": "PAY", "padding_customer_payment": "5",
        "prefix_in_invoice": "BILL/{TAHUN}/{BULAN}/", "padding_in_invoice": "4",
        "prefix_in_refund": "RBILL/{TAHUN}/{BULAN}/", "padding_in_refund": "4",
        "prefix_vendor_payment": "VPAY", "padding_vendor_payment": "5"
    }
    client.post("/accounting/settings/save", data=form)
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {"customer_ref": "PREFIX-BARU"}))
    assert _invoices().find_one({"customer_ref": "PREFIX-BARU"})["number"] == "FK/26/11/0001"
    bad = dict(form, prefix_out_invoice="INV {SALAH}")
    client.post("/accounting/settings/save", data=bad)
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {"customer_ref": "PREFIX-TETAP"}))
    assert _invoices().find_one({"customer_ref": "PREFIX-TETAP"})["number"] == "FK/26/11/0002"
# end def


def test_accounting_taxes_list_toggle_and_create(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    html = client.get("/accounting/taxes").data.decode("utf-8")
    assert "12% (Non-Luxury Good)" in html
    assert "Pembelian" in html
    assert "Penjualan" in client.get("/accounting/taxes?tax_use=sale").data.decode("utf-8")
    res = client.post("/accounting/taxes/ppn11/toggle", data={"csrf_token": logged_in["token"]}, headers={"X-Requested-With": "fetch"})
    assert res.get_json()["active"] == False
    # an inactive tax can no longer be used on a new invoice line
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "customer_ref": "PAJAK-NONAKTIF", "line_tax": ["ppn11", ""]
    }))
    assert _invoices().find_one({"customer_ref": "PAJAK-NONAKTIF"}) == None
    client.post("/accounting/taxes/create", data={
        "csrf_token": logged_in["token"], "name": "PPh 23", "tax_use": "purchase",
        "amount": "2", "base": "full", "scope": "service", "description": "Jasa", "active": "1"
    })
    tax = _db().db_tax.find_one({"name": "PPh 23"})
    assert tax["tax_use"] == "purchase"
    assert tax["invoice_label"] == "2%"
    assert client.get("/accounting/taxes/" + tax["code"]).status_code == 200
# end def


def test_accounting_accounts_list_toggle_and_create(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    html = client.get("/accounting/accounts").data.decode("utf-8")
    assert "41000010" in html
    assert "Piutang Dagang" in html
    assert "Piutang Dagang" not in client.get("/accounting/accounts?group=income").data.decode("utf-8")
    assert "Penjualan" in client.get("/accounting/accounts?q=4100").data.decode("utf-8")
    # code tree on the left: ?prefix=41 shows only 41xxxxxx
    assert "prefix=41" in html
    by_prefix = client.get("/accounting/accounts?prefix=41").data.decode("utf-8")
    assert "41000010" in by_prefix
    assert "11210010" not in by_prefix
    client.post("/accounting/accounts/create", data={
        "csrf_token": token, "code": "42000070", "name": "Diskon Penjualan",
        "account_type": "income", "description": "Diskon yang diberikan kepada pelanggan.", "active": "1"
    })
    assert _db().db_account.find_one({"code": "42000070"})["name"] == "Diskon Penjualan"
    # duplicate code is refused
    client.post("/accounting/accounts/create", data={"csrf_token": token, "code": "42000070", "name": "Lagi", "account_type": "income", "active": "1"})
    assert _db().db_account.count_documents({"code": "42000070"}) == 1
    client.post("/accounting/accounts/create", data={
        "csrf_token": token, "code": "61000010", "name": "Beban Gaji", "account_type": "expense", "active": "1"
    })
    # every active account except Piutang / Utang is offered on invoice lines
    html = client.get("/accounting/client-invoices/new").data.decode("utf-8")
    assert "42000070 Diskon Penjualan" in html
    assert "61000010 Beban Gaji" in html
    assert 'id="accountOptions"' in html
    client.post("/accounting/accounts/42000070/update", data={"csrf_token": token, "name": "Potongan Penjualan", "account_type": "income", "active": "1"})
    acc = _db().db_account.find_one({"code": "42000070"})
    assert acc["name"] == "Potongan Penjualan"
    assert _db().db_record_log.find_one({"model": "account", "record_id": str(acc["_id"]), "kind": "CHANGE"}) != None
    assert "Log catatan" in client.get("/accounting/accounts/42000070").data.decode("utf-8")
    res = client.post("/accounting/accounts/42000070/toggle", data={"csrf_token": token}, headers={"X-Requested-With": "fetch"})
    assert res.get_json()["active"] == False
    # an inactive account can no longer be used on a new invoice line
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, _contact_id("PT Sumber Makmur"), {
        "customer_ref": "AKUN-NONAKTIF", "line_account": ["42000070", "41000010"]
    }))
    assert _invoices().find_one({"customer_ref": "AKUN-NONAKTIF"}) == None
    assert client.get("/accounting/accounts/42000070").status_code == 200
# end def


def test_vendor_bill_refund_and_payment(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/contacts/create", data={"csrf_token": token, "name": "PT Armada Lintas Nusantara", "category": "VENDOR"})
    vendor = _contact_id("PT Armada Lintas Nusantara")
    assert client.get("/accounting/vendor-bills").status_code == 200
    html = client.get("/accounting/vendor-bills/new").data.decode("utf-8")
    for text in ["Tagihan Vendor", "Vendor", "Tanggal Tagihan", "Tanggal Akuntansi", "Bank Penerima", "Referensi Tagihan"]:
        assert text in html, text
    # bill: expense lines + PPN Masukan 12% (DPP 11/12) = 11%
    bill_payload = {
        "csrf_token": token, "partner_id": vendor, "invoice_date": "2026-11-06", "payment_term": "Langsung",
        "customer_ref": "PO/TRK/0045 - SJ/ALN/8891", "payment_ref": "Sewa truk subcon", "partner_bank": "BCA 123",
        "line_product": ["Sewa Truk Tronton Subcon JKT-SBY", "Penggantian Ban & Terpal"],
        "line_account": ["51000010", "51000010"], "line_quantity": ["1", "1"],
        "line_price": ["15000000", "2000000"], "line_tax": ["ppn12_dpp_in", "ppn12_dpp_in"], "action": "confirm"
    }
    client.post("/accounting/vendor-bills/create", data=bill_payload)
    bill = _invoices().find_one({"move_type": "in_invoice"})
    assert bill["state"] == "POSTED"
    assert bill["number"] == "BILL/2026/11/0001"
    assert bill["amount_tax"] == 1870000
    assert bill["amount_total"] == 18870000
    assert bill["partner_bank"] == "BCA 123"
    page = client.get("/accounting/vendor-bills/1").data.decode("utf-8")
    assert "Hutang Usaha" in page
    assert "PPN Masukan" in page
    assert "Pengembalian" in page
    # sales taxes are not allowed on a bill
    bad = dict(bill_payload, customer_ref="SALAH-PAJAK", line_tax=["ppn12_dpp", ""])
    client.post("/accounting/vendor-bills/create", data=bad)
    assert _invoices().find_one({"customer_ref": "SALAH-PAJAK"}) == None
    # vendor refund from the bill, then Tambah against it
    assert "BILL/2026/11/0001" in client.get("/accounting/vendor-refunds/new?invoice=1").data.decode("utf-8")
    client.post("/accounting/vendor-refunds/create", data={
        "csrf_token": token, "partner_id": vendor, "invoice_date": "2026-11-08", "customer_ref": "Potongan ban",
        "reversed_entry_id": str(bill["_id"]), "line_product": ["Potongan klaim ban"], "line_account": ["51000010"],
        "line_quantity": ["1"], "line_price": ["1000000"], "line_tax": [""], "action": "confirm"
    })
    refund = _invoices().find_one({"move_type": "in_refund"})
    assert refund["number"] == "RBILL/2026/11/0001"
    assert refund["reversed_entry_number"] == "BILL/2026/11/0001"
    assert "Kredit belum lunas" in client.get("/accounting/vendor-refunds/1").data.decode("utf-8")
    client.post("/accounting/vendor-refunds/1/apply", data={"csrf_token": token, "invoice_id": str(bill["_id"])})
    assert _invoices().find_one({"_id": bill["_id"]})["amount_residual"] == 17870000
    assert _db().db_record_log.find_one({"model": "vendor_refund", "record_id": str(refund["_id"]), "kind": "EVENT"}) != None
    # Bayar on the bill -> Pembayaran Vendor (Kirim), VPAY numbering
    client.post("/accounting/vendor-bills/1/pay", data={"csrf_token": token, "amount": "17870000", "method": "Transfer Bank", "date": "2026-11-10"})
    assert _invoices().find_one({"_id": bill["_id"]})["payment_state"] == "paid"
    pay = _db().db_payment.find_one({"partner_type": "supplier"})
    assert pay["number"] == "VPAY00001"
    assert pay["payment_type"] == "outbound"
    assert pay["seq"] == 1
    html = client.get("/accounting/vendor-payments").data.decode("utf-8")
    assert "Pembayaran Vendor" in html
    assert "VPAY00001" in html
    assert "Pembayaran Vendor" in client.get("/accounting/vendor-payments/1").data.decode("utf-8")
    # customer and vendor payment lists stay separate
    assert "VPAY00001" not in client.get("/accounting/client-payments").data.decode("utf-8")
# end def


def test_products_shared_catalogue(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    product = {
        "csrf_token": token, "name": "Jasa Trucking FTL Tronton (Jakarta - Surabaya)", "sale_ok": "1",
        "product_type": "service", "list_price": "18000000", "sale_tax": "ppn12_dpp", "standard_price": "0",
        "purchase_tax": "", "default_code": "SRV-TRK-JKTSBY", "weight": "0", "volume": "0", "sale_delay": "0"
    }
    assert client.get("/accounting/client-products/new").status_code == 200
    res = client.post("/accounting/client-products/create", data=product)
    assert res.headers["Location"].split("?")[0].endswith("/accounting/client-products/1")
    client.post("/accounting/vendor-products/create", data={
        "csrf_token": token, "name": "Pallet Kayu Standar Ekspor & Wrapping", "sale_ok": "1", "purchase_ok": "1",
        "product_type": "goods", "is_storable": "1", "list_price": "250000", "sale_tax": "ppn12_dpp",
        "standard_price": "0", "purchase_tax": "ppn12_dpp_in", "default_code": "MAT-PLT-001",
        "weight": "18.5", "volume": "0.2", "sale_delay": "1"
    })
    # Pelanggan > Produk = Penjualan (both); Vendor > Produk = Pembelian (pallet only)
    client_html = client.get("/accounting/client-products").data.decode("utf-8")
    assert "Jasa Trucking FTL Tronton" in client_html
    assert "Pallet Kayu" in client_html
    assert "Rp 18.000.000,00" in client_html
    vendor_html = client.get("/accounting/vendor-products").data.decode("utf-8")
    assert "Pallet Kayu" in vendor_html
    assert "Jasa Trucking FTL Tronton" not in vendor_html
    assert "Jasa Trucking FTL Tronton" in client.get("/accounting/vendor-products?filter=all").data.decode("utf-8")
    # the same product opens under either route
    page = client.get("/accounting/vendor-products/2").data.decode("utf-8")
    for text in ["[MAT-PLT-001] Pallet Kayu", "Informasi Umum", "Stok Persediaan", "Termasuk Pajak", "Log catatan"]:
        assert text in page, text
    assert "Akuntansi</button>" not in page
    assert client.get("/accounting/client-products/2").status_code == 200
    # duplicate reference refused; changes are logged
    client.post("/accounting/client-products/create", data=dict(product, name="Duplikat"))
    assert _db().db_product.find_one({"name": "Duplikat"}) == None
    client.post("/accounting/client-products/1/update", data=dict(product, list_price="19000000"))
    doc = _db().db_product.find_one({"seq": 1})
    assert doc["list_price"] == 19000000
    change = _db().db_record_log.find_one({"model": "product", "record_id": str(doc["_id"]), "kind": "CHANGE"})
    assert "Harga Jual" in [ch["label"] for ch in change["changes"]]
# end def


def test_control_journal_items_and_audit_trail(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    partner = _contact_id("PT Sumber Makmur")
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, partner, {"customer_ref": "JI-INV", "action": "confirm"}))
    inv = _invoices().find_one({"customer_ref": "JI-INV"})
    # confirm writes the ledger: 2 revenue lines + PPN Keluaran + Piutang, balanced
    lines = list(_db().db_journal_item.find({"move_id": str(inv["_id"]), "is_deleted": False}))
    assert len(lines) == 4
    assert round(sum(l["debit"] for l in lines), 2) == 46400000
    assert round(sum(l["credit"] for l in lines), 2) == 46400000
    html = client.get("/accounting/journal-items").data.decode("utf-8")
    for text in ["Item Jurnal", "Terekam", inv["number"], "11210010", "Rp 46.400.000,00"]:
        assert text in html, text
    # account-code tree: 1 > 11, 2 > 21, 4 > 41; a node filters by prefix
    assert "prefix=11" in html
    assert "prefix=41" in html
    assert "11210010" not in client.get("/accounting/journal-items?prefix=4").data.decode("utf-8")
    assert "41000010" in client.get("/accounting/journal-items?prefix=41").data.decode("utf-8")
    # reset to Draft removes the lines; posting again brings them back
    client.post("/accounting/client-invoices/" + str(inv["seq"]) + "/state", data={"csrf_token": token, "action": "reset"})
    assert _db().db_journal_item.count_documents({"move_id": str(inv["_id"]), "is_deleted": False}) == 0
    # a Terekam document without lines (e.g. inserted by a script) is backfilled
    _db().db_invoice.update_one({"_id": inv["_id"]}, {"$set": {"state": "POSTED", "items_posted": False}})
    client.get("/accounting/journal-items")
    assert _db().db_journal_item.count_documents({"move_id": str(inv["_id"]), "is_deleted": False}) == 4
    # Log Catatan: every accounting log entry with the record name + link
    html = client.get("/accounting/audit-trail").data.decode("utf-8")
    assert "Log Catatan" in html
    assert "Faktur " + inv["number"] in html
    assert "telah divalidasi" in html
    assert "/accounting/client-invoices/" + str(inv["seq"]) in html
    assert "Faktur " + inv["number"] not in client.get("/accounting/audit-trail?model=bill").data.decode("utf-8")
# end def


def test_journal_entries_list_and_detail(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    customer = _contact_id("PT Sumber Makmur")
    client.post("/contacts/create", data={"csrf_token": token, "name": "PT Armada Lintas Nusantara", "category": "VENDOR"})
    vendor = _contact_id("PT Armada Lintas Nusantara")
    # faktur 46.400.000 (Terekam) + a draft faktur + tagihan 11.100.000 (Terekam)
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, customer, {"customer_ref": "JE-INV", "action": "confirm"}))
    client.post("/accounting/client-invoices/create", data=_invoice_payload(logged_in, customer, {"customer_ref": "JE-DRAFT"}))
    client.post("/accounting/vendor-bills/create", data={
        "csrf_token": token, "partner_id": vendor, "invoice_date": "2026-11-06", "customer_ref": "JE-BILL",
        "line_product": ["Sewa truk"], "line_account": ["51000010"], "line_quantity": ["1"],
        "line_price": ["10000000"], "line_tax": ["ppn12_dpp_in"], "action": "confirm"
    })
    # default filter = Terekam; totals signed (faktur +, tagihan -)
    html = client.get("/accounting/journal-entries").data.decode("utf-8")
    assert "JE-INV" in html
    assert "JE-BILL" in html
    assert "JE-DRAFT" not in html
    assert "Penjualan" in html
    assert "Pembelian" in html
    assert "Rp -11.100.000,00" in html
    assert "Rp 35.300.000,00" in html
    assert "JE-DRAFT" in client.get("/accounting/journal-entries?state=ALL").data.decode("utf-8")
    assert "JE-INV" not in client.get("/accounting/journal-entries?journal=purchase").data.decode("utf-8")
    # a row opens the document page under the Entri Jurnal breadcrumb
    bill = _invoices().find_one({"customer_ref": "JE-BILL"})
    page = client.get("/accounting/journal-entries/vendor-bills/" + str(bill["seq"])).data.decode("utf-8")
    assert "Entri Jurnal" in page
    assert bill["number"] in page
    assert "Item Jurnal" in page
    assert client.get("/accounting/journal-entries/unknown/1").status_code == 302
# end def


def test_accounting_old_urls_redirect(logged_in):
    client = logged_in["client"]
    res = client.get("/accounting/invoices")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/accounting/client-invoices")
    res = client.get("/accounting/credit-notes/3?print=1")
    assert res.headers["Location"].endswith("/accounting/client-credit-notes/3?print=1")
    assert client.get("/accounting/customer-payments/new").headers["Location"].endswith("/accounting/client-payments/new")
    assert client.get("/accounting/bills").headers["Location"].endswith("/accounting/vendor-bills")
# end def


def test_accounting_customer_and_vendor_lists(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    # Pelanggan > Pelanggan: the Kontak list inside Akuntansi, locked to Klien
    html = client.get("/accounting/contact.CLIENT").data.decode("utf-8")
    assert "Akuntansi" in html
    assert "PT Sumber Makmur" in html
    assert "UD Sidoarjo" not in html
    assert "Klien" in html
    assert "/accounting/contact.CLIENT/new" in html
    assert "PT Sumber Makmur" not in client.get("/accounting/contact.VENDOR").data.decode("utf-8")
    assert client.get("/accounting/contact.DRIVER").status_code == 302
    # create + open + save stay in Akuntansi
    res = client.post("/accounting/contact.CLIENT/create", data={"csrf_token": token, "name": "PT Pelanggan Akuntansi", "category": "CLIENT"})
    assert "/accounting/contact.CLIENT/" in res.headers["Location"]
    contact_id = str(_db().db_contact.find_one({"name": "PT Pelanggan Akuntansi"})["_id"])
    page = client.get("/accounting/contact.CLIENT/" + contact_id).data.decode("utf-8")
    assert "Log catatan" in page
    assert "/accounting/contact.CLIENT/" + contact_id + "/update" in page
    res = client.post("/accounting/contact.CLIENT/" + contact_id + "/update", data={"csrf_token": token, "name": "PT Pelanggan Akuntansi", "category": "CLIENT", "city": "Medan"})
    assert res.headers["Location"].split("?")[0].endswith("/accounting/contact.CLIENT/" + contact_id)
    assert _db().db_contact.find_one({"name": "PT Pelanggan Akuntansi"})["city"] == "Medan"
    # the Kontak app itself is unchanged
    assert "/contacts/new" in client.get("/contacts").data.decode("utf-8")
# end def


def test_invoices_need_accounting_access(logged_in):
    _create_user(logged_in, "staf_tanpa_akun", {"perm_contacts": "full"})
    staf = _login_as("staf_tanpa_akun", "Rahasia123")
    assert staf["client"].get("/accounting/client-invoices").status_code == 302
    staf["client"].post("/accounting/client-invoices/create", data={"csrf_token": staf["token"], "customer_ref": "TIDAK-BOLEH"})
    assert _invoices().find_one({"customer_ref": "TIDAK-BOLEH"}) == None
# end def


def test_accounting_needs_access(logged_in):
    _create_user(logged_in, "staf_kontak", {"perm_contacts": "full"})
    staf = _login_as("staf_kontak", "Rahasia123")
    assert staf["client"].get("/accounting").status_code == 302
    assert "Akuntansi" not in staf["client"].get("/").data.decode("utf-8")
    _create_user(logged_in, "staf_akun", {"perm_accounting": "read"})
    akun = _login_as("staf_akun", "Rahasia123")
    assert akun["client"].get("/accounting").status_code == 200
# end def


def test_all_pages_render(logged_in):
    # Smoke-renders every GET page (catches template syntax errors).
    _seed(logged_in)
    _create_shipment(logged_in, "Malang")
    client = logged_in["client"]
    paths = [
        "/", "/operations", "/shipments", "/shipments/create", "/manifests",
        "/manifests/create", "/hub?hub=Surabaya", "/contacts",
        "/contacts?category=CLIENT", "/fleet", "/users", "/users/new", "/settings", "/accounting", "/accounting/client-invoices",
        "/accounting/client-invoices/new", "/accounting/client-credit-notes", "/accounting/client-credit-notes/new",
        "/accounting/client-payments", "/accounting/client-payments/new",
        "/accounting/vendor-bills", "/accounting/vendor-bills/new", "/accounting/vendor-refunds",
        "/accounting/vendor-refunds/new", "/accounting/vendor-payments", "/accounting/vendor-payments/new",
        "/accounting/journal-entries", "/accounting/journal-entries?state=ALL",
        "/accounting/journal-items", "/accounting/audit-trail",
        "/accounting/client-products", "/accounting/client-products/new",
        "/accounting/vendor-products", "/accounting/vendor-products/new",
        "/accounting/contact.CLIENT", "/accounting/contact.CLIENT/new", "/accounting/contact.VENDOR",
        "/accounting/settings", "/accounting/accounts", "/accounting/accounts/new", "/accounting/taxes",
        "/accounting/taxes/new", "/track"
    ]
    for path in paths:
        res = client.get(path)
        assert res.status_code == 200, path + " -> " + str(res.status_code)
    # end for
# end def


# ---------------------------------------------------------------------------
# Contacts + autocomplete API
# ---------------------------------------------------------------------------

def test_api_contacts_create_returns_id(logged_in):
    res = logged_in["client"].post("/api/contacts", data={
        "csrf_token": logged_in["token"],
        "name": "CV Baru",
        "category": "CLIENT",
        "city": "Bandung"
    })
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["status"] == "SUCCESS"
    assert payload["name"] == "CV Baru"
    assert payload["text"] == "CV Baru (Bandung)"
    found = logged_in["client"].get("/api/contacts?category=CLIENT&q=Baru").get_json()
    assert found["results"][0]["id"] == payload["id"]
# end def


def test_api_contacts_search(logged_in):
    _seed(logged_in)
    res = logged_in["client"].get("/api/contacts?category=CLIENT&q=makmur")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["results"][0]["name"] == "PT Sumber Makmur"
    res = logged_in["client"].get("/api/contacts?category=DRIVER&q=zzz-no-match")
    assert res.get_json()["results"] == []
# end def


def test_contacts_list_pager_and_search(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    html = client.get("/contacts").data.decode("utf-8")
    assert "1-4" in html
    assert "PT Sumber Makmur" in html
    html = client.get("/contacts?q=malang").data.decode("utf-8")
    assert "Toko Jaya Malang" in html
    assert "PT Sumber Makmur" not in html
    res = client.get("/contacts?page=99&per_page=999999")
    assert res.status_code == 200
    assert "1-4" in res.data.decode("utf-8")
# end def


def test_contact_form_saves_sales_and_notes(logged_in):
    client = logged_in["client"]
    res = client.post("/contacts/create", data={
        "csrf_token": logged_in["token"],
        "name": "PT Lintas Toba", "category": "CLIENT",
        "street2": "Blok B", "province": "Sumatera Utara", "postal_code": "22312",
        "tax_id": "01.234.567.8-901.000", "job_title": "Direktur",
        "sale_payment_term": "30 Hari", "sale_payment_method": "Transfer Bank",
        "fiscal_position": "PKP", "industry": "Logistik & Transportasi",
        "notes": "Tagihan dikirim tiap akhir bulan"
    })
    assert res.status_code == 302
    rec = _db().db_contact.find_one({"name": "PT Lintas Toba"})
    assert rec["sale_payment_term"] == "30 Hari"
    assert rec["fiscal_position"] == "PKP"
    assert rec["country"] == "Indonesia"
    assert rec["notes"] == "Tagihan dikirim tiap akhir bulan"
    res = client.get("/contacts/" + str(rec["_id"]) + "/edit")
    assert res.status_code == 200
    assert "Sales &amp; Purchase" in res.data.decode("utf-8")
# end def


def test_contact_form_rejects_unknown_choice(logged_in):
    client = logged_in["client"]
    client.post("/contacts/create", data={
        "csrf_token": logged_in["token"],
        "name": "CV Salah Termin", "category": "CLIENT",
        "sale_payment_term": "999 Hari"
    })
    assert _db().db_contact.find_one({"name": "CV Salah Termin"}) == None
# end def


def test_contact_edit_shows_related_contacts(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/contacts/create", data={"csrf_token": token, "name": "PT Danau Biru", "category": "CLIENT"})
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "Rina Siregar", "category": "CLIENT",
        "company_name": "PT Danau Biru", "job_title": "Finance"
    })
    html = client.get("/contacts/" + _contact_id("PT Danau Biru") + "/edit").data.decode("utf-8")
    assert "Rina Siregar" in html
    assert "Finance" in html
# end def


def test_record_log_create_and_change(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/contacts/create", data={
        "csrf_token": token, "name": "CV Log Danau", "category": "CLIENT", "city": "Medan"
    })
    contact_id = _contact_id("CV Log Danau")
    logs = list(_db().db_record_log.find({"model": "contact", "record_id": contact_id}))
    assert len(logs) == 1
    assert logs[0]["kind"] == "CREATE"
    client.post("/contacts/" + contact_id + "/update", data={
        "csrf_token": token, "name": "CV Log Danau", "category": "VENDOR", "city": "Balige"
    })
    change = _db().db_record_log.find_one({"record_id": contact_id, "kind": "CHANGE"})
    labels = [ch["label"] for ch in change["changes"]]
    assert "Kota" in labels
    assert "Kategori" in labels
    city = [ch for ch in change["changes"] if ch["label"] == "Kota"][0]
    assert city["old"] == "Medan"
    assert city["new"] == "Balige"
    html = client.get("/contacts/" + contact_id + "/edit").data.decode("utf-8")
    assert "Balige" in html
    assert "Log catatan" in html
# end def


def test_record_log_add_note(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/contacts/create", data={"csrf_token": token, "name": "PT Catatan", "category": "CLIENT"})
    contact_id = _contact_id("PT Catatan")
    url = "/log/contact/" + contact_id + "/note"
    res = client.post(url, data={"body": "tanpa token"}, headers={"X-Requested-With": "fetch"})
    assert res.status_code == 400
    res = client.post(url, data={"csrf_token": token, "body": "Klien minta invoice via email"}, headers={"X-Requested-With": "fetch"})
    payload = res.get_json()
    assert payload["status"] == "SUCCESS"
    assert "Klien minta invoice via email" in payload["html"]
    note = _db().db_record_log.find_one({"record_id": contact_id, "kind": "NOTE"})
    assert note["author_name"] == config.G_SUPERADMIN_USERNAME
    res = client.post("/log/unknown/" + contact_id + "/note", data={"csrf_token": token, "body": "x"}, headers={"X-Requested-With": "fetch"})
    assert res.status_code == 400
    html = client.get("/contacts/" + contact_id + "/edit").data.decode("utf-8")
    assert "Klien minta invoice via email" in html
# end def


def test_contacts_bulk_delete(logged_in):
    _seed(logged_in)
    client = logged_in["client"]
    ids = [_contact_id("Toko Jaya Malang"), _contact_id("UD Sidoarjo")]
    res = client.post("/contacts/bulk-delete", data={"ids": ids})
    assert res.status_code == 302
    assert _db().db_contact.count_documents({"category": "RECEIVER", "is_deleted": False}) == 2
    res = client.post("/contacts/bulk-delete", data={
        "csrf_token": logged_in["token"], "ids": ids
    })
    assert res.status_code == 302
    assert _db().db_contact.count_documents({"category": "RECEIVER", "is_deleted": False}) == 0
    assert _db().db_contact.count_documents({"category": "CLIENT", "is_deleted": False}) == 1
# end def


def test_vehicle_plate_unique(logged_in):
    _seed(logged_in)
    res = logged_in["client"].post("/fleet/vehicle/create", data={
        "csrf_token": logged_in["token"],
        "plate_number": "b 9111 uyz", "vehicle_type": "Fuso", "ownership": "INTERNAL"
    })
    assert res.status_code == 302
    assert _db().db_vehicle.count_documents({}) == 2
# end def


# ---------------------------------------------------------------------------
# Order entry (LTL + FTL), AWB generation, initial tracking log
# ---------------------------------------------------------------------------

def test_create_shipment_generates_awb_and_initial_log(logged_in):
    _seed(logged_in)
    _create_shipment(logged_in, "Malang")
    doc = _db().db_shipment.find_one({"destination_city": "Malang"})
    assert re.match(r"^AWB-\d{8}-\d{4}$", doc["tracking_code"]) != None
    assert doc["status_utama"] == "REGISTERED"
    assert doc["current_location"] == "Jakarta"
    assert len(doc["tracking_logs"]) == 1
    assert doc["tracking_logs"][0]["milestone_status"] == "ORDER_REGISTERED"
    assert "gudang asal" in doc["tracking_logs"][0]["notes"]
# end def


def test_create_shipment_requires_real_contacts(logged_in):
    _seed(logged_in)
    res = logged_in["client"].post("/shipments/create", data={
        "csrf_token": logged_in["token"],
        "service_type": "LTL",
        "sender_id": "000000000000000000000000",
        "receiver_id": "000000000000000000000000",
        "origin_city": "Jakarta",
        "destination_city": "Malang"
    }, follow_redirects=False)
    assert res.status_code == 302
    assert _db().db_shipment.count_documents({}) == 0
# end def


# ---------------------------------------------------------------------------
# Consolidated manifest + bulk update_many/$push tracking
# ---------------------------------------------------------------------------

def _make_trunk_manifest(logged_in):
    _seed(logged_in)
    _create_shipment(logged_in, "Malang")                        # through cargo
    _create_shipment(logged_in, "Surabaya", po_number="PO-2026-0001")
    mlg = _db().db_shipment.find_one({"destination_city": "Malang"})
    sby = _db().db_shipment.find_one({"destination_city": "Surabaya"})
    res = logged_in["client"].post("/manifests/create", data={
        "csrf_token": logged_in["token"],
        "origin": "Jakarta",
        "destination": "Surabaya",
        "vehicle_id": _vehicle_id("B 9111 UYZ"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(mlg["_id"]), str(sby["_id"])]
    })
    assert res.status_code == 302
    manifest = _db().db_manifest.find_one({})
    assert re.match(r"^MAN-\d{8}-\d{4}$", manifest["manifest_code"]) != None
    assert manifest["status"] == "PLANNED"
    return manifest["manifest_code"], mlg["tracking_code"], sby["tracking_code"]
# end def


def test_manifest_creation_pushes_consolidation_log(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    for awb in [awb_mlg, awb_sby]:
        doc = _shipment_doc(awb)
        assert doc["status_utama"] == "MANIFESTED"
        assert doc["active_manifest_code"] == manifest_code
        assert len(doc["tracking_logs"]) == 2  # ORDER_REGISTERED + CONSOLIDATED
        assert doc["tracking_logs"][1]["milestone_status"] == "CONSOLIDATED"
        assert manifest_code in doc["tracking_logs"][1]["notes"]
    # end for
# end def


def test_manifest_status_updates_push_to_all_shipments(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]

    # IN_TRANSIT — one update_many, both shipments get the same milestone
    client.post("/manifests/" + manifest_code + "/update", data={
        "csrf_token": logged_in["token"], "status": "IN_TRANSIT",
        "location": "Cikampek", "notes": ""
    })
    for awb in [awb_mlg, awb_sby]:
        doc = _shipment_doc(awb)
        assert doc["status_utama"] == "IN_TRANSIT"
        assert doc["tracking_logs"][-1]["milestone_status"] == "IN_TRANSIT"
        assert doc["tracking_logs"][-1]["location"] == "Cikampek"
    # end for

    # ARRIVED at the Surabaya hub
    client.post("/manifests/" + manifest_code + "/update", data={
        "csrf_token": logged_in["token"], "status": "ARRIVED",
        "location": "Surabaya", "notes": ""
    })
    for awb in [awb_mlg, awb_sby]:
        doc = _shipment_doc(awb)
        assert doc["status_utama"] == "ARRIVED_HUB"
        assert doc["current_location"] == "Surabaya"
        assert len(doc["tracking_logs"]) == 4
    # end for

    # forward-only transitions are enforced
    res = client.post("/manifests/" + manifest_code + "/update", data={
        "csrf_token": logged_in["token"], "status": "IN_TRANSIT",
        "location": "nowhere", "notes": ""
    })
    assert res.status_code == 302
    assert len(_shipment_doc(awb_mlg)["tracking_logs"]) == 4
# end def


def test_completion_delivers_local_cargo_holds_through_cargo(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]
    for status in ["IN_TRANSIT", "ARRIVED", "COMPLETED"]:
        client.post("/manifests/" + manifest_code + "/update", data={
            "csrf_token": logged_in["token"], "status": status,
            "location": "Surabaya", "notes": ""
        })
    # end for
    # Both stay at the hub. Surabaya cargo waits for antar; Malang cargo waits for a feeder.
    sby_doc = _shipment_doc(awb_sby)
    mlg_doc = _shipment_doc(awb_mlg)
    assert sby_doc["status_utama"] == "ARRIVED_HUB"
    assert "siap diantar" in sby_doc["tracking_logs"][-1]["notes"]
    assert mlg_doc["status_utama"] == "ARRIVED_HUB"
    assert mlg_doc["current_location"] == "Surabaya"
    assert mlg_doc["active_manifest_code"] == ""
# end def


def test_journey_click_moves_truck_hub_by_hub(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    _db().db_manifest.update_one(
        {"manifest_code": manifest_code},
        {"$set": {"hub_names": ["Jakarta", "Semarang", "Surabaya"]}}
    )
    client = logged_in["client"]
    token = logged_in["token"]
    page = client.get("/manifests/detail/" + manifest_code)
    html = page.data.decode("utf-8")
    assert page.status_code == 200
    assert "Berangkat" in html
    assert "Semarang" in html
    assert "Di Jakarta" in html

    def step():
        res = client.post("/manifests/" + manifest_code + "/advance", data={
            "csrf_token": token
        })
        assert res.status_code == 302
        return _db().db_manifest.find_one({"manifest_code": manifest_code})
    # end def

    doc = step()
    assert doc["status"] == "IN_TRANSIT"
    assert doc["on_road"] == True
    assert doc["stop_index"] == 0
    assert doc["last_location"] == "Menuju Semarang"
    moving = client.get("/manifests/detail/" + manifest_code).data.decode("utf-8")
    assert "Dalam perjalanan menuju Semarang" in moving
    assert "Klik untuk tiba" in moving

    doc = step()
    assert doc["status"] == "IN_TRANSIT"
    assert doc["on_road"] == False
    assert doc["stop_index"] == 1
    assert doc["last_location"] == "Semarang"
    parked = _shipment_doc(awb_sby)
    assert parked["status_utama"] == "IN_TRANSIT"
    assert parked["current_location"] == "Semarang"
    assert parked["tracking_logs"][-1]["milestone_status"] == "ARRIVED_HUB"

    doc = step()
    assert doc["on_road"] == True
    assert doc["stop_index"] == 1
    assert doc["last_location"] == "Menuju Surabaya"
    assert _shipment_doc(awb_sby)["status_utama"] == "IN_TRANSIT"

    doc = step()
    assert doc["status"] == "ARRIVED"
    assert doc["on_road"] == False
    assert doc["stop_index"] == 2
    assert _shipment_doc(awb_sby)["status_utama"] == "ARRIVED_HUB"
    arrived = client.get("/manifests/detail/" + manifest_code).data.decode("utf-8")
    assert "Selesaikan perjalanan" in arrived

    doc = step()
    assert doc["status"] == "COMPLETED"
    assert _shipment_doc(awb_sby)["status_utama"] == "ARRIVED_HUB"
    assert _shipment_doc(awb_mlg)["status_utama"] == "ARRIVED_HUB"
# end def


def test_journey_click_steps_back(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    _db().db_manifest.update_one(
        {"manifest_code": manifest_code},
        {"$set": {"hub_names": ["Jakarta", "Semarang", "Surabaya"]}}
    )
    client = logged_in["client"]
    token = logged_in["token"]

    def move(step):
        res = client.post("/manifests/" + manifest_code + "/advance", data={
            "csrf_token": token, "step": step
        })
        assert res.status_code == 302
        return _db().db_manifest.find_one({"manifest_code": manifest_code})
    # end def

    doc = move("forward")
    assert doc["status"] == "IN_TRANSIT"
    assert doc["on_road"] == True
    road = client.get("/manifests/detail/" + manifest_code).data.decode("utf-8")
    assert "Kembali ke Jakarta" in road

    doc = move("back")
    assert doc["status"] == "PLANNED"
    assert doc["on_road"] == False
    assert doc["stop_index"] == 0
    assert doc["last_location"] == "Jakarta"
    cargo = _shipment_doc(awb_sby)
    assert cargo["status_utama"] == "MANIFESTED"
    assert cargo["current_location"] == "Jakarta"
    assert cargo["tracking_logs"][-1]["milestone_status"] == "CONSOLIDATED"

    for _ in range(5):
        move("forward")
    # end for
    assert _db().db_manifest.find_one({"manifest_code": manifest_code})["status"] == "COMPLETED"
    assert _shipment_doc(awb_sby)["status_utama"] == "ARRIVED_HUB"
    assert _shipment_doc(awb_mlg)["active_manifest_code"] == ""

    doc = move("back")
    assert doc["status"] == "ARRIVED"
    assert doc["on_road"] == False
    assert doc["stop_index"] == 2
    assert _shipment_doc(awb_sby)["status_utama"] == "ARRIVED_HUB"
    assert _shipment_doc(awb_sby)["active_manifest_code"] == manifest_code
    assert _shipment_doc(awb_mlg)["active_manifest_code"] == manifest_code
    assert _shipment_doc(awb_sby)["tracking_logs"][-1]["milestone_status"] == "ARRIVED_HUB"

    doc = move("back")
    assert doc["status"] == "IN_TRANSIT"
    assert doc["on_road"] == True
    assert doc["stop_index"] == 1
    assert doc["last_location"] == "Menuju Surabaya"
    assert _shipment_doc(awb_sby)["status_utama"] == "IN_TRANSIT"

    doc = move("back")
    assert doc["on_road"] == False
    assert doc["stop_index"] == 1
    assert doc["last_location"] == "Semarang"
    parked = client.get("/manifests/detail/" + manifest_code).data.decode("utf-8")
    assert "Kembali ke jalur menuju Semarang" in parked

    doc = move("back")
    assert doc["on_road"] == True
    assert doc["stop_index"] == 0
    doc = move("back")
    assert doc["status"] == "PLANNED"
    assert len(_shipment_doc(awb_sby)["tracking_logs"]) == 2
    assert len(_shipment_doc(awb_mlg)["tracking_logs"]) == 2
# end def


# ---------------------------------------------------------------------------
# Deconsolidation & re-manifesting (transit hub sorting)
# ---------------------------------------------------------------------------

def test_hub_filter_and_feeder_manifest(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]
    for status in ["IN_TRANSIT", "ARRIVED"]:
        client.post("/manifests/" + manifest_code + "/update", data={
            "csrf_token": logged_in["token"], "status": status,
            "location": "Surabaya", "notes": ""
        })
    # end for

    # Hub page: cargo parked at Surabaya, only the Malang-bound piece matches
    res = client.get("/hub?hub=Surabaya&destination=Malang")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert awb_mlg in html
    assert awb_sby not in html

    # Feeder manifest Surabaya -> Malang with the selected shipment
    mlg = _shipment_doc(awb_mlg)
    res = client.post("/manifests/create", data={
        "csrf_token": logged_in["token"],
        "origin": "Surabaya",
        "destination": "Malang",
        "vehicle_id": _vehicle_id("L 8888 AB"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(mlg["_id"])]
    })
    assert res.status_code == 302
    mlg = _shipment_doc(awb_mlg)
    assert mlg["status_utama"] == "MANIFESTED"
    # registered + trunk consolidated + in transit + arrived hub + feeder consolidated
    assert len(mlg["tracking_logs"]) == 5

    feeder_code = mlg["active_manifest_code"]
    for status in ["IN_TRANSIT", "ARRIVED", "COMPLETED"]:
        client.post("/manifests/" + feeder_code + "/update", data={
            "csrf_token": logged_in["token"], "status": status,
            "location": "Malang", "notes": ""
        })
    # end for
    mlg = _shipment_doc(awb_mlg)
    assert mlg["status_utama"] == "ARRIVED_HUB"
    assert mlg["current_location"] == "Malang"
    res = client.post("/hub/antar", data={
        "csrf_token": logged_in["token"],
        "hub": "Malang",
        "vehicle_id": _vehicle_id("L 8888 AB"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(mlg["_id"])]
    })
    assert res.status_code == 302
    mlg = _shipment_doc(awb_mlg)
    assert mlg["status_utama"] == "OUT_FOR_DELIVERY"
    res = client.post("/hub/antar/" + mlg["active_delivery_code"] + "/deliver", data={
        "csrf_token": logged_in["token"],
        "hub": "Malang",
        "shipment_id": str(mlg["_id"]),
        "received_by": "Siti Aminah"
    })
    assert res.status_code == 302
    mlg = _shipment_doc(awb_mlg)
    assert mlg["status_utama"] == "DELIVERED"
    assert mlg["tracking_logs"][-1]["milestone_status"] == "DELIVERED"
    assert "Siti Aminah" in mlg["tracking_logs"][-1]["notes"]
# end def


def test_hub_antar_rejects_feeder_cargo_and_records_a_failed_attempt(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    for status in ["IN_TRANSIT", "ARRIVED", "COMPLETED"]:
        client.post("/manifests/" + manifest_code + "/update", data={
            "csrf_token": token, "status": status, "location": "Surabaya", "notes": ""
        })
    # end for
    page = client.get("/hub?hub=Surabaya")
    html = page.data.decode("utf-8")
    assert "Kirim antar" in html
    assert awb_sby in html
    assert "Feeder ke kota lain" in html
    mlg = _shipment_doc(awb_mlg)
    res = client.post("/hub/antar", data={
        "csrf_token": token,
        "hub": "Surabaya",
        "vehicle_id": _vehicle_id("B 9111 UYZ"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(mlg["_id"])]
    })
    assert res.status_code == 302
    assert "error=" in res.headers.get("Location", "")
    assert _shipment_doc(awb_mlg)["status_utama"] == "ARRIVED_HUB"

    sby = _shipment_doc(awb_sby)
    res = client.post("/hub/antar", data={
        "csrf_token": token,
        "hub": "Surabaya",
        "vehicle_id": _vehicle_id("B 9111 UYZ"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(sby["_id"])]
    })
    assert res.status_code == 302
    sby = _shipment_doc(awb_sby)
    assert sby["status_utama"] == "OUT_FOR_DELIVERY"
    code = sby["active_delivery_code"]
    running = client.get("/hub?hub=Surabaya").data.decode("utf-8")
    assert "Diterima" in running
    assert code in running
    client.post("/hub/antar/" + code + "/fail", data={
        "csrf_token": token,
        "hub": "Surabaya",
        "shipment_id": str(sby["_id"]),
        "reason": "Penerima tidak ada"
    })
    sby = _shipment_doc(awb_sby)
    assert sby["status_utama"] == "ARRIVED_HUB"
    assert sby["active_delivery_code"] == ""
    assert "Penerima tidak ada" in sby["tracking_logs"][-1]["notes"]
    stored = _db().db_delivery.find_one({"delivery_code": code})
    assert stored["status"] == "CLOSED"
# end def


def test_delete_manifest_returns_orders_from_transit_and_finished(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]

    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client.post("/manifests/" + manifest_code + "/update", data={
        "csrf_token": token, "status": "IN_TRANSIT", "location": "Cikampek", "notes": ""
    })
    res = client.post("/manifests/" + manifest_code + "/delete", data={"csrf_token": token})
    assert res.status_code == 302
    moving = _shipment_doc(awb_sby)
    assert moving["status_utama"] == "REGISTERED"
    assert moving["active_manifest_code"] == ""
    assert moving["current_location"] == moving["origin_city"]
    assert manifest_code not in (moving["tracking_logs"][-1].get("notes") or "")
    stored = _db().db_manifest.find_one({"manifest_code": manifest_code})
    assert stored["is_deleted"] == True
# end def


def test_delete_finished_manifest_returns_delivered_orders(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    for status in ["IN_TRANSIT", "ARRIVED", "COMPLETED"]:
        client.post("/manifests/" + manifest_code + "/update", data={
            "csrf_token": token, "status": status, "location": "Surabaya", "notes": ""
        })
    # end for
    assert _shipment_doc(awb_sby)["status_utama"] == "ARRIVED_HUB"
    client.post("/manifests/" + manifest_code + "/delete", data={"csrf_token": token})
    finished = _shipment_doc(awb_sby)
    held = _shipment_doc(awb_mlg)
    assert finished["status_utama"] == "REGISTERED"
    assert held["status_utama"] == "REGISTERED"
    assert finished["active_manifest_code"] == ""
    assert manifest_code not in "".join([log.get("notes") or "" for log in finished["tracking_logs"]])
# end def


def test_delete_finished_manifest_keeps_orders_on_a_newer_manifest(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]
    token = logged_in["token"]
    for status in ["IN_TRANSIT", "ARRIVED", "COMPLETED"]:
        client.post("/manifests/" + manifest_code + "/update", data={
            "csrf_token": token, "status": status, "location": "Surabaya", "notes": ""
        })
    # end for
    mlg = _shipment_doc(awb_mlg)
    res = client.post("/manifests/create", data={
        "csrf_token": token,
        "origin": "Surabaya",
        "destination": "Malang",
        "vehicle_id": _vehicle_id("L 8888 AB"),
        "driver_id": _driver_id("SIM-JIH-991"),
        "shipment_ids": [str(mlg["_id"])]
    })
    assert res.status_code == 302
    feeder_code = _shipment_doc(awb_mlg)["active_manifest_code"]
    client.post("/manifests/" + manifest_code + "/delete", data={"csrf_token": token})
    mlg = _shipment_doc(awb_mlg)
    assert mlg["status_utama"] == "MANIFESTED"
    assert mlg["active_manifest_code"] == feeder_code
    assert _shipment_doc(awb_sby)["status_utama"] == "REGISTERED"
# end def


# ---------------------------------------------------------------------------
# Public tracking API (by AWB and by PO number)
# ---------------------------------------------------------------------------

def test_public_track_page_and_api(logged_in):
    manifest_code, awb_mlg, awb_sby = _make_trunk_manifest(logged_in)
    client = logged_in["client"]
    client.post("/manifests/" + manifest_code + "/update", data={
        "csrf_token": logged_in["token"], "status": "IN_TRANSIT",
        "location": "Cikampek", "notes": ""
    })

    # tracking is public — no session needed
    fresh = server.app.test_client()
    res = fresh.get("/track?q=" + awb_sby)
    assert res.status_code == 200
    assert awb_sby.encode() in res.data

    # by tracking_code
    res = fresh.get("/api/track?q=" + awb_sby)
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["status"] == "SUCCESS"
    assert payload["data"]["shipment"]["po_number"] == "PO-2026-0001"
    logs = payload["data"]["tracking_logs"]
    assert len(logs) == 3  # registered + consolidated + in transit
    stamps = [log["timestamp"] for log in logs]
    assert stamps == sorted(stamps)  # chronological
    assert "updated_by" not in logs[0]  # internal field stripped

    # by po_number
    res = fresh.get("/api/track?q=PO-2026-0001")
    assert res.status_code == 200
    assert res.get_json()["data"]["shipment"]["tracking_code"] == awb_sby

    # unknown query
    res = fresh.get("/api/track?q=NOPE-123")
    assert res.status_code == 404
# end def


def test_route_request_keeps_a_route_with_the_hubs():
    from ai.ai_proc import _attach_route
    text = "tolong buat rute dari surabaya ke bali, dan tolong tambahkan 3 transit"
    proposals, added = _attach_route([
        {"tool": "create_hub", "arguments": {"name": "Surabaya Hub"}, "summary": "Surabaya Hub"},
        {"tool": "create_hub", "arguments": {"name": "Probolinggo Hub"}, "summary": "Probolinggo Hub"},
        {"tool": "create_hub", "arguments": {"name": "Situbondo Hub"}, "summary": "Situbondo Hub"},
        {"tool": "create_hub", "arguments": {"name": "Banyuwangi Hub"}, "summary": "Banyuwangi Hub"},
        {"tool": "create_hub", "arguments": {"name": "Denpasar Hub"}, "summary": "Denpasar Hub"}
    ], text)
    assert added == True
    route = proposals[-1]
    assert route["tool"] == "create_route"
    assert route["arguments"]["stops"][0] == "Surabaya Hub"
    assert route["arguments"]["stops"][-1] == "Denpasar Hub"
    assert len(route["arguments"]["stops"]) == 5
    again, added_again = _attach_route(proposals, text)
    assert added_again == False
    assert len(again) == len(proposals)
# end def


def test_three_transit_cities_need_five_stops():
    from ai.ai_proc import _asked_transits, _route_needs_more_stops
    text = "tolong buat rute dari surabaya ke bali, dan tolong tambahkan 3 transit 3 kota di antara surabaya dan bali"
    assert _asked_transits(text) == 3
    short = [{"tool": "create_route", "arguments": {"stops": ["Surabaya Hub", "Malang Hub", "Jember Hub", "Denpasar Hub"]}}]
    assert _route_needs_more_stops(short, text) == True
    full = [{"tool": "create_route", "arguments": {"stops": ["Surabaya Hub", "Probolinggo Hub", "Situbondo Hub", "Banyuwangi Hub", "Denpasar Hub"]}}]
    assert _route_needs_more_stops(full, text) == False
# end def


def test_create_route_by_stops_links_existing_hubs(logged_in):
    from manifests.manifests_proc import manifests_proc
    _seed(logged_in)
    proc = manifests_proc()
    for name in ("Surabaya Hub", "Probolinggo Hub", "Banyuwangi Hub", "Denpasar Hub"):
        made = proc.create_hub({"name": name})
        assert made["status"] == "SUCCESS"
    # end for
    result = proc.create_route_by_stops({
        "name": "Surabaya ke Bali",
        "stops": ["Surabaya", "Probolinggo", "Banyuwangi", "Bali"]
    })
    assert result["status"] == "SUCCESS"
    saved = _db().db_route.find_one({"name": "Surabaya ke Bali", "is_deleted": False})
    assert saved["hub_names"] == ["Surabaya Hub", "Probolinggo Hub", "Banyuwangi Hub", "Denpasar Hub"]
    assert saved["vehicle_id"] == _vehicle_id("B 9111 UYZ")
    assert saved["driver_id"] == _driver_id("SIM-JIH-991")
# end def


def test_bali_is_kept_when_denpasar_is_already_on_the_route(logged_in):
    from manifests.manifests_proc import manifests_proc
    _seed(logged_in)
    proc = manifests_proc()
    for name in ("Surabaya Hub", "Malang Hub", "Jember Hub", "Denpasar Hub"):
        made = proc.create_hub({"name": name})
        assert made["status"] == "SUCCESS"
    # end for
    result = proc.create_route_by_stops({
        "name": "Surabaya ke Bali",
        "stops": ["Surabaya Hub", "Malang Hub", "Jember Hub", "Denpasar Hub", "Bali Hub"]
    })
    assert result["status"] == "SUCCESS"
    saved = _db().db_route.find_one({"name": "Surabaya ke Bali", "is_deleted": False})
    assert saved["hub_names"][-2] == "Denpasar Hub"
    assert saved["hub_names"][-1] == "Bali Hub"
# end def
