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
    for path in ["/", "/shipments", "/manifests", "/hub", "/contacts", "/fleet"]:
        res = client.get(path)
        assert res.status_code == 302
        assert "/login" in res.headers.get("Location", "")
    # end for
# end def


def test_login_and_dashboard(logged_in):
    res = logged_in["client"].get("/")
    assert res.status_code == 200
    assert b"Dasbor" in res.data
# end def


def test_users_page_is_superadmin_only(logged_in):
    res = logged_in["client"].get("/users")
    assert res.status_code == 200
    assert config.G_SUPERADMIN_USERNAME in res.data.decode("utf-8")
# end def


def test_all_pages_render(logged_in):
    # Smoke-renders every GET page (catches template syntax errors).
    _seed(logged_in)
    _create_shipment(logged_in, "Malang")
    client = logged_in["client"]
    paths = [
        "/", "/shipments", "/shipments/create", "/manifests",
        "/manifests/create", "/hub?hub=Surabaya", "/contacts",
        "/contacts?category=CLIENT", "/fleet", "/users", "/track"
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
