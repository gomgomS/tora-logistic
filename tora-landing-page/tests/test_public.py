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


def test_home_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    # hero, services, steps and coverage sections all present
    for marker in ["LTL Konsolidasi", "FTL Charter", "Cara Kerja", "Jangkauan", "/track"]:
        assert marker in html
    # end for
# end def


def test_track_page_renders(client):
    res = client.get("/track")
    assert res.status_code == 200
    assert "Lacak Kiriman" in res.data.decode("utf-8")
# end def
