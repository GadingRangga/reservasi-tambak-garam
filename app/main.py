import io
import os
import uuid
from datetime import date, timedelta

import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from app.models import Reservation, SiteSetting, db


def get_settings() -> SiteSetting:
    setting = db.session.get(SiteSetting, 1)
    if setting is None:
        setting = SiteSetting(
            id=1, max_daily_capacity=50, ticket_price=25000, visit_duration_hours=2
        )
        db.session.add(setting)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            setting = db.session.get(SiteSetting, 1)
    return setting


def get_used_quota(target_date: date) -> int:
    total = (
        db.session.query(func.coalesce(func.sum(Reservation.participants), 0))
        .filter(
            Reservation.visit_date == target_date,
            Reservation.status != "cancelled",
        )
        .scalar()
    )
    return int(total or 0)


def generate_booking_code() -> str:
    return f"TG-{uuid.uuid4().hex[:6].upper()}"


def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-tambak-garam-2026"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///reservasi_tambak.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        get_settings()

    @app.route("/", methods=["GET"])
    def index():
        settings = get_settings()
        tomorrow = date.today() + timedelta(days=1)
        code = request.args.get("code", "").strip().upper()
        found_reservation = None
        lookup_error = None

        if code:
            found_reservation = Reservation.query.filter_by(booking_code=code).first()
            if found_reservation is None:
                lookup_error = f"Kode reservasi '{code}' tidak ditemukan."

        return render_template(
            "index.html",
            settings=settings,
            min_date=tomorrow.isoformat(),
            found_reservation=found_reservation,
            lookup_error=lookup_error,
        )

    @app.route("/api/quota", methods=["GET"])
    def api_quota():
        date_str = request.args.get("date", "")
        settings = get_settings()
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify({"error": "Format tanggal tidak valid (YYYY-MM-DD)."}), 400

        used = get_used_quota(target_date)
        remaining = max(settings.max_daily_capacity - used, 0)
        return jsonify(
            {
                "date": target_date.isoformat(),
                "max_capacity": settings.max_daily_capacity,
                "used_quota": used,
                "remaining_quota": remaining,
                "ticket_price": settings.ticket_price,
            }
        )

    @app.route("/reserve", methods=["POST"])
    def reserve():
        settings = get_settings()
        visitor_name = request.form.get("visitor_name", "").strip()
        visitor_email = request.form.get("visitor_email", "").strip()
        visit_date_str = request.form.get("visit_date", "").strip()
        participants_raw = request.form.get("participants", "").strip()

        def fail(message: str):
            flash(message, "error")
            tomorrow = date.today() + timedelta(days=1)
            return (
                render_template(
                    "index.html",
                    settings=settings,
                    min_date=tomorrow.isoformat(),
                    found_reservation=None,
                    lookup_error=None,
                ),
                400,
            )

        if not visitor_name or not visitor_email:
            return fail("Nama dan email pengunjung wajib diisi.")

        try:
            visit_date = date.fromisoformat(visit_date_str)
        except ValueError:
            return fail("Tanggal kunjungan tidak valid.")

        if visit_date <= date.today():
            return fail("Tanggal kunjungan harus untuk tanggal mendatang (minimal besok).")

        try:
            participants = int(participants_raw)
        except ValueError:
            return fail("Jumlah peserta harus berupa angka bulat.")

        if participants < 1:
            return fail("Jumlah peserta tidak boleh kurang dari 1 orang.")

        used_quota = get_used_quota(visit_date)
        remaining_quota = settings.max_daily_capacity - used_quota
        if participants > remaining_quota:
            return fail(
                f"Kuota harian tidak mencukupi. Sisa kuota pada {visit_date.isoformat()} hanya {max(remaining_quota, 0)} orang."
            )

        total_price = participants * settings.ticket_price
        booking_code = generate_booking_code()

        new_res = Reservation(
            booking_code=booking_code,
            visitor_name=visitor_name,
            visitor_email=visitor_email,
            visit_date=visit_date,
            participants=participants,
            total_price=total_price,
            status="pending",
        )
        db.session.add(new_res)
        db.session.commit()

        flash(f"Reservasi berhasil dibuat dengan kode {booking_code}.", "success")
        return redirect(url_for("index", code=booking_code))

    @app.route("/cancel/<booking_code>", methods=["POST"])
    def cancel_reservation(booking_code: str):
        reservation = Reservation.query.filter_by(
            booking_code=booking_code.strip().upper()
        ).first()
        if reservation is None:
            flash("Reservasi tidak ditemukan.", "error")
            return redirect(url_for("index")), 404

        if reservation.status == "cancelled":
            flash("Reservasi tersebut sudah dibatalkan sebelumnya.", "info")
        else:
            reservation.status = "cancelled"
            db.session.commit()
            flash(
                f"Reservasi {reservation.booking_code} berhasil dibatalkan dan kuota telah dikembalikan.",
                "success",
            )
        return redirect(url_for("index", code=reservation.booking_code))

    @app.route("/admin", methods=["GET"])
    def admin():
        settings = get_settings()
        filter_date_str = request.args.get("date", "").strip()
        query = Reservation.query

        selected_date = None
        if filter_date_str:
            try:
                selected_date = date.fromisoformat(filter_date_str)
                query = query.filter(Reservation.visit_date == selected_date)
            except ValueError:
                flash("Format filter tanggal tidak valid.", "error")

        reservations = query.order_by(
            Reservation.visit_date.asc(), Reservation.created_at.desc()
        ).all()

        active_participants = sum(
            r.participants for r in reservations if r.status != "cancelled"
        )

        return render_template(
            "admin.html",
            settings=settings,
            reservations=reservations,
            filter_date=filter_date_str,
            active_participants=active_participants,
        )

    @app.route("/admin/reservations/<int:res_id>/status", methods=["POST"])
    def admin_update_status(res_id: int):
        reservation = db.session.get(Reservation, res_id)
        if reservation is None:
            flash("Data reservasi tidak ditemukan.", "error")
            return redirect(url_for("admin")), 404

        if reservation.status == "cancelled":
            flash("Reservasi yang sudah dibatalkan tidak dapat diubah statusnya.", "error")
            return redirect(url_for("admin")), 400

        new_status = request.form.get("status", "").strip().lower()
        if new_status not in {"approved", "cancelled"}:
            flash("Status tidak valid.", "error")
            return redirect(url_for("admin")), 400

        reservation.status = new_status
        db.session.commit()
        flash(
            f"Status reservasi {reservation.booking_code} diubah menjadi {new_status}.",
            "success",
        )
        return redirect(url_for("admin"))

    @app.route("/admin/settings", methods=["POST"])
    def admin_update_settings():
        settings = get_settings()
        try:
            new_capacity = int(request.form.get("max_daily_capacity", ""))
        except ValueError:
            flash("Kapasitas harian harus berupa angka.", "error")
            return redirect(url_for("admin")), 400

        if new_capacity < 1:
            flash("Kapasitas harian minimal 1 orang.", "error")
            return redirect(url_for("admin")), 400

        settings.max_daily_capacity = new_capacity
        db.session.commit()
        flash(
            f"Kapasitas maksimum harian diperbarui menjadi {new_capacity} orang.",
            "success",
        )
        return redirect(url_for("admin"))

    @app.route("/admin/export", methods=["GET"])
    def admin_export():
        reservations = Reservation.query.order_by(Reservation.visit_date.asc()).all()
        rows = [
            {
                "Kode Booking": r.booking_code,
                "Nama Pengunjung": r.visitor_name,
                "Email": r.visitor_email,
                "Tanggal Kunjungan": r.visit_date.isoformat(),
                "Jumlah Peserta": r.participants,
                "Total Biaya (Rp)": r.total_price,
                "Status": r.status,
            }
            for r in reservations
        ]
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Reservasi")
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="rekap-reservasi-tambak-garam.xlsx",
        )

    @app.route("/health", methods=["GET"])
    def health():
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "service": "reservasi-tambak-garam"}), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)