import { useEffect, useState } from "react";
import { api, countWords, formatDate } from "../api";
import Deadline from "../components/Deadline.jsx";

export default function Submission({ contest, reload }) {
  const [saved, setSaved] = useState(undefined); // undefined = грузится, null = ещё нет
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/stories/me")
      .then((s) => {
        setSaved(s);
        if (s) {
          setTitle(s.title);
          setBody(s.body);
        }
      })
      .catch((e) => setError(e.message));
  }, []);

  const dirty =
    saved !== undefined && ((saved?.title ?? "") !== title.trim() || (saved?.body ?? "") !== body.trim());

  // Предупреждение при закрытии вкладки с несохранённым текстом.
  useEffect(() => {
    if (!dirty || !(title || body)) return;
    const h = (e) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty, title, body]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSaved(await api("/stories/me", { method: "PUT", body: { title, body } }));
      reload();
    } catch (err) {
      setError(err.message);
      reload(); // возможно, фаза уже сменилась
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Удалить рассказ?")) return;
    try {
      await api("/stories/me", { method: "DELETE" });
      setSaved(null);
      setTitle("");
      setBody("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  if (saved === undefined && !error) return <p className="center">Загрузка…</p>;

  return (
    <form className="card" onSubmit={save}>
      <h2>Ваш рассказ</h2>
      <Deadline iso={contest.submission_ends_at} label="Приём работ" />
      <p className="muted small">
        Только простой текст, без форматирования. Абзацы разделяйте пустой строкой. Править рассказ можно до конца
        приёма работ. Не подписывайтесь в тексте: конкурс анонимный.
      </p>
      <label>
        Название
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      </label>
      <label>
        Текст
        <textarea
          className="story-text"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={18}
          maxLength={60000}
          required
        />
      </label>
      <div className="row between">
        <span className="muted small">{countWords(body)} слов · {body.length} / 60000 знаков</span>
        <span className="muted small">
          {saved ? `Сохранено ${formatDate(saved.updated_at)}${dirty ? " (есть несохранённые правки)" : ""}` : "Ещё не отправлено"}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button className="primary" disabled={busy || !dirty}>
          {saved ? "Сохранить изменения" : "Отправить рассказ"}
        </button>
        {saved && (
          <button type="button" className="danger" onClick={remove}>
            Удалить
          </button>
        )}
      </div>
    </form>
  );
}
