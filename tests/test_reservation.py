from datetime import date, timedelta

import pytest

from app.main import create_app
from app.models import Reservation, db


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
        }
    )
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def future_date_str(days_ahead: int = 2) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def past_date_str(days_ago: int = 1) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_home_endpoint_accessible(client):
    """Endpoint utama (/) dapat diakses dengan status 200."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Wisata Edukasi Tambak Garam" in response.data


def test_health_check_endpoint(client):
    """Endpoint /health mengembalikan status HTTP 200 dan JSON ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "reservasi-tambak-garam"


def test_valid_reservation_and_total_price(client, app):
    """Reservasi valid berhasil dibuat dan total biaya dihitung dengan benar (peserta x Rp25.000)."""
    target_date = future_date_str(3)
    response = client.post(
        "/reserve",
        data={
            "visitor_name": "Budi Santoso",
            "visitor_email": "budi@example.com",
            "visit_date": target_date,
            "participants": "4",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        res = Reservation.query.filter_by(visitor_name="Budi Santoso").first()
        assert res is not None
        assert res.participants == 4
        assert res.total_price == 100000
        assert res.status == "pending"


@pytest.mark.parametrize("invalid_participants", ["0", "-3"])
def test_reject_zero_or_negative_participants(client, app, invalid_participants):
    """Reservasi ditolak jika jumlah peserta sama dengan nol atau negatif."""
    response = client.post(
        "/reserve",
        data={
            "visitor_name": "Siti Aminah",
            "visitor_email": "siti@example.com",
            "visit_date": future_date_str(2),
            "participants": invalid_participants,
        },
    )
    assert response.status_code == 400

    with app.app_context():
        assert Reservation.query.count() == 0


def test_reject_past_or_today_date(client, app):
    """Tanggal reservasi di masa lalu atau hari ini ditolak."""
    for invalid_date in [past_date_str(1), date.today().isoformat()]:
        response = client.post(
            "/reserve",
            data={
                "visitor_name": "Andi Wijaya",
                "visitor_email": "andi@example.com",
                "visit_date": invalid_date,
                "participants": "2",
            },
        )
        assert response.status_code == 400

    with app.app_context():
        assert Reservation.query.count() == 0


def test_reject_when_daily_quota_exceeded(client, app):
    """Reservasi ditolak jika jumlah peserta melebihi sisa kuota harian (default 50)."""
    target_date = future_date_str(5)

    # Reservasi pertama 40 orang (berhasil)
    first = client.post(
        "/reserve",
        data={
            "visitor_name": "Rombongan A",
            "visitor_email": "a@example.com",
            "visit_date": target_date,
            "participants": "40",
        },
    )
    assert first.status_code == 302

    # Reservasi kedua 15 orang pada tanggal sama (total 55 > 50, harus ditolak)
    second = client.post(
        "/reserve",
        data={
            "visitor_name": "Rombongan B",
            "visitor_email": "b@example.com",
            "visit_date": target_date,
            "participants": "15",
        },
    )
    assert second.status_code == 400

    with app.app_context():
        assert Reservation.query.count() == 1


def test_cancel_reservation_restores_quota(client, app):
    """Reservasi dapat dibatalkan dan kuota yang dibatalkan kembali tersedia."""
    target_date = future_date_str(4)
    client.post(
        "/reserve",
        data={
            "visitor_name": "Dewi Lestari",
            "visitor_email": "dewi@example.com",
            "visit_date": target_date,
            "participants": "10",
        },
    )

    with app.app_context():
        res = Reservation.query.filter_by(visitor_name="Dewi Lestari").first()
        booking_code = res.booking_code

    # Cek kuota terpakai sebelum batal
    quota_before = client.get(f"/api/quota?date={target_date}").get_json()
    assert quota_before["used_quota"] == 10
    assert quota_before["remaining_quota"] == 40

    # Batalkan reservasi
    cancel_resp = client.post(f"/cancel/{booking_code}")
    assert cancel_resp.status_code == 302

    # Cek kuota setelah batal
    quota_after = client.get(f"/api/quota?date={target_date}").get_json()
    assert quota_after["used_quota"] == 0
    assert quota_after["remaining_quota"] == 50


def test_admin_can_view_and_approve_reservation(client, app):
    """Daftar reservasi berhasil dilihat dan disetujui oleh admin."""
    target_date = future_date_str(6)
    client.post(
        "/reserve",
        data={
            "visitor_name": "Raka Pratama",
            "visitor_email": "raka@example.com",
            "visit_date": target_date,
            "participants": "3",
        },
    )

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    assert b"Raka Pratama" in admin_page.data

    with app.app_context():
        res = Reservation.query.filter_by(visitor_name="Raka Pratama").first()
        res_id = res.id

    approve_resp = client.post(
        f"/admin/reservations/{res_id}/status", data={"status": "approved"}
    )
    assert approve_resp.status_code == 302

    with app.app_context():
        updated = db.session.get(Reservation, res_id)
        assert updated.status == "approved"


def test_admin_cannot_approve_cancelled_reservation(client, app):
    """Reservasi yang sudah dibatalkan tidak bisa disetujui kembali oleh admin."""
    target_date = future_date_str(7)
    client.post(
        "/reserve",
        data={
            "visitor_name": "Nadia Putri",
            "visitor_email": "nadia@example.com",
            "visit_date": target_date,
            "participants": "5",
        },
    )

    with app.app_context():
        res = Reservation.query.filter_by(visitor_name="Nadia Putri").first()
        res_id = res.id
        booking_code = res.booking_code

    client.post(f"/cancel/{booking_code}")

    attempt = client.post(
        f"/admin/reservations/{res_id}/status", data={"status": "approved"}
    )
    assert attempt.status_code == 400

    with app.app_context():
        still_cancelled = db.session.get(Reservation, res_id)
        assert still_cancelled.status == "cancelled"


def test_admin_export_excel(client):
    """Endpoint ekspor rekap admin menghasilkan berkas Excel (.xlsx)."""
    response = client.get("/admin/export")
    assert response.status_code == 200
    assert (
        response.mimetype
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )