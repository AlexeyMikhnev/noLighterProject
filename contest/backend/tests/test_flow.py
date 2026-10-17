from datetime import datetime, timedelta, timezone

import pytest

NICKS = ["alice", "bob", "carol", "dave", "erin"]
SCALES = ["impression", "theme", "style", "light", "dark", "adventure"]


def rating(v: int) -> dict:
    return {k: v for k in SCALES}


def start_contest(client, admin, **kw):
    r = client.post("/api/admin/contest", json={"theme": "Огонь", **kw}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def advance(client, admin, expected: str):
    r = client.post("/api/admin/contest/advance", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["phase"] == expected


def submit(client, user, title):
    r = client.put("/api/stories/me", json={"title": title, "body": f"Текст рассказа {title}"}, headers=user)
    assert r.status_code == 200, r.text


@pytest.fixture()
def voting(client, admin, make_user):
    """Конкурс в фазе оценивания: 5 участников, у каждого рассказ «Story <nick>»."""
    users = {n: make_user(n) for n in NICKS}
    start_contest(client, admin)
    advance(client, admin, "submission")
    for n, u in users.items():
        submit(client, u, f"Story {n}")
    advance(client, admin, "voting")
    return users


def number_of(client, user, title) -> int:
    items = client.get("/api/voting/stories", headers=user).json()["stories"]
    return next(i["anon_number"] for i in items if i["title"] == title)


# ---------- инвайты ----------


def test_invite_is_single_use(client, admin):
    token = client.post("/api/admin/invites", json={"count": 1}, headers=admin).json()[0]["token"]
    assert client.get(f"/api/auth/invite/{token}").json() == {"valid": True}
    body = {"invite_token": token, "email": "a@example.com", "nickname": "aa", "password": "password123"}
    assert client.post("/api/auth/register", json=body).status_code == 200
    assert client.get(f"/api/auth/invite/{token}").json() == {"valid": False}
    body["email"], body["nickname"] = "b@example.com", "bb"
    assert client.post("/api/auth/register", json=body).status_code == 400


def test_register_requires_valid_invite(client):
    body = {
        "invite_token": "00000000-0000-0000-0000-000000000000",
        "email": "a@example.com",
        "nickname": "aa",
        "password": "password123",
    }
    assert client.post("/api/auth/register", json=body).status_code == 400


def test_only_organizer_can_use_admin(client, make_user):
    user = make_user("alice")
    assert client.post("/api/admin/invites", json={"count": 1}, headers=user).status_code == 403
    assert client.get("/api/admin/stats").status_code == 401


# ---------- фазы ----------


def test_draft_hides_theme_from_participants(client, admin, make_user):
    user = make_user("alice")
    start_contest(client, admin)
    assert client.get("/api/contest/current", headers=user).json()["theme"] is None
    assert client.get("/api/contest/current", headers=admin).json()["theme"] == "Огонь"
    # в черновике сдавать работы нельзя
    r = client.put("/api/stories/me", json={"title": "x", "body": "y"}, headers=user)
    assert r.status_code == 403
    advance(client, admin, "submission")
    assert client.get("/api/contest/current", headers=user).json()["theme"] == "Огонь"


def test_submission_is_editable_then_frozen(client, admin, make_user):
    user = make_user("alice")
    start_contest(client, admin)
    advance(client, admin, "submission")
    submit(client, user, "v1")
    client.put("/api/stories/me", json={"title": "v2", "body": "новый текст"}, headers=user)
    assert client.get("/api/stories/me", headers=user).json()["title"] == "v2"
    advance(client, admin, "voting")
    r = client.put("/api/stories/me", json={"title": "v3", "body": "поздно"}, headers=user)
    assert r.status_code == 403
    assert client.delete("/api/stories/me", headers=user).status_code == 403


def test_voting_not_available_during_submission(client, admin, make_user):
    user = make_user("alice")
    start_contest(client, admin)
    advance(client, admin, "submission")
    submit(client, user, "mine")
    assert client.get("/api/voting/stories", headers=user).status_code == 403


def test_results_closed_before_final(client, voting, admin):
    user = voting["alice"]
    assert client.get("/api/results", headers=user).status_code == 403
    assert client.get("/api/results/stories/1", headers=user).status_code == 403


def test_cannot_go_past_results(client, voting, admin):
    advance(client, admin, "results")
    assert client.post("/api/admin/contest/advance", headers=admin).status_code == 409


def test_deadline_auto_advances_phase(client, admin, make_user):
    user = make_user("alice")
    soon = datetime.now(timezone.utc) + timedelta(seconds=1)
    start_contest(
        client,
        admin,
        submission_ends_at=soon.isoformat(),
        voting_ends_at=(soon + timedelta(days=1)).isoformat(),
    )
    advance(client, admin, "submission")
    submit(client, user, "mine")
    import time

    time.sleep(1.5)
    assert client.get("/api/contest/current", headers=user).json()["phase"] == "voting"


def test_deadlines_must_be_in_future(client, admin):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = client.post("/api/admin/contest", json={"theme": "x", "submission_ends_at": past}, headers=admin)
    assert r.status_code == 422


# ---------- анонимность ----------


def test_voting_payloads_never_contain_author(client, voting):
    user = voting["alice"]
    texts = [client.get("/api/voting/stories", headers=user).text]
    for item in client.get("/api/voting/stories", headers=user).json()["stories"]:
        texts.append(client.get(f"/api/voting/stories/{item['anon_number']}", headers=user).text)
    voting_blob = " ".join(texts).lower()
    blob = voting_blob + client.get("/api/contest/current", headers=user).text.lower()
    for nick in NICKS:
        if nick != "alice":
            # название и текст рассказа содержат «Story <nick>», это не утечка автора
            assert nick not in blob.replace("story " + nick, "")
    for forbidden in ("author", "created_at", "updated_at"):
        assert forbidden not in blob
    # внутренние id рассказов выдали бы порядок отправки
    assert '"id"' not in voting_blob


def test_organizer_cannot_see_authors_before_final(client, voting, admin):
    for path in ("/api/results", "/api/voting/stories"):
        assert client.get(path, headers=admin).status_code == 403
    assert "author" not in client.get("/api/admin/stats", headers=admin).text


def test_anon_numbers_are_a_permutation(client, voting):
    seen = set()
    for n, user in voting.items():
        own_titles = {i["title"] for i in client.get("/api/voting/stories", headers=user).json()["stories"]}
        assert f"Story {n}" not in own_titles  # собственная работа в списке отсутствует
        seen |= {number_of(client, user, t) for t in own_titles}
    assert seen == {1, 2, 3, 4, 5}


# ---------- оценивание ----------


def test_cannot_rate_or_star_own_story(client, voting):
    alice = voting["alice"]
    # номер своей работы виден как «дырка» в списке; пробуем его
    mine = ({1, 2, 3, 4, 5} - {i["anon_number"] for i in client.get("/api/voting/stories", headers=alice).json()["stories"]}).pop()
    assert client.get(f"/api/voting/stories/{mine}", headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/rating", json=rating(5), headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/star", headers=alice).status_code == 403


def test_rating_validation_and_update(client, voting):
    alice = voting["alice"]
    n = number_of(client, alice, "Story bob")
    bad = rating(3) | {"style": 6}
    assert client.put(f"/api/voting/stories/{n}/rating", json=bad, headers=alice).status_code == 422
    partial = {k: 3 for k in SCALES[:-1]}
    assert client.put(f"/api/voting/stories/{n}/rating", json=partial, headers=alice).status_code == 422
    assert client.put(f"/api/voting/stories/{n}/rating", json=rating(2), headers=alice).status_code == 200
    assert client.put(f"/api/voting/stories/{n}/rating", json=rating(4), headers=alice).status_code == 200
    assert client.get(f"/api/voting/stories/{n}", headers=alice).json()["my_rating"] == rating(4)


def test_star_limit_and_refund(client, voting):
    alice = voting["alice"]
    nums = [number_of(client, alice, f"Story {n}") for n in ("bob", "carol", "dave", "erin")]
    for n in nums[:3]:
        r = client.put(f"/api/voting/stories/{n}/star", headers=alice)
        assert r.status_code == 200
    assert r.json()["stars_left"] == 0
    # повторная звезда той же работе идемпотентна, а четвёртая другой запрещена
    assert client.put(f"/api/voting/stories/{nums[0]}/star", headers=alice).status_code == 200
    assert client.put(f"/api/voting/stories/{nums[3]}/star", headers=alice).status_code == 409
    # забрали звезду, можно отдать другой
    assert client.delete(f"/api/voting/stories/{nums[0]}/star", headers=alice).json()["stars_left"] == 1
    assert client.put(f"/api/voting/stories/{nums[3]}/star", headers=alice).status_code == 200


def test_non_author_cannot_vote_when_rule_enabled(client, admin, make_user):
    alice, lurker = make_user("alice"), make_user("lurker")
    start_contest(client, admin)
    advance(client, admin, "submission")
    submit(client, alice, "A")
    advance(client, admin, "voting")
    assert client.get("/api/voting/stories", headers=lurker).status_code == 403


# ---------- результаты ----------


def test_results_tops_and_reveal(client, voting, admin):
    # bob: хорошо по слогу, alice: плохо; carol: 5 звёзд-голосов и т.д.
    def vote(voter, title, **scores):
        u = voting[voter]
        n = number_of(client, u, title)
        r = client.put(f"/api/voting/stories/{n}/rating", json=rating(3) | scores, headers=u)
        assert r.status_code == 200, r.text
        return n

    # «Story bob»: style 5 и 3 -> среднее 4.0;  «Story carol»: style 4 и 4 -> 4.0 (ничья по среднему, голосов поровну)
    vote("alice", "Story bob", style=5)
    vote("carol", "Story bob", style=3)
    vote("alice", "Story carol", style=4)
    vote("bob", "Story carol", style=4)
    vote("alice", "Story dave", style=2, dark=5)  # одна оценка

    # звёзды: bob получает 2, carol 1
    for voter, title in (("alice", "Story bob"), ("carol", "Story bob"), ("dave", "Story carol")):
        n = number_of(client, voting[voter], title)
        assert client.put(f"/api/voting/stories/{n}/star", headers=voting[voter]).status_code == 200

    advance(client, admin, "results")
    res = client.get("/api/results", headers=voting["erin"]).json()
    by_key = {s["key"]: s["ranking"] for s in res["scales"]}

    style = by_key["style"]
    assert [e["rank"] for e in style] == [1, 1, 3]  # bob и carol делят 1-е место
    assert {e["author"] for e in style[:2]} == {"bob", "carol"}
    assert style[2]["author"] == "dave" and style[2]["value"] == 2.0

    dark = by_key["dark"]
    assert dark[0]["author"] == "dave" and dark[0]["value"] == 5.0 and dark[0]["rank"] == 1

    # работа без единой оценки в топ по шкалам не попадает
    assert all(e["author"] not in ("alice", "erin") for e in style)

    stars = res["stars"]["ranking"]
    assert [(e["author"], e["value"], e["rank"]) for e in stars] == [("bob", 2, 1), ("carol", 1, 2)]
    assert res["totals"] == {"stories": 5, "ratings": 5, "stars": 3}

    # любой участник теперь может прочитать работу вместе с автором
    n = stars[0]["anon_number"]
    story = client.get(f"/api/results/stories/{n}", headers=voting["erin"]).json()
    assert story["author"] == "bob" and story["stars"] == 2 and story["votes"] == 2
    assert story["scores"]["style"] == 4.0


def test_cannot_vote_after_results(client, voting, admin):
    alice = voting["alice"]
    n = number_of(client, alice, "Story bob")
    advance(client, admin, "results")
    assert client.put(f"/api/voting/stories/{n}/rating", json=rating(5), headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{n}/star", headers=alice).status_code == 403


# ---------- рецензии ----------


def review(client, user, title, text):
    n = number_of(client, user, title)
    return n, client.put(f"/api/voting/stories/{n}/review", json={"body": text}, headers=user)


def test_review_lifecycle_and_validation(client, voting):
    alice = voting["alice"]
    n, r = review(client, alice, "Story bob", "  Первая версия  ")
    assert r.status_code == 200 and r.json() == {"my_review": "Первая версия"}
    # перезапись, а не вторая рецензия
    assert client.put(f"/api/voting/stories/{n}/review", json={"body": "Вторая"}, headers=alice).status_code == 200
    assert client.get(f"/api/voting/stories/{n}", headers=alice).json()["my_review"] == "Вторая"
    items = client.get("/api/voting/stories", headers=alice).json()["stories"]
    assert [i["reviewed"] for i in items if i["anon_number"] == n] == [True]
    # пустая, из пробелов и слишком длинная отклоняются
    for bad in ("", "   \n ", "я" * 5001):
        assert client.put(f"/api/voting/stories/{n}/review", json={"body": bad}, headers=alice).status_code == 422
    assert client.delete(f"/api/voting/stories/{n}/review", headers=alice).json() == {"my_review": None}
    assert client.get(f"/api/voting/stories/{n}", headers=alice).json()["my_review"] is None


def test_cannot_review_own_story_or_outside_voting(client, voting, admin):
    alice = voting["alice"]
    mine = ({1, 2, 3, 4, 5} - {i["anon_number"] for i in client.get("/api/voting/stories", headers=alice).json()["stories"]}).pop()
    assert client.put(f"/api/voting/stories/{mine}/review", json={"body": "хвалю себя"}, headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/review", json={"body": "x"}, headers=admin).status_code == 403
    n = number_of(client, alice, "Story bob")
    advance(client, admin, "results")
    assert client.put(f"/api/voting/stories/{n}/review", json={"body": "поздно"}, headers=alice).status_code == 403
    assert client.delete(f"/api/voting/stories/{n}/review", headers=alice).status_code == 403


def test_non_author_cannot_review_when_rule_enabled(client, admin, make_user):
    alice, lurker = make_user("alice"), make_user("lurker")
    start_contest(client, admin)
    advance(client, admin, "submission")
    submit(client, alice, "A")
    advance(client, admin, "voting")
    assert client.put("/api/voting/stories/1/review", json={"body": "x"}, headers=lurker).status_code == 403


def test_reviews_hidden_until_results_then_readable_and_anonymous(client, voting, admin):
    bob = voting["bob"]
    for voter in ("alice", "carol", "dave"):
        review(client, voting[voter], "Story bob", f"Рецензия от {voter}")
    n = number_of(client, voting["alice"], "Story bob")

    # до финала автор рассказа и остальные рецензий не видят: ни в оценивании, ни в кабинете
    assert client.get("/api/results/stories/1", headers=bob).status_code == 403
    assert client.get("/api/results/stories", headers=bob).status_code == 403
    cab = client.get("/api/me/contests", headers=bob).json()
    detail = client.get(f"/api/me/contests/{cab[0]['id']}", headers=bob).json()
    assert detail["received"] is None and detail["received_hidden"] is True
    assert "Рецензия от" not in client.get("/api/voting/stories", headers=bob).text
    assert "Рецензия от" not in str(detail)

    advance(client, admin, "results")
    story = client.get(f"/api/results/stories/{n}", headers=voting["erin"]).json()
    assert sorted(r["body"] for r in story["reviews"]) == ["Рецензия от alice", "Рецензия от carol", "Рецензия от dave"]
    # авторы рецензий не раскрываются даже в финале: только текст, без полей автора, id и времени
    assert all(set(r) == {"body"} for r in story["reviews"])
    blob = client.get(f"/api/results/stories/{n}", headers=voting["erin"]).text
    for forbidden in ("reviewer", "rater", "created_at", "updated_at", '"id"'):
        assert forbidden not in blob
    # список всех работ: есть и работы без оценок, счётчик рецензий совпадает
    listing = client.get("/api/results/stories", headers=voting["erin"]).json()
    assert len(listing) == 5
    assert next(i for i in listing if i["anon_number"] == n)["reviews"] == 3
    assert next(i for i in listing if i["author"] == "alice")["reviews"] == 0


# ---------- личный кабинет ----------


def test_cabinet_given_during_voting_and_received_after(client, voting, admin):
    alice, bob = voting["alice"], voting["bob"]
    n_bob = number_of(client, alice, "Story bob")
    n_carol = number_of(client, alice, "Story carol")
    client.put(f"/api/voting/stories/{n_bob}/rating", json=rating(5), headers=alice)
    client.put(f"/api/voting/stories/{n_bob}/star", headers=alice)
    client.put(f"/api/voting/stories/{n_carol}/review", json={"body": "Мне понравилось"}, headers=alice)
    client.put(f"/api/voting/stories/{number_of(client, bob, 'Story alice')}/rating", json=rating(2), headers=bob)

    archive = client.get("/api/me/contests", headers=alice).json()
    assert len(archive) == 1
    assert archive[0]["story_title"] == "Story alice"
    assert archive[0]["given"] == {"ratings": 1, "stars": 1, "reviews": 1}
    cid = archive[0]["id"]

    d = client.get(f"/api/me/contests/{cid}", headers=alice).json()
    assert d["story"]["title"] == "Story alice" and d["story"]["anon_number"] is None
    assert d["received"] is None and d["received_hidden"] is True
    by_n = {g["anon_number"]: g for g in d["given"]}
    assert by_n[n_bob]["rating"] == rating(5) and by_n[n_bob]["starred"] and by_n[n_bob]["review"] is None
    assert by_n[n_carol]["review"] == "Мне понравилось" and by_n[n_carol]["rating"] is None
    # пока идёт оценивание, авторы чужих работ в кабинете скрыты
    assert all(g["author"] is None for g in d["given"])
    assert "bob" not in str({k: v for k, v in d.items() if k != "story"}).replace("Story bob", "")

    advance(client, admin, "results")
    d = client.get(f"/api/me/contests/{cid}", headers=alice).json()
    assert d["received_hidden"] is False
    assert d["received"]["votes"] == 1 and d["received"]["stars"] == 0
    assert d["received"]["reviews"] == []
    assert {g["author"] for g in d["given"]} == {"bob", "carol"}
    assert d["story"]["anon_number"] in {1, 2, 3, 4, 5}
    # свои итоги: bob оценил alice на 2, а alice bob'а на 5, так что у alice второе место
    style = next(s for s in d["received"]["scales"] if s["key"] == "style")
    assert style["value"] == 2.0 and style["rank"] == 2
    # рецензия alice на carol видна carol в её кабинете без имени автора
    carol = client.get(f"/api/me/contests/{cid}", headers=voting["carol"]).json()
    assert carol["received"]["reviews"] == [{"body": "Мне понравилось"}]
    assert "alice" not in str(carol["received"])


def test_cabinet_is_private_and_participant_only(client, voting, admin, make_user):
    cid = client.get("/api/me/contests", headers=voting["alice"]).json()[0]["id"]
    outsider = make_user("zed")  # зарегистрирован, но в конкурсе не участвовал
    assert client.get("/api/me/contests", headers=outsider).json() == []
    assert client.get(f"/api/me/contests/{cid}", headers=outsider).status_code == 404
    assert client.get("/api/me/contests", headers=admin).status_code == 403
    assert client.get("/api/me/contests").status_code == 401


def test_cabinet_archives_several_contests(client, voting, admin):
    advance(client, admin, "results")
    start_contest(client, admin, **{})  # второй конкурс
    advance(client, admin, "submission")
    submit(client, voting["alice"], "Second story")
    archive = client.get("/api/me/contests", headers=voting["alice"]).json()
    assert [c["story_title"] for c in archive] == ["Second story", "Story alice"]
    assert archive[0]["phase"] == "submission" and archive[1]["phase"] == "results"
    # у bob во втором конкурсе нет участия, в архиве только первый
    assert [c["story_title"] for c in client.get("/api/me/contests", headers=voting["bob"]).json()] == ["Story bob"]
