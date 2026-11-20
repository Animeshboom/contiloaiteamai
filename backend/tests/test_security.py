"""Security: lockout, admin two-step login, admin alerts, contact-info privacy, backups."""
import io
import json
import zipfile

from sqlalchemy import select

from app.core.config import get_settings
from app.models import Notification
from app.services import security_service
from tests.conftest import ADMIN, ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD, login, password_for, uid

API = "/api/v1"


def _alerts(db, title_part=""):
    db.expire_all()
    return [n for n in db.scalars(select(Notification).where(Notification.event_type == "security_alert"))
            if title_part in n.title]


def test_lockout_after_five_wrong_passwords(client, as_admin, db):
    for _ in range(4):
        r = client.post(f"{API}/auth/login", json={"email": ARTIST2, "password": "wrong-password"})
        assert r.status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": ARTIST2, "password": "wrong-password"})
    assert r.status_code == 429 and "Too many wrong passwords" in r.json()["detail"]
    # even the right password is refused while locked
    assert client.post(f"{API}/auth/login", json={"email": ARTIST2, "password": password_for(ARTIST2)}).status_code == 429
    assert _alerts(db, "Account locked")
    assert client.get(f"{API}/users/{uid(db, ARTIST2)}", headers=as_admin).json()["locked_until"]
    assert client.post(f"{API}/users/{uid(db, ARTIST2)}/unlock", headers=as_admin).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": ARTIST2, "password": password_for(ARTIST2)}).status_code == 200


def test_admin_two_step_login(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_mfa_required", True)
    h = login(client, ADMIN)  # password only (aal1)
    assert client.get(f"{API}/users", headers=h).status_code == 403  # admin pages need two-step
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200
    lead = login(client, LEAD)
    assert client.get(f"{API}/users", headers=lead).status_code == 200  # leads are not affected

    setup = client.post(f"{API}/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert client.post(f"{API}/auth/mfa/enable", headers=h, json={"code": "000000"}).status_code == 422
    r = client.post(f"{API}/auth/mfa/enable", headers=h, json={"code": security_service.totp_code(setup["secret"])})
    assert r.status_code == 200 and r.json()["user"]["mfa_enabled"]
    assert client.get(f"{API}/users", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401  # the older password-only session ended

    # next sign-in: password, then code
    r = client.post(f"{API}/auth/login", json={"email": ADMIN, "password": password_for(ADMIN)})
    assert r.status_code == 200 and r.json()["mfa_required"] and r.json()["access_token"] is None
    bad = client.post(f"{API}/auth/login/mfa", json={"mfa_token": r.json()["mfa_token"], "code": "123456"})
    assert bad.status_code == 401
    ok = client.post(f"{API}/auth/login/mfa", json={"mfa_token": r.json()["mfa_token"],
                                                    "code": security_service.totp_code(setup["secret"])})
    assert ok.status_code == 200
    admin_h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get(f"{API}/users", headers=admin_h).status_code == 200
    # a two-step ticket is not an access token
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['mfa_token']}"}).status_code == 401


def test_new_admin_device_alert(client, db):
    def sign_in(agent):
        client.post(f"{API}/auth/login", json={"email": ADMIN, "password": password_for(ADMIN)},
                    headers={"User-Agent": agent})
    sign_in("Laptop Chrome")
    assert not _alerts(db, "New sign-in")  # the first device is just remembered
    sign_in("Laptop Chrome")
    assert not _alerts(db, "New sign-in")
    sign_in("Unknown Phone")
    assert _alerts(db, "New sign-in")


def test_bulk_import_alert(client, as_admin, db):
    content = "name\n" + "\n".join(f"Person {i}" for i in range(6)) + "\n"
    r = client.post(f"{API}/artists/import", headers=as_admin, files={"file": ("a.csv", content, "text/csv")})
    assert len(r.json()["created"]) == 6
    assert _alerts(db, "Bulk change")


def test_artists_never_see_other_peoples_contact_details(client, db):
    artist = login(client, ARTIST)
    assert client.get(f"{API}/users", headers=artist).status_code == 403
    assert client.get(f"{API}/users/{uid(db, ARTIST2)}", headers=artist).status_code == 403
    assert client.get(f"{API}/teams", headers=artist).status_code == 403
    lead = login(client, LEAD)  # leads: own team only
    assert client.get(f"{API}/users/{uid(db, ARTIST_OTHER_TEAM)}", headers=lead).status_code == 404


def test_backup_download(client, as_admin, db):
    lead = login(client, LEAD)
    r = client.get(f"{API}/backup", headers=lead)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"people.json", "attendance.json", "assignments.json", "README.txt"} <= set(z.namelist())
    assert "activity_log.json" not in z.namelist()  # admin only
    people = json.loads(z.read("people.json"))
    emails = {p["email"] for p in people}
    assert ARTIST in emails and ARTIST_OTHER_TEAM not in emails  # their team only
    assert not any("password" in k or "totp" in k for p in people for k in p)

    full = zipfile.ZipFile(io.BytesIO(client.get(f"{API}/backup", headers=as_admin).content))
    assert {"activity_log.json", "teams.json", "projects.json"} <= set(full.namelist())
    assert ARTIST_OTHER_TEAM in {p["email"] for p in json.loads(full.read("people.json"))}
    assert client.get(f"{API}/backup", headers=login(client, ARTIST)).status_code == 403
