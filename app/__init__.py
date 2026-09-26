# -*- coding: utf-8 -*-
import os
from flask import Flask

db_dir = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "cobros.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "cobros-local"

    from .models import db
    db.init_app(app)

    os.makedirs(app.instance_path, exist_ok=True)

    def money(value):
        try:
            n = float(value or 0)
        except (TypeError, ValueError):
            return str(value or "")
        return "$ " + f"{n:,.0f}".replace(",", ".")

    app.add_template_filter(money, "money")

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        from .migraciones import ejecutar as migrar
        migrar(db)

        from .asesorias_seed import seed_asesorias
        seed_asesorias()

    from .respaldos import respaldo_arranque
    respaldo_arranque(app)

    return app
