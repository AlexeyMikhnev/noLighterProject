from datetime import datetime, timedelta, timezone

import pytest

NICKS = ["alice", "bob", "carol", "dave", "erin"]
SCALES = ["impression", "theme", "style", "mood", "adventure"]


@pytest.fixture()
def lenient(monkeypatch):
    """Отключает правило нарушителей: для тестов механики топов, где голосуют не все и не за всё."""
    monkeypatch.setattr("app.services.violations", lambda *a, **k: {})
    monkeypatch.setattr("app.routers.results.violations", lambda *a, **k: {})


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


def test_story_disclaimer_and_limits(client, admin, make_user):
    user = make_user("alice")
    start_contest(client, admin)
    advance(client, admin, "submission")
    put = lambda **kw: client.put("/api/stories/me", json={"title": "t", "body": "текст"} | kw, headers=user)

    # дисклеймер необязателен
    r = put()
    assert r.status_code == 200 and r.json()["disclaimer"] == ""

    # сохраняется (пробелы по краям срезаются) и меняется
    r = put(disclaimer="  18+, тяжёлая тема \n")
    assert r.json()["disclaimer"] == "18+, тяжёлая тема"
    assert client.get("/api/stories/me", headers=user).json()["disclaimer"] == "18+, тяжёлая тема"
    assert put(disclaimer="").json()["disclaimer"] == ""

    # границы: дисклеймер до 1000, рассказ до 10 000 знаков
    assert put(disclaimer="я" * 1000).status_code == 200
    assert put(disclaimer="я" * 1001).status_code == 422
    assert put(body="я" * 10_000).status_code == 200
    assert put(body="я" * 10_001).status_code == 422


def test_story_richtext_is_sanitized(client, admin, make_user):
    user = make_user("alice")
    start_contest(client, admin)
    advance(client, admin, "submission")
    put = lambda body: client.put("/api/stories/me", json={"title": "t", "body": body}, headers=user)

    # форматирование сохраняется, опасное вырезается
    r = put('<p>Это <strong>важно</strong></p><script>alert(1)</script><p onclick="x()"><a href="javascript:1">ссылка</a></p>')
    assert r.status_code == 200
    assert r.json()["body"] == "<p>Это <strong>важно</strong></p><p>ссылка</p>"

    # обычный текст превращается в абзацы
    assert put("раз\n\nдва").json()["body"] == "<p>раз</p><p>два</p>"

    # лимит считается по видимому тексту, а не по размеру разметки
    marked = "<p>" + "<strong>я</strong>" * 5_000 + "</p>"  # 5000 знаков, ~100 КБ сырого HTML
    assert put(marked).status_code == 422  # сырой HTML выше потолка
    assert put("<p>" + "<em>я</em>" * 3_000 + "</p>").status_code == 200  # ~37 КБ разметки, 3000 знаков
    assert put("<p>" + "я" * 10_001 + "</p>").status_code == 422
    # пустой после очистки текст отклоняется
    assert put("<p> </p><script>x</script>").status_code == 422


def test_survey_is_optional_and_only_aggregated(client, admin, voting):
    alice, bob, carol, dave = (voting[n] for n in ("alice", "bob", "carol", "dave"))
    n = number_of(client, alice, "Story bob")
    url = f"/api/voting/stories/{n}/survey"

    cur = client.get("/api/contest/current", headers=alice).json()
    assert [q["key"] for q in cur["survey"]][:3] == ["genres", "settings", "hero_gender"]
    assert client.get(f"/api/voting/stories/{n}", headers=alice).json()["my_survey"] is None

    full = {
        "genres": ["drama", "drama", "thriller"],
        "settings": ["scifi"],
        "hero_gender": "female",
        "about_children": False,  # «нет» — это ответ, а не пустота
        "about_animals": None,
        "someone_died": True,
        "has_guns": False,
    }
    r = client.put(url, json=full, headers=alice)
    assert r.status_code == 200, r.text
    mine = r.json()["my_survey"]
    assert mine["genres"] == ["drama", "thriller"] and mine["about_children"] is False and mine["about_animals"] is None
    assert client.get(f"/api/voting/stories/{n}", headers=alice).json()["my_survey"] == mine

    # можно ответить частично, ответы можно переписать
    assert client.put(url, json={"genres": ["drama"], "someone_died": True}, headers=carol).status_code == 200

    # мусор отклоняется
    for bad in ({"genres": ["nope"]}, {"hero_gender": "x"}, {"unknown": 1}, {"about_guns": True}):
        assert client.put(url, json=bad, headers=dave).status_code == 422
    # на свой рассказ нельзя
    assert client.put(url, json=full, headers=bob).status_code == 403

    # пустой опросник = ответы удалены, в статистику не попадает
    assert client.put(url, json={"genres": ["comedy"]}, headers=dave).status_code == 200
    assert client.put(url, json={}, headers=dave).json()["my_survey"] is None

    advance(client, admin, "results")
    st = client.get(f"/api/results/stories/{n}", headers=alice).json()["survey"]
    assert st["respondents"] == 2
    q = {x["key"]: x for x in st["questions"]}
    genres = {o["key"]: o["count"] for o in q["genres"]["options"]}
    assert genres["drama"] == 2 and genres["thriller"] == 1 and genres["comedy"] == 0
    died = {o["key"]: o["count"] for o in q["someone_died"]["options"]}
    assert died == {"yes": 2, "no": 0}
    assert q["about_children"]["answered"] == 1 and q["about_animals"]["answered"] == 0
    # по конкурсу в целом тоже только агрегаты
    total = client.get("/api/results", headers=alice).json()["survey"]
    assert total["respondents"] == 2
    assert "rater" not in str(total)


def test_results_mark_authors_who_skipped_mandatory_voting(client, admin, voting):
    """Нарушитель: оценил не все чужие работы или раздал не все звёзды. Текст его показывается, но с пометкой."""

    def act(voter, rate_n, star_n):
        u = voting[voter]
        others = [n for n in NICKS if n != voter]
        for n in others[:rate_n]:
            num = number_of(client, u, f"Story {n}")
            assert client.put(f"/api/voting/stories/{num}/rating", json=rating(4), headers=u).status_code == 200
        for n in others[:star_n]:
            num = number_of(client, u, f"Story {n}")
            assert client.put(f"/api/voting/stories/{num}/star", headers=u).status_code == 200

    act("alice", 4, 3)  # всё выполнено
    act("bob", 4, 2)    # не раздал все звёзды
    act("carol", 3, 3)  # оценил не все работы
    act("dave", 0, 0)   # ничего
    act("erin", 4, 3)   # всё выполнено
    advance(client, admin, "results")

    viewer = voting["alice"]
    items = {i["author"]: i for i in client.get("/api/results/stories", headers=viewer).json()}
    assert items["alice"]["violation"] is None and items["erin"]["violation"] is None
    assert items["bob"]["violation"] == {"ratings": None, "stars": {"done": 2, "required": 3}}
    assert items["carol"]["violation"] == {"ratings": {"done": 3, "required": 4}, "stars": None}
    assert items["dave"]["violation"] == {"ratings": {"done": 0, "required": 4}, "stars": {"done": 0, "required": 3}}
    # рассказ нарушителя остаётся доступным, с той же пометкой
    story = client.get(f"/api/results/stories/{items['dave']['anon_number']}", headers=viewer).json()
    assert story["violation"] == items["dave"]["violation"] and story["body"]
    # в топы и к победителям нарушители не попадают, места остальных считаются без них
    res = client.get("/api/results", headers=viewer).json()
    for sc in res["scales"]:
        assert {e["author"] for e in sc["ranking"]} <= {"alice", "erin"}
    assert {e["author"] for e in next(sc for sc in res["scales"] if sc["key"] == "style")["ranking"]} == {"alice", "erin"}
    stars = res["stars"]["ranking"]
    assert [(e["author"], e["rank"]) for e in stars] == [("alice", 1)]
    # а свои итоги нарушитель в кабинете видит, только без места
    cab = client.get("/api/me/contests", headers=voting["carol"]).json()
    d = client.get(f"/api/me/contests/{cab[0]['id']}", headers=voting["carol"]).json()
    style = next(x for x in d["received"]["scales"] if x["key"] == "style")
    assert style["value"] is not None and style["rank"] is None
    assert d["received"]["violation"] == items["carol"]["violation"]


def test_rules_public_editable_by_organizer_only(client, admin, make_user):
    user = make_user("alice")

    # читать правила можно без входа; пока не сохранены, отдаётся текст по умолчанию
    r = client.get("/api/rules")
    assert r.status_code == 200
    default = r.json()
    assert default["is_default"] is True and "Обязательное при оценивании" in default["body"]

    # редактировать может только организатор
    assert client.put("/api/admin/rules", json={"body": "<p>x</p>"}).status_code in (401, 403)
    assert client.put("/api/admin/rules", json={"body": "<p>x</p>"}, headers=user).status_code == 403
    assert client.delete("/api/admin/rules", headers=user).status_code == 403

    # форматирование сохраняется, опасное вырезается
    html = '<h2>Правила</h2><p onclick="x()"><strong>Важно</strong></p><script>alert(1)</script><ul><li>раз</li></ul>'
    r = client.put("/api/admin/rules", json={"body": html}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "<h2>Правила</h2><p><strong>Важно</strong></p><ul><li>раз</li></ul>"
    pub = client.get("/api/rules").json()
    assert pub["is_default"] is False and pub["body"] == r.json()["body"] and pub["updated_at"]

    # лимит по видимому тексту; пустой текст допустим
    assert client.put("/api/admin/rules", json={"body": "<p>" + "я" * 20_001 + "</p>"}, headers=admin).status_code == 422
    assert client.put("/api/admin/rules", json={"body": ""}, headers=admin).json()["body"] == ""

    # сброс к тексту по умолчанию
    back = client.delete("/api/admin/rules", headers=admin).json()
    assert back["is_default"] is True and back["body"] == default["body"]


def test_disclaimer_shown_to_readers(client, admin, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    start_contest(client, admin)
    advance(client, admin, "submission")
    client.put("/api/stories/me", json={"title": "A", "body": "a", "disclaimer": "осторожно: грусть"}, headers=alice)
    submit(client, bob, "B")
    advance(client, admin, "voting")
    n = number_of(client, bob, "A")
    assert client.get(f"/api/voting/stories/{n}", headers=bob).json()["disclaimer"] == "осторожно: грусть"
    advance(client, admin, "results")
    assert client.get(f"/api/results/stories/{n}", headers=bob).json()["disclaimer"] == "осторожно: грусть"
    cab = client.get("/api/me/contests", headers=alice).json()
    detail = client.get(f"/api/me/contests/{cab[0]['id']}", headers=alice).json()
    assert detail["story"]["disclaimer"] == "осторожно: грусть"


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
        items = client.get("/api/voting/stories", headers=user).json()["stories"]
        # в списке все пять работ без «дырок»; своя помечена и только она
        assert sorted(i["anon_number"] for i in items) == [1, 2, 3, 4, 5]
        assert [i["title"] for i in items if i["mine"]] == [f"Story {n}"]
        seen |= {i["anon_number"] for i in items}
    assert seen == {1, 2, 3, 4, 5}


# ---------- оценивание ----------


def test_cannot_rate_or_star_own_story(client, voting):
    alice = voting["alice"]
    mine = number_of(client, alice, "Story alice")
    # свой рассказ можно прочитать, но в нём нет ничего оценочного
    r = client.get(f"/api/voting/stories/{mine}", headers=alice)
    assert r.status_code == 200
    body = r.json()
    assert body["mine"] is True and body["title"] == "Story alice"
    assert body["my_rating"] is None and body["my_review"] is None and body["my_survey"] is None and body["starred"] is False
    # а оценивать, отмечать звездой, рецензировать и заполнять опросник нельзя
    assert client.put(f"/api/voting/stories/{mine}/rating", json=rating(5), headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/star", headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/review", json={"body": "x"}, headers=alice).status_code == 403
    assert client.put(f"/api/voting/stories/{mine}/survey", json={"genres": ["drama"]}, headers=alice).status_code == 403


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


def test_results_tops_and_reveal(client, voting, admin, lenient):
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
    vote("alice", "Story dave", style=2, mood=5)  # одна оценка

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

    mood = by_key["mood"]
    assert mood[0]["author"] == "dave" and mood[0]["value"] == 5.0 and mood[0]["rank"] == 1

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
    mine = number_of(client, alice, "Story alice")
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


def test_cabinet_given_during_voting_and_received_after(client, voting, admin, lenient):
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
    assert archive[0]["given"] == {"ratings": 1, "stars": 1, "reviews": 1, "guesses": 0}
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


# ---------- угадайка ----------


def marks(client, user, owner, nicknames):
    n = number_of(client, user, f"Story {owner}")
    return n, client.put(f"/api/guess/stories/{n}", json={"nicknames": nicknames}, headers=user)


def test_guess_matrix_payload_has_no_authors(client, voting):
    d = client.get("/api/guess", headers=voting["alice"]).json()
    assert set(d) == {"phase", "stories", "candidates", "marks"}
    assert d["phase"] == "voting" and d["marks"] == {}
    # в столбцах все приславшие, кроме меня, по алфавиту; в строках чужие рассказы
    assert d["candidates"] == ["bob", "carol", "dave", "erin"]
    assert len(d["stories"]) == 4 and all(set(s) == {"anon_number", "title"} for s in d["stories"])
    assert "Story alice" not in {s["title"] for s in d["stories"]}
    blob = client.get("/api/guess", headers=voting["alice"]).text
    for forbidden in ('"id"', "author", "truth", "result", "created_at"):
        assert forbidden not in blob


def test_guess_access_rules(client, voting, admin, make_user):
    assert client.get("/api/guess", headers=admin).status_code == 403
    n = number_of(client, voting["alice"], "Story bob")
    assert client.put(f"/api/guess/stories/{n}", json={"nicknames": []}, headers=admin).status_code == 403
    assert client.get("/api/guess").status_code == 401
    # без рассказа при включённом правиле угадывать нельзя
    lurker = make_user("lurker")
    assert client.get("/api/guess", headers=lurker).status_code == 403


def test_guess_closed_before_voting_and_writes_closed_after(client, admin, make_user, voting):
    alice = voting["alice"]
    n, r = marks(client, alice, "bob", ["carol"])
    assert r.status_code == 200
    advance(client, admin, "results")
    # после итогов можно смотреть, но не менять
    assert client.get("/api/guess", headers=alice).status_code == 200
    assert client.put(f"/api/guess/stories/{n}", json={"nicknames": ["dave"]}, headers=alice).status_code == 403


def test_guess_not_available_during_submission(client, admin, make_user):
    alice = make_user("alice")
    start_contest(client, admin)
    advance(client, admin, "submission")
    submit(client, alice, "A")
    assert client.get("/api/guess", headers=alice).status_code == 403


def test_guess_row_validation_replace_and_clear(client, voting):
    alice = voting["alice"]
    n, r = marks(client, alice, "bob", ["dave", "carol", "carol"])
    # ответ ничего не говорит о верности; дубликаты схлопнуты
    assert r.status_code == 200 and r.json() == {"anon_number": n, "nicknames": ["carol", "dave"]}
    assert marks(client, alice, "bob", ["erin"])[1].json()["nicknames"] == ["erin"]
    assert client.get("/api/guess", headers=alice).json()["marks"] == {str(n): ["erin"]}
    # один и тот же автор в нескольких строках разрешён (в интерфейсе это только предупреждение)
    assert marks(client, alice, "carol", ["erin"])[1].status_code == 200
    # нельзя: неизвестный ник, себя, свой рассказ
    assert marks(client, alice, "dave", ["nobody"])[1].status_code == 422
    assert marks(client, alice, "dave", ["alice"])[1].status_code == 422
    mine = ({1, 2, 3, 4, 5} - {s["anon_number"] for s in client.get("/api/guess", headers=alice).json()["stories"]}).pop()
    assert client.put(f"/api/guess/stories/{mine}", json={"nicknames": ["bob"]}, headers=alice).status_code == 403
    assert client.put(f"/api/guess/stories/{n}", json={"nicknames": [], "extra": 1}, headers=alice).status_code == 422
    # пустой список снимает отметки
    assert marks(client, alice, "bob", [])[1].json()["nicknames"] == []
    assert str(n) not in client.get("/api/guess", headers=alice).json()["marks"]


def test_detective_scoring_places_and_no_feedback_before_results(client, voting, admin, lenient):
    a, b, c, d = (voting[x] for x in ("alice", "bob", "carol", "dave"))
    num = {t: number_of(client, a, f"Story {t}") for t in ("bob", "carol", "dave")}
    assert marks(client, a, "bob", ["bob"])[1].status_code == 200  # верно: 1
    assert marks(client, a, "carol", ["carol", "dave"])[1].status_code == 200  # верно из двух: 0,5
    assert marks(client, a, "dave", ["erin"])[1].status_code == 200  # неверно: 0
    assert marks(client, b, "alice", ["alice", "carol"])[1].status_code == 200  # 0,5
    assert marks(client, b, "erin", ["erin"])[1].status_code == 200  # 1  -> у bob 1,5, ничья с alice
    assert marks(client, c, "dave", ["alice", "bob", "dave", "erin"])[1].status_code == 200  # 1/4
    assert marks(client, d, "carol", ["carol"])[1].status_code == 200  # 1
    # erin ничего не отметила

    # до итогов нет ни правильных ответов, ни очков, ни рейтинга
    assert client.get("/api/results", headers=a).status_code == 403
    d_voting = client.get("/api/guess", headers=a).json()
    assert "truth" not in d_voting and "result" not in d_voting
    cid = client.get("/api/me/contests", headers=a).json()[0]["id"]
    cab = client.get(f"/api/me/contests/{cid}", headers=a).json()
    assert len(cab["guess"]["rows"]) == 3 and cab["guess"]["result"] is None
    assert all(r["author"] is None and r["hit"] is None and r["points"] is None for r in cab["guess"]["rows"])
    assert client.get("/api/me/contests", headers=a).json()[0]["given"]["guesses"] == 3

    advance(client, admin, "results")
    erin = voting["erin"]
    ranking = client.get("/api/results", headers=erin).json()["detective"]["ranking"]
    assert [(e["nickname"], e["value"], e["rank"]) for e in ranking] == [
        ("alice", 1.5, 1),
        ("bob", 1.5, 1),  # равные очки делят место
        ("dave", 1.0, 3),
        ("carol", 0.25, 4),  # отметил всех четверых: 1/4
    ]
    alice_row = next(e for e in ranking if e["nickname"] == "alice")
    assert alice_row["marked"] == 3 and alice_row["hits"] == 2
    # не отметивший ничего (erin) в номинации отсутствует
    assert "erin" not in {e["nickname"] for e in ranking}

    # матрица после итогов: правда и мой результат
    full = client.get("/api/guess", headers=a).json()
    assert full["truth"][str(num["bob"])] == "bob" and full["truth"][str(num["dave"])] == "dave"
    assert full["result"]["rank"] == 1 and full["result"]["value"] == 1.5

    # статистика по рассказу: «Story dave» отмечали alice (мимо) и carol (в точку)
    assert client.get(f"/api/results/stories/{num['dave']}", headers=erin).json()["guessed"] == {"guessers": 2, "hits": 1}
    assert client.get(f"/api/results/stories/{num['carol']}", headers=erin).json()["guessed"] == {"guessers": 2, "hits": 2}

    # кабинет после итогов: разбор по строкам, у не игравшего erin раздела нет
    cab = client.get(f"/api/me/contests/{cid}", headers=a).json()
    rows = {r["title"]: r for r in cab["guess"]["rows"]}
    assert rows["Story carol"]["hit"] is True and rows["Story carol"]["points"] == 0.5
    assert rows["Story dave"]["hit"] is False and rows["Story dave"]["author"] == "dave"
    assert cab["guess"]["result"]["value"] == 1.5
    cab_erin = client.get(f"/api/me/contests/{cid}", headers=erin).json()
    assert cab_erin["guess"] is None
    assert cab_erin["received"]["guessed_by"] == {"guessers": 1, "hits": 1}


def test_detective_respects_violators_and_guess_never_creates_them(client, voting, admin):
    """Угадайка необязательна: не игравший не затронут правилом нарушителей, а сама игра нарушителем не делает."""

    def do_duties(user_nick):
        u = voting[user_nick]
        others = [n for n in NICKS if n != user_nick]
        for n in others:
            num = number_of(client, u, f"Story {n}")
            assert client.put(f"/api/voting/stories/{num}/rating", json=rating(4), headers=u).status_code == 200
        for n in others[:3]:
            num = number_of(client, u, f"Story {n}")
            assert client.put(f"/api/voting/stories/{num}/star", headers=u).status_code == 200

    do_duties("alice")  # обязанности выполнены, в угадайке не играла
    do_duties("carol")  # обязанности выполнены, играла
    # bob обязанностей не выполнил (ни одной оценки), но играл; dave и erin ничего не делали и не играли
    assert marks(client, voting["carol"], "bob", ["bob"])[1].status_code == 200  # верно: 1
    assert marks(client, voting["bob"], "carol", ["carol"])[1].status_code == 200  # верно: 1, но bob нарушитель
    advance(client, admin, "results")

    viewer = voting["erin"]
    det = client.get("/api/results", headers=viewer).json()["detective"]
    assert [(e["nickname"], e["value"], e["rank"]) for e in det["ranking"]] == [("carol", 1.0, 1)]
    assert [(e["nickname"], e["value"]) for e in det["excluded"]] == [("bob", 1.0)]
    # не игравшие (alice, dave, erin) нигде не фигурируют
    shown = {e["nickname"] for e in det["ranking"] + det["excluded"]}
    assert shown == {"carol", "bob"}

    # игра не сделала нарушителем carol и не спасла bob; alice без угадайки по-прежнему чиста
    items = {i["author"]: i for i in client.get("/api/results/stories", headers=viewer).json()}
    assert items["alice"]["violation"] is None and items["carol"]["violation"] is None
    assert items["bob"]["violation"]["ratings"] == {"done": 0, "required": 4}

    # собственный итог: у нарушителя очки есть, места нет
    mine = client.get("/api/guess", headers=voting["bob"]).json()["result"]
    assert mine["excluded"] is True and mine["rank"] is None and mine["value"] == 1.0
    assert client.get("/api/guess", headers=voting["carol"]).json()["result"]["rank"] == 1
    assert client.get("/api/guess", headers=voting["alice"]).json()["result"] is None
