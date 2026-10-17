import { useEffect, useState } from "react";
import { formatDate } from "../api";

function left(ms) {
  const m = Math.max(0, Math.floor(ms / 60000));
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  if (d > 0) return `${d} д ${h} ч`;
  if (h > 0) return `${h} ч ${mm} мин`;
  return `${mm} мин`;
}

export default function Deadline({ iso, label }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);
  if (!iso) return <p className="muted">{label}: срок не ограничен, фазу завершит организатор.</p>;
  const ms = new Date(iso).getTime() - now;
  return (
    <p className="muted">
      {label}: до {formatDate(iso)}
      {ms > 0 ? ` (осталось ${left(ms)})` : " (срок вышел)"}
    </p>
  );
}
