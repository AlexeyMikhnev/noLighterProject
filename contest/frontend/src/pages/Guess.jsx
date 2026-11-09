import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

const fmt = (v) => String(Math.round(v * 100) / 100).replace(".", ",");

// Одна клетка. Вынесена и мемоизирована: при наведении мыши матрица не перерисовывается.
const Cell = memo(function Cell({ r, c, n, nick, marked, mode, onToggle }) {
  const cls = "cell" + (mode ? " " + mode : marked ? " on" : "");
  const sign = mode === "hit" ? "✓" : mode === "miss" ? "✕" : mode === "truth" ? "●" : marked ? "✓" : "";
  return (
    <td data-r={r} data-c={c}>
      <button
        type="button"
        className={cls}
        aria-pressed={marked}
        aria-label={`Рассказ №${n}: автор — ${nick}`}
        disabled={!onToggle}
        onClick={onToggle ? () => onToggle(n, nick) : undefined}
      >
        {sign}
      </button>
    </td>
  );
});

export default function Guess() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [marks, setMarks] = useState({}); // anon_number -> [ник, ...]
  const [error, setError] = useState("");
  const [status, setStatus] = useState(""); // "", "saving", "saved", "error: ..."
  const [hover, setHover] = useState({ r: null, c: null });
  const queue = useRef({}); // очередь запросов по строкам: ответы не обгоняют друг друга
  const marksRef = useRef({}); // актуальные отметки: обновляются синхронно, до перерисовки
  const pending = useRef(0);

  const load = useCallback(async () => {
    try {
      const d = await api("/guess");
      marksRef.current = d.marks;
      setData(d);
      setMarks(d.marks);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (user.role !== "organizer") load();
  }, [load, user.role]);

  const editable = data?.phase === "voting";

  const toggle = useCallback(
    (n, nick) => {
      const cur = marksRef.current[n] || [];
      const next = cur.includes(nick) ? cur.filter((x) => x !== nick) : [...cur, nick];
      marksRef.current = { ...marksRef.current, [n]: next };
      setMarks(marksRef.current);
      setStatus("saving");
      pending.current += 1;
      // Запросы по одной строке идут по очереди и каждый шлёт самое свежее состояние строки.
      const prev = queue.current[n] || Promise.resolve();
      queue.current[n] = prev
        .then(() => api(`/guess/stories/${n}`, { method: "PUT", body: { nicknames: marksRef.current[n] || [] } }))
        .then(() => {
          pending.current -= 1;
          if (pending.current === 0) setStatus("saved");
        })
        .catch((e) => {
          pending.current -= 1;
          setStatus("error: " + e.message);
          load(); // возвращаем то, что реально сохранено на сервере
        });
    },
    [load]
  );

  // Сколько раз каждый участник отмечен в разных строках.
  const dup = useMemo(() => {
    const count = {};
    Object.values(marks).forEach((row) => row.forEach((nick) => (count[nick] = (count[nick] || 0) + 1)));
    return count;
  }, [marks]);

  const onOver = (e) => {
    const el = e.target.closest("[data-r],[data-c]");
    const r = el?.dataset.r ?? null;
    const c = el?.dataset.c ?? null;
    setHover((h) => (h.r === r && h.c === c ? h : { r, c }));
  };

  if (user.role === "organizer")
    return (
      <div className="card">
        <p>Организатор в конкурсе не участвует, угадайки у него нет.</p>
      </div>
    );
  if (error && !data)
    return (
      <div className="card">
        <h1>Угадайка</h1>
        <p className="error">{error}</p>
        <p>
          <Link to="/">На главную</Link>
        </p>
      </div>
    );
  if (!data) return <p className="center">Загрузка…</p>;

  const { stories, candidates, truth, result } = data;
  const rowsMarked = stories.filter((s) => (marks[s.anon_number] || []).length > 0).length;
  const repeated = candidates.filter((c) => (dup[c] || 0) > 1);

  const cellMode = (n, nick, marked) => {
    if (!truth) return null;
    const isTruth = truth[n] === nick;
    if (marked) return isTruth ? "hit" : "miss";
    return isTruth ? "truth" : null;
  };

  const rowPoints = (n) => {
    const row = marks[n] || [];
    if (!row.length) return null;
    return row.includes(truth?.[n]) ? 1 / row.length : 0;
  };

  return (
    <>
      <h1>Угадайка</h1>
      <div className="card">
        <p>
          Необязательная игра: отметьте в строке рассказа его возможного автора. Можно отметить нескольких: за верный
          ответ вы получите <b>1/k балла</b>, где k — число отметок в строке (двое — по 0,5).
        </p>
        <details className="rules">
          <summary>Подробнее о правилах</summary>
          <p>
            Трое — по 0,33 и так далее. Отметить сразу всех не выгодно: ожидаемый выигрыш от этого не растёт. На
            оценки, звёзды и топы рассказов игра не влияет, результат попадёт в номинацию «Лучший детектив» после итогов.
            Тот, кто ничего не отметил, в номинации не участвует.
          </p>
          {editable ? (
            <p className="muted small">
              Верность отметок до итогов не показывается. Каждая отметка сохраняется сразу. Своего ника в столбцах
              нет: вы точно знаете, что чужой рассказ написали не вы.
            </p>
          ) : (
            <p className="muted small">Оценивание завершено, отметки больше менять нельзя.</p>
          )}
        </details>

        {truth && (
          <p className="winner">
            {result ? (
              result.excluded ? (
                <>
                  🔍 Ваши очки: <strong>{fmt(result.value)}</strong> · вне зачёта: вы не выполнили обязательное оценивание,
                  поэтому места в номинации «Лучший детектив» у вас нет.
                </>
              ) : (
                <>
                  🔍 Ваши очки: <strong>{fmt(result.value)}</strong> · место {result.rank} · верных строк {result.hits} из{" "}
                  {result.marked}. Общий рейтинг — на вкладке «Лучший детектив» в <Link to="/">итогах</Link>.
                </>
              )
            ) : (
              <>Вы ничего не отметили, поэтому в номинации «Лучший детектив» вас нет.</>
            )}
          </p>
        )}

        <div className="row between">
          <span>
            Отмечено рассказов: <strong>{rowsMarked}</strong> из {stories.length}
          </span>
          <span className="small" aria-live="polite">
            {status === "saving" && <span className="muted">Сохраняю…</span>}
            {status === "saved" && <span className="ok">Сохранено ✓</span>}
            {status.startsWith("error") && <span className="error">{status}</span>}
          </span>
        </div>

        {editable && repeated.length > 0 && (
          <p className="warn-note" role="status">
            ⚠ Один участник отмечен у нескольких рассказов:{" "}
            {repeated.map((c) => `${c} (${dup[c]})`).join(", ")}. Но у каждого участника ровно один рассказ, значит
            хотя бы одна из этих отметок ошибочна. Это только подсказка, ограничений нет.
          </p>
        )}

        {truth && (
          <p className="muted small matrix-legend">
            <span className="cell hit">✓</span> верно <span className="cell miss">✕</span> мимо{" "}
            <span className="cell truth">●</span> настоящий автор, которого вы не отметили
          </p>
        )}
      </div>

      {stories.length === 0 || candidates.length === 0 ? (
        <div className="card">
          <p>Пока недостаточно работ для угадайки.</p>
        </div>
      ) : (
        <>
          {/* Подсветка строки и столбца под курсором: одна динамическая таблица стилей вместо перерисовки клеток. */}
          <style>
            {hover.r != null ? `.matrix tr[data-row="${hover.r}"] td, .matrix th.rowh[data-r="${hover.r}"] { background: var(--hl); }` : ""}
            {hover.c != null ? `.matrix td[data-c="${hover.c}"], .matrix th.colh[data-c="${hover.c}"] { background: var(--hl); }` : ""}
          </style>
          <div
            className="matrix-wrap"
            role="region"
            aria-label="Матрица угадайки: строки — рассказы, столбцы — участники"
            tabIndex={0}
          >
            <table
              className="matrix"
              onMouseOver={onOver}
              onFocus={onOver}
              onMouseLeave={() => setHover({ r: null, c: null })}
            >
              <thead>
                <tr>
                  <th className="corner" scope="col">
                    Рассказ ↓ · участник →
                  </th>
                  {candidates.map((nick, c) => (
                    <th
                      key={nick}
                      scope="col"
                      data-c={c}
                      className={"colh" + (editable && (dup[nick] || 0) > 1 ? " warn" : "")}
                      title={nick}
                    >
                      <span>{nick}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stories.map((s, r) => {
                  const row = marks[s.anon_number] || [];
                  const pts = truth ? rowPoints(s.anon_number) : null;
                  return (
                    <tr key={s.anon_number} data-row={r}>
                      <th scope="row" className="rowh" data-r={r} title={s.title}>
                        <div className="rowh-in">
                          <span className="num">№{s.anon_number}</span>
                          <span className="t">{s.title}</span>
                          <span className="pts" title={truth ? "очки за эту строку" : "очки за верный ответ в этой строке"}>
                            {truth ? (pts == null ? "" : `+${fmt(pts)}`) : row.length > 1 ? `×${fmt(1 / row.length)}` : ""}
                          </span>
                        </div>
                      </th>
                      {candidates.map((nick, c) => {
                        const marked = row.includes(nick);
                        return (
                          <Cell
                            key={nick}
                            r={r}
                            c={c}
                            n={s.anon_number}
                            nick={nick}
                            marked={marked}
                            mode={cellMode(s.anon_number, nick, marked)}
                            onToggle={editable ? toggle : null}
                          />
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
