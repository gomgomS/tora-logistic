import os
import sys

os.environ["MONGO_DB_NAME"] = "slapz_test"

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


def _token_from(html):
    marker = 'name="csrf_token" value="'
    start = html.find(marker) + len(marker)
    end = html.find('"', start)
    return html[start:end]
# end def


@pytest.fixture()
def logged_in(client):
    html = client.get("/login").data.decode("utf-8")
    token = _token_from(html)
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


def test_login_required(client):
    res = client.get("/orders")
    assert res.status_code == 302
    assert "/login" in (res.headers.get("Location") or "")
# end def


def test_login_page_renders(client):
    res = client.get("/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Masuk" in html
    assert config.G_SUPERADMIN_USERNAME in html
# end def


def test_login_and_order_list(logged_in):
    res = logged_in["client"].get("/orders")
    assert res.status_code == 200
    assert "Belum ada order" in res.data.decode("utf-8")
# end def


def test_route_creates_hubs_inline(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    res = client.post("/routes/create", data={
        "csrf_token": token,
        "name": "Surabaya ke Malang",
        "hub_names": ["Surabaya Hub", "Pasuruan Hub", "Malang Hub"]
    })
    assert res.status_code == 302
    page = client.get("/routes").data.decode("utf-8")
    assert "Surabaya ke Malang" in page
    assert "Pasuruan Hub" in page
    hubs = list(_db().db_hub.find({"is_deleted": False}))
    names = [h["name"] for h in hubs]
    assert "Surabaya Hub" in names
    assert "Malang Hub" in names
# end def


def test_order_journey_move_and_insert_hub(logged_in):
    client = logged_in["client"]
    token = logged_in["token"]
    client.post("/routes/create", data={
        "csrf_token": token,
        "name": "Jakarta ke Surabaya",
        "hub_names": ["Gudang Jakarta", "Surabaya Hub"]
    })
    route = _db().db_route.find_one({"name": "Jakarta ke Surabaya"})
    res = client.post("/orders/create", data={
        "csrf_token": token,
        "sender_name": "Andi",
        "receiver_name": "Siti",
        "route_id": str(route["_id"])
    })
    assert res.status_code == 302
    loc = res.headers.get("Location") or ""
    assert "/orders/detail/" in loc
    code = loc.split("/orders/detail/")[-1].split("?")[0]
    page = client.get("/orders/detail/" + code)
    html = page.data.decode("utf-8")
    assert "Gudang Jakarta" in html
    assert "Surabaya Hub" in html
    assert "Berangkat" in html
    assert "Sisip" in html
    assert "Bongkar muat" in html
    assert "Istirahat" in html
    assert "Tunggu muatan" in html
    assert "cth: Bongkar muat" in html
    assert "Catat" in html

    res = client.post("/orders/" + code + "/stop-event", data={
        "csrf_token": token,
        "stop_index": "0",
        "event_note": "Bongkar muat"
    })
    assert res.status_code == 302
    order = _db().db_order.find_one({"tracking_code": code})
    notes = [log.get("notes") for log in order.get("tracking_logs") or []]
    assert "Bongkar muat di Gudang Jakarta" in notes

    res = client.post("/orders/" + code + "/stop-event", data={
        "csrf_token": token,
        "stop_index": "0",
        "event_note": "Cek colly"
    })
    assert res.status_code == 302
    order = _db().db_order.find_one({"tracking_code": code})
    notes = [log.get("notes") for log in order.get("tracking_logs") or []]
    assert "Cek colly di Gudang Jakarta" in notes

    client.post("/orders/" + code + "/advance", data={
        "csrf_token": token, "step": "forward"
    })
    order = _db().db_order.find_one({"tracking_code": code})
    assert order["status"] == "IN_TRANSIT"
    assert order["on_road"] == True

    client.post("/orders/" + code + "/insert-hub", data={
        "csrf_token": token,
        "after_index": "0",
        "hub_name": "Cirebon Hub"
    })
    order = _db().db_order.find_one({"tracking_code": code})
    assert order["hub_names"] == ["Gudang Jakarta", "Cirebon Hub", "Surabaya Hub"]
    assert order["on_road"] == True
    assert order["stop_index"] == 0
    assert order["current_location"] == "Menuju Cirebon Hub"
    notes = [log.get("notes") for log in order.get("tracking_logs") or []]
    assert "Berangkat dari Gudang Jakarta menuju Cirebon Hub" in notes
    assert "Berangkat dari Gudang Jakarta menuju Surabaya Hub" not in notes
    assert "Bongkar muat di Gudang Jakarta" in notes
    assert _db().db_hub.find_one({"name": "Cirebon Hub", "is_deleted": False}) != None

    page = client.get("/orders/detail/" + code).data.decode("utf-8")
    assert "Cirebon Hub" in page
    assert "Dalam perjalanan menuju Cirebon Hub" in page
    assert "Berangkat dari Gudang Jakarta menuju Cirebon Hub" in page
    assert "Segarkan" in page

    _db().db_order.update_one(
        {"tracking_code": code},
        {"$set": {
            "current_location": "Menuju Surabaya Hub",
            "tracking_logs": [
                {
                    "milestone_status": "REGISTERED",
                    "location": "Gudang Jakarta",
                    "notes": "Order diterima. Kiriman di Gudang Jakarta",
                    "updated_by": "t",
                    "timestamp": "2026-10-19 16:24:50"
                },
                {
                    "milestone_status": "REGISTERED",
                    "location": "Gudang Jakarta",
                    "notes": "Bongkar muat di Gudang Jakarta",
                    "updated_by": "t",
                    "timestamp": "2026-10-19 16:24:58",
                    "event": "BONGKAR_MUAT",
                    "stop_name": "Gudang Jakarta"
                },
                {
                    "milestone_status": "IN_TRANSIT",
                    "location": "Menuju Surabaya Hub",
                    "notes": "Berangkat dari Gudang Jakarta menuju Surabaya Hub",
                    "updated_by": "t",
                    "timestamp": "2026-10-19 16:25:17"
                }
            ]
        }}
    )
    res = client.post("/orders/" + code + "/refresh-riwayat", data={
        "csrf_token": token
    })
    assert res.status_code == 302
    order = _db().db_order.find_one({"tracking_code": code})
    assert order["current_location"] == "Menuju Cirebon Hub"
    notes = [log.get("notes") for log in order.get("tracking_logs") or []]
    assert "Berangkat dari Gudang Jakarta menuju Cirebon Hub" in notes
    assert "Berangkat dari Gudang Jakarta menuju Surabaya Hub" not in notes
    assert "Bongkar muat di Gudang Jakarta" in notes
    page = client.get("/orders/detail/" + code).data.decode("utf-8")
    assert "Berangkat dari Gudang Jakarta menuju Cirebon Hub" in page
    assert "Menuju Cirebon Hub" in page
    assert "Bongkar muat di Gudang Jakarta" in page
# end def
