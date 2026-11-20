"""Studio chat: automatic channels, who can post, edit/delete rules, unread counts, retention, live hub."""
import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.models import ChatMessage, User
from app.services import chat_service
from tests.conftest import ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD, LEAD_OTHER, login

API = "/api/v1"


def _team_key(db, email):
    return f"team:{db.scalar(select(User.team_id).where(User.email == email))}"


def _keys(client, h):
    return [c["key"] for c in client.get(f"{API}/chat/channels", headers=h).json()]


def test_channels_follow_roles_and_teams(client, as_admin, db):
    artist, lead = login(client, ARTIST), login(client, LEAD)
    assert _keys(client, artist) == ["everyone", _team_key(db, ARTIST)]
    assert set(_keys(client, lead)) >= {"everyone", "leads", _team_key(db, ARTIST)}
    admin_keys = _keys(client, as_admin)
    assert {"everyone", "leads", _team_key(db, ARTIST), _team_key(db, ARTIST_OTHER_TEAM)} <= set(admin_keys)
    # artists can't open other teams' chats or the leads chat
    assert client.get(f"{API}/chat/channels/{_team_key(db, ARTIST_OTHER_TEAM)}/messages", headers=artist).status_code == 404
    assert client.get(f"{API}/chat/channels/leads/messages", headers=artist).status_code == 404


def test_posting_rules_links_and_unread(client, as_admin, db):
    artist, artist2, lead = login(client, ARTIST), login(client, ARTIST2), login(client, LEAD)
    team = _team_key(db, ARTIST)
    r = client.post(f"{API}/chat/channels/{team}/messages", headers=artist,
                    json={"body": "Review call: https://meet.google.com/abc-defg-hij"})
    assert r.status_code == 201 and "meet.google.com" in r.json()["body"]
    assert client.post(f"{API}/chat/channels/everyone/messages", headers=artist, json={"body": "hi"}).status_code == 403
    assert client.post(f"{API}/chat/channels/everyone/messages", headers=lead, json={"body": "Studio closes at 6"}).status_code == 201

    ch = {c["key"]: c for c in client.get(f"{API}/chat/channels", headers=artist2).json()}
    assert ch[team]["unread"] == 1 and ch["everyone"]["unread"] == 1
    assert client.get(f"{API}/chat/unread", headers=artist2).json() == {"unread": 2}
    msgs = client.get(f"{API}/chat/channels/{team}/messages", headers=artist2).json()
    client.post(f"{API}/chat/channels/{team}/read", headers=artist2, json={"last_id": msgs[-1]["id"]})
    assert client.get(f"{API}/chat/unread", headers=artist2).json() == {"unread": 1}
    # your own messages never count as unread
    assert {c["key"]: c["unread"] for c in client.get(f"{API}/chat/channels", headers=artist).json()}[team] == 0
    other_lead = login(client, LEAD_OTHER)
    assert client.post(f"{API}/chat/channels/{team}/messages", headers=other_lead, json={"body": "x"}).status_code == 404


def test_edit_and_delete_rules(client, as_admin, db):
    artist, artist2 = login(client, ARTIST), login(client, ARTIST2)
    team = _team_key(db, ARTIST)
    m = client.post(f"{API}/chat/channels/{team}/messages", headers=artist, json={"body": "typo hre"}).json()
    r = client.patch(f"{API}/chat/messages/{m['id']}", headers=artist, json={"body": "typo here"})
    assert r.status_code == 200 and r.json()["edited_at"]
    assert client.patch(f"{API}/chat/messages/{m['id']}", headers=artist2, json={"body": "nope"}).status_code == 403
    assert client.delete(f"{API}/chat/messages/{m['id']}", headers=artist2).status_code == 403

    old = db.get(ChatMessage, m["id"])
    old.created_at = utcnow() - timedelta(minutes=20)
    db.commit()
    assert client.patch(f"{API}/chat/messages/{m['id']}", headers=artist, json={"body": "late"}).status_code == 403
    assert client.delete(f"{API}/chat/messages/{m['id']}", headers=artist).status_code == 403
    assert client.delete(f"{API}/chat/messages/{m['id']}", headers=as_admin).status_code == 204  # admins: any time
    shown = client.get(f"{API}/chat/channels/{team}/messages", headers=artist).json()[-1]
    assert shown["deleted"] and shown["body"] is None


def test_retention_and_paging(client, db):
    lead = login(client, LEAD)
    for i in range(3):
        client.post(f"{API}/chat/channels/everyone/messages", headers=lead, json={"body": f"m{i}"})
    first = db.scalar(select(ChatMessage).order_by(ChatMessage.id))
    first.created_at = utcnow() - timedelta(days=91)
    db.commit()
    assert chat_service.purge_old(db) == 1
    page = client.get(f"{API}/chat/channels/everyone/messages?limit=1", headers=lead).json()
    assert [m["body"] for m in page] == ["m2"]
    older = client.get(f"{API}/chat/channels/everyone/messages?before_id={page[0]['id']}", headers=lead).json()
    assert [m["body"] for m in older] == ["m1"]


def test_live_hub_delivers_only_to_members():
    async def scenario():
        hub = chat_service.Hub()
        hub.attach(asyncio.get_running_loop())
        team_a, everyone_only = hub.subscribe({"everyone", "team:1"}), hub.subscribe({"everyone"})
        hub.publish("team:1", "message", {"id": 1})
        await asyncio.sleep(0)
        assert team_a.get_nowait() == ("message", {"id": 1})
        assert everyone_only.empty()
    asyncio.run(scenario())


def test_stream_ticket(client):
    artist = login(client, ARTIST)
    t = client.post(f"{API}/chat/stream-ticket", headers=artist).json()["ticket"]
    assert t and client.get(f"{API}/chat/stream?ticket=bogus").status_code == 401
