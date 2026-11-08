# Example: a complete feature module (HTML page + JSON API)

A worked example of adding a `tariffs` feature (shipping rate card) to the
ERP portal. It shows every layer end to end. Real references:
`slapz102_modules/sample/` (minimal) and `slapz102_modules/contacts/` (ERP
with login + JSON API).

Files created or touched:

```
slapz102_core/model.py                               + db_tariff schema
slapz102_modules/tariffs/tariffs_proc.py             business logic
slapz102_modules/tariffs/tariffs_blueprint.py        routes
slapz102_modules/view/tariffs/view_tariffs.py        request/response glue
templates/tariffs.html                               page
server.py                                            + import + register
tests/test_tariffs.py                                tests
```

## 1. Schema — `slapz102_core/model.py`

```python
"db_tariff": {
    "origin_city": "",
    "destination_city": "",
    "service_type": "LTL",
    "price_per_kg": 0,
    "min_weight_kg": 0
},
```

## 2. Proc — `slapz102_modules/tariffs/tariffs_proc.py`

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from bson.objectid import ObjectId

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# TARIFFS MODULE — business logic layer.
#
# Rate card per origin/destination/service, used to quote order prices.
# ---------------------------------------------------------------------------

SERVICE_TYPES = ["LTL", "FTL"]


def _to_number(value):
    try:
        return float(value)
    except Exception:
        return None
    # end try
# end def


class tariffs_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _tariff_public(self, doc):
        doc["id"] = str(doc.pop("_id"))
        return doc
    # end def

    def list_tariffs(self):
        recs = list(self.mgdDB.db_tariff.find(
            {"is_deleted": False}
        ).sort([("origin_city", 1), ("destination_city", 1)]))
        out = []
        for rec in recs:
            out.append(self._tariff_public(rec))
        # end for
        return out
    # end def

    def get_tariff(self, tariff_id):
        try:
            oid = ObjectId(tariff_id)
        except Exception:
            return None
        # end try
        rec = self.mgdDB.db_tariff.find_one({"_id": oid, "is_deleted": False})
        if rec == None:
            return None
        # end if
        return self._tariff_public(rec)
    # end def

    def create_tariff(self, params):
        origin = (params.get("origin_city") or "").strip()
        destination = (params.get("destination_city") or "").strip()
        service = (params.get("service_type") or "").strip().upper()
        price = _to_number(params.get("price_per_kg"))
        if origin == "" or destination == "":
            return {"status": "ERROR", "desc": "Kota asal dan tujuan wajib diisi"}
        # end if
        if service not in SERVICE_TYPES:
            return {"status": "ERROR", "desc": "Layanan harus LTL atau FTL"}
        # end if
        if price == None or price <= 0:
            return {"status": "ERROR", "desc": "Harga per kg harus lebih dari 0"}
        # end if
        rec = database.new(self.mgdDB, "db_tariff")
        rec.put("origin_city", origin)
        rec.put("destination_city", destination)
        rec.put("service_type", service)
        rec.put("price_per_kg", price)
        rec.put("min_weight_kg", _to_number(params.get("min_weight_kg")) or 0)
        rec.insert()
        saved = rec.get()
        return {
            "status": "SUCCESS",
            "desc": "Tarif dibuat",
            "id": str(saved.get("_id", ""))
        }
    # end def

    def delete_tariff(self, tariff_id):
        tariff = self.get_tariff(tariff_id)
        if tariff == None:
            return {"status": "ERROR", "desc": "Tarif tidak ditemukan"}
        # end if
        self.mgdDB.db_tariff.update_one(
            {"_id": ObjectId(tariff["id"])},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Tarif dihapus"}
    # end def
# end class
```

## 3. Blueprint — `slapz102_modules/tariffs/tariffs_blueprint.py`

```python
import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint
from view.tariffs import view_tariffs

# ---------------------------------------------------------------------------
# TARIFFS MODULE — route layer.
#
# /tariffs                    rate card list + create form
# /tariffs/create             form POST
# /tariffs/<id>/delete        soft delete POST
# /api/tariffs                JSON list
# ---------------------------------------------------------------------------

tariffs_blueprint = Blueprint("tariffs_blueprint", __name__)

@tariffs_blueprint.route("/tariffs", methods=["GET"])
def index():
    try:
        return view_tariffs.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@tariffs_blueprint.route("/tariffs/create", methods=["POST"])
def create():
    try:
        return view_tariffs.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@tariffs_blueprint.route("/tariffs/<tariff_id>/delete", methods=["POST"])
def delete(tariff_id):
    try:
        return view_tariffs.html_delete(tariff_id)
    except Exception as e:
        print(traceback.format_exc())
        return "Terjadi kesalahan", 500
    # end try
# end def

@tariffs_blueprint.route("/api/tariffs", methods=["GET"])
def api_list():
    try:
        return view_tariffs.api_list()
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "ERROR", "desc": "Terjadi kesalahan"}, 500
    # end try
# end def
```

## 4. View — `slapz102_modules/view/tariffs/view_tariffs.py`

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for, jsonify
from flask_login import login_required, current_user
from slapz102_core import config
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from tariffs.tariffs_proc import tariffs_proc, SERVICE_TYPES
from shipments.shipments_proc import shipments_proc

# ---------------------------------------------------------------------------
# TARIFFS MODULE — view / render layer.
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/",
        "sidebar_counts": shipments_proc().sidebar_counts()
    }
# end def

@login_required
def html_index():
    data = _base_data()
    data["current_user"] = current_user
    data["form_error"] = (request.args.get("error") or "").strip()
    data["form_success"] = (request.args.get("success") or "").strip()
    data["service_types"] = SERVICE_TYPES
    data["tariffs"] = tariffs_proc().list_tariffs()
    return render_template("tariffs.html", data=data)
# end def

@login_required
def html_create():
    if not csrf.validate():
        return redirect(url_for("tariffs_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = tariffs_proc().create_tariff(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("tariffs_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("tariffs_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def html_delete(tariff_id):
    if not csrf.validate():
        return redirect(url_for("tariffs_blueprint.index", error="Sesi tidak valid, coba lagi"))
    # end if
    result = tariffs_proc().delete_tariff(tariff_id)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("tariffs_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("tariffs_blueprint.index", success=result.get("desc", "")))
# end def

@login_required
def api_list():
    return jsonify({"status": "SUCCESS", "results": tariffs_proc().list_tariffs()})
# end def
```

## 5. Template — `templates/tariffs.html`

```html
{% extends "erp_base.html" %}
{% from "_ui.html" import empty_state %}

{% block title %}Tarif — {{ data.site_name }}{% endblock %}
{% block topbar_title %}Tarif{% endblock %}
{% block erp_content %}
  {% if data.form_error %}<p class="text-danger">{{ data.form_error }}</p>{% endif %}

  <form method="post" action="{{ url_for('tariffs_blueprint.create') }}">
    <input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
    <input name="origin_city" placeholder="Kota asal">
    <input name="destination_city" placeholder="Kota tujuan">
    <select name="service_type">
      {% for s in data.service_types %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
    </select>
    <input name="price_per_kg" type="number" step="0.01">
    <button type="submit">Simpan</button>
  </form>

  {% for t in data.tariffs %}
    <div>
      {{ t.origin_city }} → {{ t.destination_city }} ({{ t.service_type }}): {{ t.price_per_kg }}
      <form method="post" action="{{ url_for('tariffs_blueprint.delete', tariff_id=t.id) }}">
        <input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
        <button type="submit">Hapus</button>
      </form>
    </div>
  {% else %}
    {{ empty_state("Belum ada tarif", "Tambahkan tarif pertama di atas.") }}
  {% endfor %}
{% endblock %}
```

Style with existing component classes from `static/v2/input.css`; add new
ones there and run `npm run build:css` if needed.

## 6. Register — `server.py`

```python
from tariffs.tariffs_blueprint import tariffs_blueprint

app.register_blueprint(tariffs_blueprint, url_prefix="/")
```

## 7. Tests — `tests/test_tariffs.py`

Reuse the scratch-DB `client` and `logged_in` fixture pattern from
`tests/test_logistics.py`:

```python
def test_tariffs_requires_login(client):
    res = client.get("/tariffs")
    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")
# end def

def test_create_tariff(logged_in):
    client = logged_in["client"]
    res = client.post("/tariffs/create", data={
        "csrf_token": logged_in["token"],
        "origin_city": "Medan",
        "destination_city": "Balige",
        "service_type": "LTL",
        "price_per_kg": "4500"
    })
    assert res.status_code == 302
    rec = _db().db_tariff.find_one({"origin_city": "Medan"})
    assert rec != None
    assert rec["is_deleted"] == False
# end def

def test_create_tariff_rejects_missing_csrf(logged_in):
    client = logged_in["client"]
    client.post("/tariffs/create", data={"origin_city": "X", "destination_city": "Y"})
    assert _db().db_tariff.count_documents({}) == 0
# end def
```

Run `python3 -m pytest tests/ -v`; all tests must pass.
