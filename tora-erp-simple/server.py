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

from auth.auth_proc import auth_proc

login_manager = LoginManager()
login_manager.login_view = "auth_blueprint.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return auth_proc().get_login_user(user_id)
# end def

from sample.sample_blueprint import sample_blueprint
from auth.auth_blueprint import auth_blueprint
from routes.routes_blueprint import routes_blueprint
from orders.orders_blueprint import orders_blueprint

app.register_blueprint(sample_blueprint, url_prefix="/sample")
app.register_blueprint(auth_blueprint, url_prefix="/")
app.register_blueprint(routes_blueprint, url_prefix="/")
app.register_blueprint(orders_blueprint, url_prefix="/")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5005")),
        debug=True
    )
# end if
