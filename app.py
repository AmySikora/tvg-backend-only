import os
from typing import Tuple
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, instance_relative_config=True)

default_db_path = os.path.join(os.path.dirname(__file__), "ticketveriguard.db")
database_url = os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)


class ClickLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    destination_url = db.Column(db.Text, nullable=False)
    normalized_url = db.Column(db.Text, nullable=True)
    final_url = db.Column(db.Text, nullable=True)
    event_name = db.Column(db.String(255), nullable=True)
    section = db.Column(db.String(100), nullable=True)
    row = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(100), nullable=True)
    referrer = db.Column(db.Text, nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    affiliate_applied = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<ClickLog {self.id} {self.destination_url}>"


def normalize_url(url: str) -> str:
    return str(url or "").strip()


def is_valid_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def maybe_apply_affiliate_link(url: str) -> Tuple[str, bool]:
    return url, False


@app.route("/", methods=["GET"])
def home():
    return "Ticket VeriGuard backend is running.", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/out", methods=["GET"])
def outbound_redirect():
    destination_url = normalize_url(request.args.get("url", ""))
    event_name = normalize_url(request.args.get("event", ""))
    section = normalize_url(request.args.get("section", ""))
    row = normalize_url(request.args.get("row", ""))
    source = normalize_url(request.args.get("source", ""))

    if not destination_url:
        return jsonify({"error": "Missing required query parameter: url"}), 400

    if not is_valid_http_url(destination_url):
        return jsonify({"error": "Invalid destination URL"}), 400

    normalized = normalize_url(destination_url)
    final_url, affiliate_applied = maybe_apply_affiliate_link(normalized)

    referrer = request.referrer
    user_agent = request.headers.get("User-Agent")

    try:
        click = ClickLog(
            destination_url=destination_url,
            normalized_url=normalized,
            final_url=final_url,
            event_name=event_name or None,
            section=section or None,
            row=row or None,
            source=source or None,
            referrer=referrer,
            user_agent=user_agent,
            affiliate_applied=affiliate_applied,
        )
        db.session.add(click)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        app.logger.error("Failed to log outbound click: %s", error)

    return redirect(final_url, code=302)


@app.route("/logs", methods=["GET"])
def logs():
    try:
        rows = ClickLog.query.order_by(ClickLog.timestamp.desc()).limit(25).all()
        return jsonify([
            {
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "destination_url": row.destination_url,
                "normalized_url": row.normalized_url,
                "final_url": row.final_url,
                "source": row.source,
                "referrer": row.referrer,
                "user_agent": row.user_agent,
            }
            for row in rows
        ]), 200
    except Exception as error:
        app.logger.error("Failed to load logs: %s", error)
        return jsonify({"error": "Could not load logs"}), 500


def init_db() -> None:
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
