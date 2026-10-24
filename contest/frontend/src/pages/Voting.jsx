import { useCallback, useEffect, useState } from "react";
import { api, countWords } from "../api";
import Deadline from "../components/Deadline.jsx";
import ScaleInput from "../components/ScaleInput.jsx";
import Disclaimer from "../components/Disclaimer.jsx";
import StoryBody from "../components/StoryBody.jsx";
import SurveyForm, { emptySurvey, normSurvey } from "../components/SurveyForm.jsx";

const MAX_REVIEW = 5000;
const HIDE_KEY = "voting:hideRated";
const HIDE_TEXT_KEY = "voting:hideText";

// Переключатели интерфейса помним в браузере; localStorage может быть недоступен.
function loadFlag(key) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function saveFlag(key, on) {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch {}
}

export default function Voting({ contest, reload }) {
  const scales = contest.scales;
  const [list, setList] = useState(null);
  const [starsLeft, setStarsLeft] = useState(contest.stars_total);
  const [selected, setSelected] = useState(null); // anon_number
  const [story, setStory] = useState(null);
  const [draft, setDraft] = useState({});
  const [reviewDraft, setReviewDraft] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [surveyDraft, setSurveyDraft] = useState(emptySurvey);
  const [surveyNote, setSurveyNote] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [hideRated, setHideRated] = useState(() => loadFlag(HIDE_KEY));
  // Свёрнутый текст остаётся свёрнутым и у следующих рассказов: удобно быстро проставлять оценки и звёзды.
  const [hideText, setHideText] = useState(() => loadFlag(HIDE_TEXT_KEY));

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
    setSurveyNote("");
    try {
      const s = await api(`/voting/stories/${n}`);
      setStory(s);
      setDraft(s.my_rating || {});
      setReviewDraft(s.my_review || "");
      setSurveyDraft({ ...emptySurvey, ...(s.my_survey || {}) });
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

  const questions = contest.survey ?? [];
  const surveyChanged =
    story &&
    JSON.stringify(normSurvey(questions, surveyDraft)) !== JSON.stringify(normSurvey(questions, story.my_survey ?? {}));

  const saveSurvey = async () => {
    setBusy(true);
    setSurveyNote("");
    try {
      const res = await api(`/voting/stories/${selected}/survey`, {
        method: "PUT",
        body: normSurvey(questions, surveyDraft),
      });
      setStory({ ...story, my_survey: res.my_survey });
      setSurveyDraft({ ...emptySurvey, ...(res.my_survey || {}) });
      setSurveyNote(res.my_survey ? "Ответы сохранены" : "Ответы удалены");
    } catch (e) {
      setSurveyNote(e.message);
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

  const toggleHide = (on) => {
    setHideRated(on);
    saveFlag(HIDE_KEY, on);
  };

  const toggleText = () => {
    setHideText(!hideText);
    saveFlag(HIDE_TEXT_KEY, !hideText);
  };

  // Счётчики считаем по чужим работам: свой рассказ в списке есть, но оценить его нельзя.
  const others = list.filter((i) => !i.mine);
  const rated = others.filter((i) => i.rated).length;
  // Открытый рассказ не прячем, даже если только что его оценили: иначе он «убежит» из списка под рукой.
  const visible = hideRated ? list.filter((i) => !i.rated || i.anon_number === selected) : list;
  const total = contest.stars_total;

  return (
    <div className="voting">
      <aside className="card list-pane">
        <h2>Работы</h2>
        <Deadline iso={contest.voting_ends_at} label="Оценивание" />
        <p>
          Оценено <strong>{rated}</strong> из {others.length}
        </p>
        <p className="stars-left" title="Каждой звездой можно отметить один рассказ">
          {Array.from({ length: total }, (_, i) => (
            <span key={i} className={i < starsLeft ? "star on" : "star"}>
              ★
            </span>
          ))}
          <span className="muted small"> осталось {starsLeft} из {total}</span>
        </p>
        <p className="muted small">Авторы скрыты до публикации результатов. Ваш рассказ тоже в списке, под общим номером: его можно прочитать, но не оценить.</p>
        {list.length > 0 && (
          <label className="inline check">
            <input type="checkbox" checked={hideRated} onChange={(e) => toggleHide(e.target.checked)} /> Скрыть оценённое
          </label>
        )}
        {others.length === 0 && <p>Пока нет чужих рассказов для оценки.</p>}
        {hideRated && others.length > 0 && visible.every((i) => i.mine) && <p className="muted">Все работы оценены.</p>}
        <ul className="story-list">
          {visible.map((i) => (
            <li key={i.anon_number}>
              <button className={i.anon_number === selected ? "active" : ""} onClick={() => open(i.anon_number)}>
                <span className="num">№{i.anon_number}</span>
                <span className="t">{i.title}</span>
                <span className="meta">
                  {i.mine && <span className="mine-badge">ваш</span>}
                  {i.reviewed && <span title="Есть ваша рецензия">✎</span>}
                  {i.starred && <span className="star on">★</span>}
                  {!i.mine && (i.rated ? <span className="ok">✓</span> : <span className="muted">·</span>)}
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
            <div className="eyebrow">Рассказ №{story.anon_number}{story.mine && " · ваш"}</div>
            <div className="row between">
              <h2>{story.title}</h2>
              <button type="button" aria-expanded={!hideText} onClick={toggleText}>
                {hideText ? "Показать текст" : "Скрыть текст"}
              </button>
            </div>
            <Disclaimer text={story.disclaimer} />
            {hideText ? (
              <p className="muted small">Текст рассказа скрыт. Нажмите «Показать текст», чтобы прочитать.</p>
            ) : (
              <StoryBody html={story.body} />
            )}

            {story.mine ? (
              <>
                <hr />
                <p className="muted">
                  Это ваш рассказ. Его можно перечитать здесь, но оценить, отметить звездой, прорецензировать или
                  заполнить опросник нельзя. Оценки и рецензии вы увидите в финале.
                </p>
              </>
            ) : (
              <>
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

            {questions.length > 0 && (
              <>
                <hr />
                <h3>Опросник</h3>
                <p className="muted small">
                  Необязательно, нужен только для статистики и никак не влияет на оценки и топы. Итоги по рассказу и
                  по всему конкурсу будут показаны в финале, без привязки к людям.
                </p>
                <SurveyForm questions={questions} value={surveyDraft} onChange={setSurveyDraft} />
                <div className="row">
                  <button className="primary" disabled={!surveyChanged || busy} onClick={saveSurvey}>
                    Сохранить ответы
                  </button>
                  {surveyDraft !== emptySurvey && (
                    <button type="button" className="link" onClick={() => setSurveyDraft(emptySurvey)}>
                      Сбросить
                    </button>
                  )}
                </div>
                {surveyNote && <p className="note">{surveyNote}</p>}
              </>
            )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
