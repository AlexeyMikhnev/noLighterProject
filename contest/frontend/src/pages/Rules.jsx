import { useEffect, useState } from "react";
import { api, formatDate } from "../api";
import StoryBody from "../components/StoryBody.jsx";

/** Правила конкурса. Страница публичная: читать их можно и до входа. */
export default function Rules() {
  const [rules, setRules] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/rules")
      .then(setRules)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!rules) return <p className="center">Загрузка…</p>;

  return (
    <div className="card rules-page">
      <h1>Правила конкурса</h1>
      {rules.body ? <StoryBody html={rules.body} /> : <p className="muted">Правила пока не опубликованы.</p>}
      {rules.updated_at && <p className="muted small">Обновлено {formatDate(rules.updated_at)}</p>}
    </div>
  );
}
