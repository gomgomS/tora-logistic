import os
import sys

# Tests run against a scratch database so local data is never touched
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

def _get_csrf_token(client):
    html = client.get("/sample/").data.decode("utf-8")
    marker = 'name="csrf_token" value="'
    start = html.find(marker) + len(marker)
    end = html.find('"', start)
    return html[start:end]
# end def

def test_index_empty(client):
    res = client.get("/sample/")
    assert res.status_code == 200
    assert "No items yet" in res.data.decode("utf-8")
# end def

def test_create_requires_csrf_token(client):
    res = client.post("/sample/sample/create", data={"title": "No token"})
    assert res.status_code == 302
    res = client.get("/sample/")
    assert "No token" not in res.data.decode("utf-8")
# end def

def test_create_item(client):
    token = _get_csrf_token(client)
    res = client.post("/sample/sample/create", data={
        "csrf_token": token,
        "title": "First item",
        "body": "Created by the test suite"
    })
    assert res.status_code == 302
    res = client.get("/sample/")
    html = res.data.decode("utf-8")
    assert "First item" in html
    assert "Created by the test suite" in html
# end def

def test_create_sanitizes_input(client):
    token = _get_csrf_token(client)
    client.post("/sample/sample/create", data={
        "csrf_token": token,
        "title": "Hi <script>alert(1)</script>"
    })
    res = client.get("/sample/")
    html = res.data.decode("utf-8")
    assert "<script>" not in html
    assert "Hi &amp;lt;script&amp;gt;" in html
# end def

def test_empty_title_is_rejected(client):
    token = _get_csrf_token(client)
    res = client.post("/sample/sample/create", data={"csrf_token": token, "title": ""})
    assert res.status_code == 302
    res = client.get("/sample/")
    assert "No items yet" in res.data.decode("utf-8")
# end def

def test_detail_and_soft_delete(client):
    token = _get_csrf_token(client)
    client.post("/sample/sample/create", data={
        "csrf_token": token,
        "title": "Delete me"
    })
    res = client.get("/sample/sample/delete-me")
    assert res.status_code == 200

    res = client.post("/sample/sample/delete/delete-me", data={"csrf_token": token})
    assert res.status_code == 302

    res = client.get("/sample/sample/delete-me")
    assert res.status_code == 404
    res = client.get("/sample/")
    assert "Delete me" not in res.data.decode("utf-8")

    db = database.get_db_conn(config.mainDB)
    doc = db.db_sample_item.find_one({"slug": "delete-me"})
    assert doc != None
    assert doc["is_deleted"] == True
# end def
