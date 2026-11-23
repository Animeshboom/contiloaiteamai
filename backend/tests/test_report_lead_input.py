"""Team lead additions to the EOD report and the attendance roster."""
from app.services import report_service as rs


def _new_report(client, h):
    r = client.post("/api/v1/reports", headers=h, json={"use_ai": False})
    assert r.status_code == 201, r.text
    return r.json()


def test_lead_can_generate_and_add_notes(client, as_lead):
    rep = _new_report(client, as_lead)
    artist = rep["metrics"]["artists"][0]["name"]
    body = {"lead_input": {
        "blockers": "Render farm down 2 hours.",
        "tomorrow_plan": "Finish SC05 lighting.\nStart SC06 layout.",
        "artist_remarks": {artist: "Great cleanup work.", "Not A Real Person": "ignored", "": "x"},
        "links": [{"label": "Playblasts", "url": "https://drive.google.com/drive/folders/abc"}],
    }}
    r = client.patch(f"/api/v1/reports/{rep['id']}", headers=as_lead, json=body)
    assert r.status_code == 200, r.text
    out = client.get(f"/api/v1/reports/{rep['id']}", headers=as_lead).json()
    li = out["lead_input"]
    assert li["artist_remarks"] == {artist: "Great cleanup work."}  # unknown names dropped
    text = out["body"]
    assert rs.LEAD_START in text and "Render farm down 2 hours." in text and "Start SC06 layout." in text
    assert f"• {artist}: Great cleanup work." in text and "Playblasts: https://drive.google.com/drive/folders/abc" in text
    # The notes sit before the footer, and saving again replaces (not duplicates) the block.
    assert text.index(rs.LEAD_END) < text.rindex("\n—\n")
    client.patch(f"/api/v1/reports/{rep['id']}", headers=as_lead, json={"lead_input": {"blockers": "None today."}})
    text = client.get(f"/api/v1/reports/{rep['id']}", headers=as_lead).json()["body"]
    assert text.count(rs.LEAD_START) == 1 and "None today." in text and "Render farm" not in text

    # Clearing everything removes the block.
    client.patch(f"/api/v1/reports/{rep['id']}", headers=as_lead, json={"lead_input": {}})
    assert rs.LEAD_START not in client.get(f"/api/v1/reports/{rep['id']}", headers=as_lead).json()["body"]


def test_bad_link_rejected_and_notes_locked_after_submit(client, as_lead):
    rep = _new_report(client, as_lead)
    r = client.patch(f"/api/v1/reports/{rep['id']}", headers=as_lead,
                     json={"lead_input": {"links": [{"url": "javascript:alert(1)"}]}})
    assert r.status_code == 422
    assert client.post(f"/api/v1/reports/{rep['id']}/submit", headers=as_lead, json={}).status_code == 200
    r = client.patch(f"/api/v1/reports/{rep['id']}", headers=as_lead, json={"lead_input": {"blockers": "late"}})
    assert r.status_code == 409


def test_attendance_roster_lists_absent_first():
    m = {"totals": {"present": 1, "team_members": 3, "half_day": 0, "on_leave": 1, "absent": 1, "not_checked_in": 0},
         "artists": [{"name": "Asha", "attendance": "present", "check_in": "09:58"},
                     {"name": "Zoya", "attendance": "absent", "check_in": None},
                     {"name": "Ravi", "attendance": "leave", "check_in": None}]}
    lines = rs.render_attendance(m)
    assert lines[2] == "  Present 1 of 3 · On leave 1 · Absent 1"
    assert lines[3] == "  ⚠ NOT PRESENT:" and lines[4] == "    ✗ Zoya — absent"
    assert lines.index("    · Ravi — on leave") < lines.index("    ✓ Asha — present")
