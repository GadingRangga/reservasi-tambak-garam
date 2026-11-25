from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class SiteSetting(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    max_daily_capacity = db.Column(db.Integer, nullable=False, default=50)
    ticket_price = db.Column(db.Integer, nullable=False, default=25000)
    visit_duration_hours = db.Column(db.Integer, nullable=False, default=2)


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    booking_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    visitor_name = db.Column(db.String(100), nullable=False)
    visitor_email = db.Column(db.String(120), nullable=False)
    visit_date = db.Column(db.Date, nullable=False, index=True)
    participants = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )