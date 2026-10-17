import { useCallback, useEffect, useState } from "react";
import { api, countWords } from "../api";
import Deadline from "../components/Deadline.jsx";
import ScaleInput from "../components/ScaleInput.jsx";

const MAX_REVIEW = 5000;

export default function Voting({ contest, reload }) {
  const scales = contest.scales;
  const [list, setList] = useState(null);
  const [starsLeft, setStarsLeft] = useState(contest.stars_total);
  const [selected, setSelected] = useState(null); // anon_number
  const [story, setStory] = useState(null);
  const [draft, setDraft] = useState({});
  const [reviewDraft, setReviewDraft] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const data = await api("/voting/stories");
      setList(data.stories);
      setStarsLeft(data.stars_left);
      setError("");
    } catch (e) {
      setError(e.message);
      reload();
    }
  }, [reload]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const open = async (n) => {
    setSelected(n);
    setStory(null);
    setNote("");
    setReviewNote("");
    try {
      const s = await api(`/voting/stories/${n}`);
      setStory(s);
      setDraft(s.my_rating || {});
      setReviewDraft(s.my_review || "");
    } catch (e) {
      setError(e.message);
    }
  };

  const patchItem = (n, patch) =>
    setList((l) => l.map((i) => (i.anon_number === n ? { ...i, ...patch } : i)));

  const complete = scales.every((s) => draft[s.key]);
  const changed = story && scales.some((s) => (story.my_rating?.[s.key] ?? 0) !== (draft[s.key] ?? 0));

  const saveRating = async () => {
    setBusy(true);
    setNote("");
    try {
      const item = await api(`/voting/stories/${selected}/rating`, { method: "PUT", body: draft });
      patchItem(selected, item);
      setStory({ ...story, my_rating: { ...draft } });
      setNote("Оценка сохранена");
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy(false);
    }
  };

  const reviewChanged = story && reviewDraft.trim() !== (story.my_review || "");

  const saveReview = async () => {
    setBusy(true);
    setReviewNote("");
    try {
      const res = await api(`/voting/stories/${selected}/review`, { method: "PUT", body: { body: reviewDraft } });
      setStory({ ...story, my_review: res.my_review });
      setReviewDraft(res.my_review);
      patchItem(selected, { reviewed: true });
      setReviewNote("Рецензия сохранена");
    } catch (e) {
      setReviewNote(e.message);
    } finally {
      setBusy(false);
    }
  };

  const deleteReview = async () => {
    if (!window.confirm("Удалить вашу рецензию на этот рассказ?")) return;
    setBusy(true);
    setReviewNote("");
    try {
      await api(`/voting/stories/${selected}/review`, { method: "DELETE" });
      setStory({ ...story, my_review: null });
      setReviewDraft("");
      patchItem(selected, { reviewed: false });
      setReviewNote("Рецензия удалена");
    } catch (e) {
      setReviewNote(e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleStar = async () => {
    setNote("");
    try {
      const res = await api(`/voting/stories/${selected}/star`, {
        method: story.starred ? "DELETE" : "PUT",
      });
      setStory({ ...story, starred: res.starred });
      setStarsLeft(res.stars_left);
      patchItem(selected, { starred: res.starred });
    } catch (e) {
      setNote(e.message);
    }
  };

  if (error && !list) return <p className="error">{error}</p>;
  if (!list) return <p className="center">Загрузка…</p>;

  const rated = list.filter((i) => i.rated).length;
  const total = contest.stars_total;

  return (
    <div className="voting">
      <aside className="card list-pane">
        <h2>Работы</h2>
        <Deadline iso={contest.voting_ends_at} label="Оценивание" />
        <p>
          Оценено <strong>{rated}</strong> из {list.length}
        </p>
        <p className="stars-left" title="Каждой звездой можно отметить один рассказ">
          {Array.from({ length: total }, (_, i) => (
            <span key={i} className={i < starsLeft ? "star on" : "star"}>
              ★
            </span>
          ))}
          <span className="muted small"> осталось {starsLeft} из {total}</span>
        </p>
        <p className="muted small">Авторы скрыты до публикации результатов. Свой рассказ вы тут не увидите.</p>
        {list.length === 0 && <p>Пока нет рассказов для оценки.</p>}
        <ul className="story-list">
          {list.map((i) => (
            <li key={i.anon_number}>
              <button className={i.anon_number === selected ? "active" : ""} onClick={() => open(i.anon_number)}>
                <span className="num">№{i.anon_number}</span>
                <span className="t">{i.title}</span>
                <span className="meta">
                  {i.reviewed && <span title="Есть ваша рецензия">✎</span>}
                  {i.starred && <span className="star on">★</span>}
                  {i.rated ? <span className="ok">✓</span> : <span className="muted">·</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="card reader">
        {!selected && <p className="muted">Выберите рассказ слева.</p>}
        {selected && !story && <p className="muted">Загрузка…</p>}
        {story && (
          <>
            <div className="eyebrow">Рассказ №{story.anon_number}</div>
            <h2>{story.title}</h2>
            <article className="story-body">{story.body}</article>

            <hr />
            <h3>Ваша оценка</h3>
            {scales.map((s) => (
              <ScaleInput
                key={s.key}
                label={s.label}
                hint={s.hint}
                value={draft[s.key]}
                onChange={(v) => setDraft({ ...draft, [s.key]: v })}
              />
            ))}
            <div className="row">
              <button className="primary" disabled={!complete || !changed || busy} onClick={saveRating}>
                {story.my_rating ? "Обновить оценку" : "Сохранить оценку"}
              </button>
              <button
                className={story.starred ? "star-btn on" : "star-btn"}
                disabled={!story.starred && starsLeft <= 0}
                onClick={toggleStar}
              >
                {story.starred ? "★ Звезда отдана (забрать)" : "☆ Отдать звезду"}
              </button>
            </div>
            {!complete && <p className="muted small">Чтобы сохранить, выставьте оценку по всем шкалам.</p>}
            {note && <p className="note">{note}</p>}

            <hr />
            <h3>Анонимная рецензия</h3>
            <p className="muted small">
              Необязательно. Автор рассказа прочтёт рецензию после завершения оценивания, как и остальные участники.
              Ваше имя не раскрывается никогда, даже в финале. Не подписывайтесь и не пишите того, что выдаст вас.
            </p>
            <textarea
              className="review-text"
              rows={6}
              maxLength={MAX_REVIEW}
              value={reviewDraft}
              onChange={(e) => setReviewDraft(e.target.value)}
              placeholder="Что получилось, что бы вы изменили, что запомнилось…"
              aria-label="Текст рецензии"
            />
            <div className="row between">
              <span className="muted small">
                {countWords(reviewDraft)} сл. · {reviewDraft.length} / {MAX_REVIEW}
              </span>
              <span className="row">
                {story.my_review && (
                  <button className="danger" disabled={busy} onClick={deleteReview}>
                    Удалить
                  </button>
                )}
                <button className="primary" disabled={!reviewDraft.trim() || !reviewChanged || busy} onClick={saveReview}>
                  {story.my_review ? "Обновить рецензию" : "Сохранить рецензию"}
                </button>
              </span>
            </div>
            {reviewNote && <p className="note">{reviewNote}</p>}
          </>
        )}
      </section>
    </div>
  );
}
