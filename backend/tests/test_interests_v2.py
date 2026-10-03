"""Version-gated interests and feed filters (eng review OV3).

    1.12 (no X-Chintan-Client) ─ legacy categories, legacy save merged losslessly
    1.13 (X-Chintan-Client: 1.13) ─ v2 categories + States, v2 save derives legacy
    /articles ─ v2 clients filter category_v2 / subcategory_v2 / state
"""

import os

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "t")
os.environ.setdefault("JWT_SECRET", "t")
server = pytest.importorskip("server")


class Req:
    def __init__(self, version=None):
        self.headers = {"X-Chintan-Client": version} if version else {}
        self.cookies = {}


@pytest.fixture
async def db(monkeypatch):
    d = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", d)
    await d.users.insert_one({"user_id": "u1", "email": "a@b.c", "interests": ["Cricket"],
                              "interests_v2": ["Cricket", "Hockey", "Maharashtra"]})
    return d


@pytest.mark.parametrize("raw,ok", [(None, False), ("", False), ("1.12", False), ("1.13", True),
                                    ("1.14.2", True), ("2.0", True), ("banana", False)])
def test_version_gate(raw, ok):
    assert server._is_v2_client(Req(raw)) is ok


async def test_categories_by_client(db):
    legacy = await server.get_interest_categories(Req())
    assert legacy is server.INTEREST_CATEGORIES and "Health" not in legacy
    v2 = await server.get_interest_categories(Req("1.13"))
    assert "Health" in v2 and "Maharashtra" in v2["States"] and "Hockey" in v2["Sports"]


async def test_112_save_keeps_v2_only_picks(db):
    user = await db.users.find_one({"user_id": "u1"})
    out = await server.update_interests(server.InterestsUpdate(interests=["Cricket", "Olympics", "Football"]),
                                        Req(), user)
    assert out["interests"] == ["Cricket", "Olympics", "Football"]
    assert out["interests_v2"] == ["Cricket", "Hockey", "Maharashtra", "Football"]


async def test_113_save_derives_legacy(db):
    user = await db.users.find_one({"user_id": "u1"})
    out = await server.update_interests(server.InterestsUpdate(interests=["Health", "Chess", "Kerala", "Cricket"]),
                                        Req("1.13"), user)
    assert out["interests_v2"] == ["Health", "Chess", "Kerala", "Cricket"]
    assert out["interests"] == ["Science", "Cricket"]


async def test_feed_filters_by_client(db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.articles.insert_many([
        {"article_id": "h", "title": "Dengue", "category": "Science", "category_v2": "Health",
         "published_at": now, "rank_at": now, "state": "Kerala"},
        {"article_id": "s", "title": "ISRO", "category": "Science", "category_v2": "Science",
         "published_at": now, "rank_at": now},
    ])
    legacy = await server.get_articles(category="Science", request=Req())
    assert {a["article_id"] for a in legacy} == {"h", "s"}
    v2 = await server.get_articles(category="Health", request=Req("1.13"))
    assert [a["article_id"] for a in v2] == ["h"]
    by_state = await server.get_articles(state="Kerala", request=Req("1.13"))
    assert [a["article_id"] for a in by_state] == ["h"]
    ignored = await server.get_articles(state="Kerala", request=Req())   # 1.12 never sends it; ignore if it did
    assert {a["article_id"] for a in ignored} == {"h", "s"}


async def test_any_state_filter(db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.articles.insert_many([
        {"article_id": "k", "title": "Kochi", "category": "Politics", "published_at": now, "rank_at": now, "state": "Kerala"},
        {"article_id": "n", "title": "National", "category": "Politics", "published_at": now, "rank_at": now, "state": None},
    ])
    got = await server.get_articles(state="*", request=Req("1.13"))
    assert [a["article_id"] for a in got] == ["k"]
