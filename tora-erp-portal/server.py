import os
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Flask
from flask_login import LoginManager
from slapz102_core import config

app = Flask(__name__)
app.secret_key = config.G_FLASK_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Refuse to serve outside development while the sample secret is unchanged.
# Direct dev runs ("python3 server.py") and FLASK_ENV=development are allowed.
KNOWN_UNSAFE_SECRETS = ["CHANGE-ME-BEFORE-DEPLOY", "dev-only-unsafe-secret"]
if (
    app.secret_key in KNOWN_UNSAFE_SECRETS
    and __name__ != "__main__"
    and os.environ.get("FLASK_ENV") != "development"
    and os.environ.get("FLASK_DEBUG") != "1"
):
    raise RuntimeError(
        "G_FLASK_SECRET is still the sample value. Generate one with: "
        "python3 -c \"import os; print(os.urandom(24).hex())\" "
        "and set it in slapz102_core/config.py"
    )
# end if

# Flask-Login: session auth for the ERP portal. The user loader delegates
# to the auth proc (framework users collection, werkzeug password hashes).
from auth.auth_proc import auth_proc

login_manager = LoginManager()
login_manager.login_view = "auth_blueprint.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return auth_proc().get_login_user(user_id)
# end def

# Import one blueprint per feature module, then register it below.
# Adding a new feature = create slapz102_modules/<feature>/ with
# <feature>_blueprint.py, then add two matching lines here.
# The sample module stays registered under /sample as the reference
# implementation of the framework pattern.
from sample.sample_blueprint import sample_blueprint
from auth.auth_blueprint import auth_blueprint
from contacts.contacts_blueprint import contacts_blueprint
from fleet.fleet_blueprint import fleet_blueprint
from shipments.shipments_blueprint import shipments_blueprint
from manifests.manifests_blueprint import manifests_blueprint
from tracking.tracking_blueprint import tracking_blueprint
from ai.ai_blueprint import ai_blueprint

app.register_blueprint(sample_blueprint, url_prefix="/sample")
app.register_blueprint(auth_blueprint, url_prefix="/")
app.register_blueprint(contacts_blueprint, url_prefix="/")
app.register_blueprint(fleet_blueprint, url_prefix="/")
app.register_blueprint(shipments_blueprint, url_prefix="/")
app.register_blueprint(manifests_blueprint, url_prefix="/")
app.register_blueprint(tracking_blueprint, url_prefix="/")
app.register_blueprint(ai_blueprint, url_prefix="/")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5004")),
        debug=True
    )
# end if
