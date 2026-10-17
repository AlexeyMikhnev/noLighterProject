import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Reviews from "../components/Reviews.jsx";

function fmt(v, isStars) {
  return isStars ? String(v) : v.toFixed(2);
}

export default function Results({ contest }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("stars");
  const [open, setOpen] = useState(null); // раскрытый рассказ
  const [story, setStory] = useState(null);
  const [all, setAll] = useState(null); // все работы, в том числе не попавшие в топы

  useEffect(() => {
    api("/results")
      .then(setData)
      .catch((e) => setError(e.message));
    api("/results/stories")
      .then(setAll)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (open == null) return setStory(null);
    api(`/results/stories/${open}`)
      .then(setStory)
      .catch((e) => setError(e.message));
  }, [open]);

  if (error) return <p className="error">{error}</p>;
  if (!data || !all) return <p className="center">Загрузка…</p>;

  const tabs = [
    { key: "stars", label: "★ Звёзды", ranking: data.stars.ranking, isStars: true },
    ...data.scales.map((s) => ({ key: s.key, label: s.label, ranking: s.ranking, isStars: false })),
    { key: "all", label: "Все работы и рецензии", all: true },
  ];
  const current = tabs.find((t) => t.key === tab);
  const winners = current.all ? [] : current.ranking.filter((e) => e.rank === 1);

  return (
    <div className="card">
      <h2>Итоги конкурса</h2>
      <p className="muted">
        Авторы раскрыты. Топы считаются отдельно по каждой шкале (средняя оценка) и отдельно по звёздам.
        Всего работ: {data.totals.stories}, оценок: {data.totals.ratings}, звёзд: {data.totals.stars}.
      </p>

      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={t.key === tab}
            className={t.key === tab ? "on" : ""}
            onClick={() => {
              setTab(t.key);
              setOpen(null);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {winners.length > 0 && (
        <p className="winner">
          🏆 {winners.length > 1 ? "Победители" : "Победитель"} в номинации «{current.label.replace("★ ", "")}»:{" "}
          <strong>{winners.map((w) => `${w.author} — «${w.title}»`).join("; ")}</strong>
        </p>
      )}

      {current.all ? (
        <>
          <table className="ranking">
            <thead>
              <tr>
                <th>№</th>
                <th>Рассказ</th>
                <th>Автор</th>
                <th className="num">Слов</th>
                <th className="num">Рецензий</th>
              </tr>
            </thead>
            <tbody>
              {all.map((e) => (
                <tr key={e.anon_number} onClick={() => setOpen(open === e.anon_number ? null : e.anon_number)}>
                  <td>{e.anon_number}</td>
                  <td>{e.title}</td>
                  <td>{e.author}</td>
                  <td className="num">{e.words}</td>
                  <td className="num">{e.reviews}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : current.ranking.length === 0 ? (
        <p className="muted">В этой номинации данных нет.</p>
      ) : (
        <table className="ranking">
          <thead>
            <tr>
              <th>Место</th>
              <th>№</th>
              <th>Рассказ</th>
              <th>Автор</th>
              <th className="num">{current.isStars ? "Звёзд" : "Средний балл"}</th>
              {!current.isStars && <th className="num">Оценок</th>}
            </tr>
          </thead>
          <tbody>
            {current.ranking.map((e) => (
              <tr
                key={e.anon_number}
                className={e.rank === 1 ? "first" : ""}
                onClick={() => setOpen(open === e.anon_number ? null : e.anon_number)}
              >
                <td>{e.rank}</td>
                <td>{e.anon_number}</td>
                <td>{e.title}</td>
                <td>{e.author}</td>
                <td className="num">{fmt(e.value, current.isStars)}</td>
                {!current.isStars && <td className="num">{e.votes}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">
        Нажмите на строку, чтобы прочитать рассказ, увидеть его оценки и рецензии. Рецензенты остаются анонимными.
        Свои оценки и рецензии, а также архив прошлых конкурсов, ищите в <Link to="/profile">личном кабинете</Link>.
      </p>

      {story && (
        <section className="result-story">
          <div className="eyebrow">
            №{story.anon_number} · автор: {story.author}
          </div>
          <h3>{story.title}</h3>
          <p className="muted small">
            Оценок: {story.votes} · звёзд: {story.stars}
            {story.scores &&
              " · " + contest.scales.map((s) => `${s.label}: ${story.scores[s.key].toFixed(2)}`).join(" · ")}
          </p>
          <article className="story-body">{story.body}</article>
          <Reviews reviews={story.reviews} />
        </section>
      )}
    </div>
  );
}
