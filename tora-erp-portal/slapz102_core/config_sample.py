import os

def _load_dotenv():
    # Local secrets live in .env. Existing process env wins.
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env"
    )
    if not os.path.isfile(path):
        return
    # end if
    handle = open(path, "r", encoding="utf-8")
    try:
        for line in handle:
            line = line.strip()
            if line == "" or line.startswith("#") or "=" not in line:
                continue
            # end if
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key != "" and key not in os.environ:
                os.environ[key] = value
            # end if
        # end for
    finally:
        handle.close()
    # end try
# end def

_load_dotenv()

# ---------------------------------------------------------------------------
# Framework configuration — SAMPLE FILE (committed).
#
# Copy it to start a project:
#     cp slapz102_core/config_sample.py slapz102_core/config.py
#
# config.py is gitignored: unique values (secret key, DB name, public URL)
# live only in your local config.py and never reach the repository.
#
# Usage in modules:  from slapz102_core import config  ->  config.mainDB
# ---------------------------------------------------------------------------

# Flask session signing secret — REPLACE with your own unique value:
#     python3 -c "import os; print(os.urandom(24).hex())"
# The server refuses to start outside development mode while this is unchanged.
G_FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY", "CHANGE-ME-BEFORE-DEPLOY")

# Repo root, independent of the folder the server is launched from
G_HOME_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G_STATIC_URL_PATH = "/static"
G_UPLOAD_PATH = G_HOME_PATH + G_STATIC_URL_PATH + "/upload"
G_UPLOAD_URL_PATH = G_STATIC_URL_PATH + "/upload"

# Public URL of the deployed site (no trailing slash). Used to build absolute
# URLs for Open Graph / share previews.
G_PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:5004").strip().rstrip("/")

# Display name used by the sample module's templates
G_SITE_NAME = os.environ.get("SITE_NAME", "Tora Expedition ERP")

# Default social-share / Open Graph image (relative to /static)
G_OG_IMAGE_PATH = G_STATIC_URL_PATH + "/brand/og-default.jpg"

# DATABASE ---------------------------------------------------------------
# MongoDB connection. Override MONGO_URI / MONGO_DB_NAME per environment.
# NOTE: this ERP portal and the landing page (public tracking) must point
# at the SAME database so shipments created here are trackable there.
mainDB = os.environ.get("MONGO_DB_NAME", "tora_logistics")
mainDB_string = os.environ.get(
    "MONGO_URI", "mongodb://127.0.0.1:27017/"
).rstrip("/") + "/" + mainDB

G_DATABASE_CONNECT = [
    {"dbname": mainDB, "dbstring": mainDB_string}
]

# Offset in hours added to UTC when building rec_timestamp fields
JKTA_TZ = int(os.environ.get("TZ_OFFSET_HOURS", "7"))

# AUTH --------------------------------------------------------------------
# Bootstrap superadmin: created automatically the first time the login page
# is rendered while the users collection is still empty. Override both via
# environment variables in production, then change the password.
G_SUPERADMIN_USERNAME = os.environ.get("SUPERADMIN_USERNAME", "superadmin")
G_SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "ToraAdmin#2026")

# AI assistant. Set OPENAI_API_KEY in a gitignored .env file.
G_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
G_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Browser key for the hub place picker. Enable Maps JavaScript API and Places API.
G_GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
