import { useEffect, useState } from "react";
import { api, formatDate } from "../api";
import Deadline from "../components/Deadline.jsx";
import RichEditor from "../components/RichEditor.jsx";

const MAX_BODY = 10000;

export default function Submission({ contest, reload }) {
  const [saved, setSaved] = useState(undefined); // undefined = грузится, null = ещё нет
  const [title, setTitle] = useState("");
  // Текст живёт в редакторе; здесь его HTML. baseline — HTML на момент загрузки/сохранения:
  // сравнивать с ответом сервера нельзя, редактор записывает разметку чуть иначе.
  const [body, setBody] = useState("");
  const [baseline, setBaseline] = useState("");
  const [len, setLen] = useState(0);
  const [words, setWords] = useState(0);
  const [editorKey, setEditorKey] = useState(0);
  const [disclaimer, setDisclaimer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/stories/me")
      .then((s) => {
        setSaved(s);
        if (s) {
          setTitle(s.title);
          setBody(s.body);
          setBaseline(s.body);
          setDisclaimer(s.disclaimer ?? "");
        }
      })
      .catch((e) => setError(e.message));
  }, []);

  const dirty =
    saved !== undefined &&
    ((saved?.title ?? "") !== title.trim() ||
      body !== baseline ||
      (saved?.disclaimer ?? "") !== disclaimer.trim());

  // Предупреждение при закрытии вкладки с несохранённым текстом.
  useEffect(() => {
    if (!dirty || !(title || body || disclaimer)) return;
    const h = (e) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty, title, body, disclaimer]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSaved(await api("/stories/me", { method: "PUT", body: { title, body, disclaimer } }));
      setBaseline(body);
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
      setBaseline("");
      setLen(0);
      setWords(0);
      setDisclaimer("");
      setEditorKey((k) => k + 1); // пересоздать редактор пустым
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
        Доступно базовое форматирование: жирный, курсив, подчёркивание, подзаголовки, цитаты, списки и разделитель
        сцен. Ссылок, картинок и других стилей нет. Править рассказ можно до конца приёма работ. Не подписывайтесь в тексте: конкурс анонимный.
      </p>
      <label>
        Название
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      </label>
      <label>
        Дисклеймер <span className="muted small">(необязательно)</span>
        <textarea
          value={disclaimer}
          onChange={(e) => setDisclaimer(e.target.value)}
          rows={3}
          maxLength={1000}
          placeholder="Например: жанр, возрастные ограничения, предупреждения о тяжёлых темах. Читатели увидят это перед рассказом."
        />
      </label>
      <div className="row between">
        <span />
        <span className="muted small">{disclaimer.length} / 1000 знаков</span>
      </div>
      <div className="field-label">Текст</div>
      <RichEditor
        key={editorKey}
        initialHtml={body}
        onReady={(html, n, w) => {
          // редактор нормализует загруженный HTML: принимаем его вид за исходный
          setBody(html);
          setBaseline(html);
          setLen(n);
          setWords(w);
        }}
        onChange={(html, n, w) => {
          setBody(html);
          setLen(n);
          setWords(w);
        }}
      />
      <div className="row between">
        <span className="muted small">
          {words} слов · {len} / {MAX_BODY} знаков
          {len > MAX_BODY && <span className="error"> · слишком длинно</span>}
        </span>
        <span className="muted small">
          {saved ? `Сохранено ${formatDate(saved.updated_at)}${dirty ? " (есть несохранённые правки)" : ""}` : "Ещё не отправлено"}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button className="primary" disabled={busy || !dirty || len === 0 || len > MAX_BODY}>
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
