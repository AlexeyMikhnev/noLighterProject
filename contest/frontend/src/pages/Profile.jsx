import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatDate } from "../api";
import { useAuth } from "../auth.jsx";
import Reviews from "../components/Reviews.jsx";
import Disclaimer from "../components/Disclaimer.jsx";
import StoryBody from "../components/StoryBody.jsx";

const PHASE = { draft: "подготовка", submission: "приём работ", voting: "оценивание", results: "завершён" };

function Given({ items, scales, revealed }) {
  if (items.length === 0) return <p className="muted">Вы пока ничего не оценивали и не рецензировали.</p>;
  return (
    <ul className="given">
      {items.map((g) => (
        <li key={g.anon_number} className="given-item">
          <div className="row between">
            <strong>
              №{g.anon_number} · {g.title}
            </strong>
            <span className="muted small">
              {revealed ? `автор: ${g.author}` : "автор скрыт до итогов"}
              {g.starred && <span className="star on"> ★</span>}
            </span>
          </div>
          {g.rating && (
            <p className="small chips">
              {scales.map((s) => (
                <span key={s.key} className="chip">
                  {s.label}: <b>{g.rating[s.key]}</b>
                </span>
              ))}
            </p>
          )}
          {g.review && (
            <blockquote className="review">
              <div className="eyebrow">Ваша рецензия (анонимно)</div>
              <p>{g.review}</p>
            </blockquote>
          )}
        </li>
      ))}
    </ul>
  );
}

function Detail({ id }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setD(null);
    setError("");
    api(`/me/contests/${id}`)
      .then(setD)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Загрузка…</p>;

  return <DetailBody d={d} revealed={d.contest.phase === "results"} />;
}

function DetailBody({ d, revealed }) {
  const [scales, setScales] = useState(d.received?.scales ?? null);

  useEffect(() => {
    if (scales) return;
    api("/contest/current")
      .then((c) => c && setScales(c.scales))
      .catch(() => setScales([]));
  }, [scales]);

  const labels = scales ?? [];
  return (
    <>
      <div className="eyebrow">Конкурс №{d.contest.id} · {PHASE[d.contest.phase]}</div>
      <h2>{d.contest.theme ?? "Тема не объявлена"}</h2>

      <h3>Мой рассказ</h3>
      {d.story ? (
        <>
          <p className="muted small">
            {revealed && d.story.anon_number != null && <>Анонимный номер: №{d.story.anon_number} · </>}
            отправлен {formatDate(d.story.created_at)}
            {d.story.updated_at !== d.story.created_at && `, изменён ${formatDate(d.story.updated_at)}`}
          </p>
          <details>
            <summary>
              <strong>{d.story.title}</strong>
            </summary>
            <Disclaimer text={d.story.disclaimer} />
            <StoryBody html={d.story.body} />
          </details>
        </>
      ) : (
        <p className="muted">В этом конкурсе вы не присылали рассказ.</p>
      )}

      {d.story && (
        <>
          <hr />
          <h3>Что получил мой рассказ</h3>
          {d.received_hidden && (
            <p className="muted">Оценки, звёзды и рецензии откроются после завершения оценивания.</p>
          )}
          {d.received && (
            <>
              <p className="muted small">
                Оценок получено: {d.received.votes} · звёзд: {d.received.stars}
                {d.received.stars_rank != null && ` (место в топе по звёздам: ${d.received.stars_rank})`}
              </p>
              <table className="ranking static">
                <thead>
                  <tr>
                    <th>Шкала</th>
                    <th className="num">Средний балл</th>
                    <th className="num">Место</th>
                  </tr>
                </thead>
                <tbody>
                  {d.received.scales.map((s) => (
                    <tr key={s.key} className={s.rank === 1 ? "first" : ""}>
                      <td>{s.label}</td>
                      <td className="num">{s.value != null ? s.value.toFixed(2) : "—"}</td>
                      <td className="num">{s.rank ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Reviews reviews={d.received.reviews} title="Рецензии на мой рассказ" />
            </>
          )}
        </>
      )}

      <hr />
      <h3>Мои оценки и рецензии</h3>
      <Given items={d.given} scales={labels} revealed={revealed} />
    </>
  );
}

export default function Profile() {
  const { user } = useAuth();
  const [list, setList] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/me/contests")
      .then((l) => {
        setList(l);
        if (l.length) setSelected(l[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (user.role === "organizer")
    return (
      <div className="card">
        <p>Организатор в конкурсах не участвует, личного архива у него нет.</p>
      </div>
    );
  if (error) return <p className="error">{error}</p>;
  if (!list) return <p className="center">Загрузка…</p>;

  return (
    <>
      <h1>Личный кабинет</h1>
      <p className="muted">
        {user.nickname} · архив ваших участий. Полученные оценки и рецензии открываются после итогов конкурса;
        авторы рецензий не раскрываются никогда.
      </p>
      {list.length === 0 ? (
        <div className="card">
          <p>
            Вы ещё не участвовали ни в одном конкурсе. Пришлите рассказ на <Link to="/">главной странице</Link>.
          </p>
        </div>
      ) : (
        <div className="voting">
          <aside className="card list-pane">
            <h2>Мои конкурсы</h2>
            <ul className="story-list">
              {list.map((c) => (
                <li key={c.id}>
                  <button className={c.id === selected ? "active" : ""} onClick={() => setSelected(c.id)}>
                    <span className="num">№{c.id}</span>
                    <span className="t">
                      {c.theme ?? "Без темы"}
                      <span className="muted small block">
                        {c.story_title ? `«${c.story_title}»` : "без рассказа"} · {PHASE[c.phase]}
                      </span>
                      <span className="muted small block">
                        оценок {c.given.ratings} · звёзд {c.given.stars} · рецензий {c.given.reviews}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <section className="card reader">{selected && <Detail id={selected} />}</section>
        </div>
      )}
    </>
  );
}
