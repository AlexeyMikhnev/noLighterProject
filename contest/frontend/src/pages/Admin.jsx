import { useCallback, useEffect, useState } from "react";
import { api, formatDate, fromLocalInput, toLocalInput } from "../api";
import PhaseSteps, { PHASE_LABELS } from "../components/PhaseSteps.jsx";

const NEXT_LABEL = {
  draft: "Начать приём работ",
  submission: "Закрыть приём и начать оценивание",
  voting: "Закрыть оценивание и показать результаты",
};

function CreateContest({ onDone }) {
  const [theme, setTheme] = useState("");
  const [sub, setSub] = useState("");
  const [vote, setVote] = useState("");
  const [mustSubmit, setMustSubmit] = useState(true);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api("/admin/contest", {
        method: "POST",
        body: {
          theme,
          submission_ends_at: fromLocalInput(sub),
          voting_ends_at: fromLocalInput(vote),
          voters_must_submit: mustSubmit,
        },
      });
      onDone();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h2>Новый конкурс</h2>
      <label>
        Тема
        <input value={theme} onChange={(e) => setTheme(e.target.value)} maxLength={300} required />
      </label>
      <div className="grid2">
        <label>
          Конец приёма работ (необязательно)
          <input type="datetime-local" value={sub} onChange={(e) => setSub(e.target.value)} />
        </label>
        <label>
          Конец оценивания (необязательно)
          <input type="datetime-local" value={vote} onChange={(e) => setVote(e.target.value)} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={mustSubmit} onChange={(e) => setMustSubmit(e.target.checked)} />
        Оценивать могут только те, кто сам прислал рассказ
      </label>
      <p className="muted small">
        Без дедлайна фазу завершает организатор вручную. С дедлайном она переключится сама.
      </p>
      {error && <p className="error">{error}</p>}
      <button className="primary">Создать (в черновике)</button>
    </form>
  );
}

function ContestPanel({ contest, stats, onChange }) {
  const [sub, setSub] = useState(toLocalInput(contest.submission_ends_at));
  const [vote, setVote] = useState(toLocalInput(contest.voting_ends_at));
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const next = NEXT_LABEL[contest.phase];

  const advance = async () => {
    let warn = `${next}? Вернуться назад будет нельзя.`;
    if (contest.phase === "submission") warn += ` Сейчас работ: ${stats?.stories ?? 0}. После закрытия приёма авторы не смогут править тексты.`;
    if (contest.phase === "voting") warn += " Авторы работ станут видны всем.";
    if (!window.confirm(warn)) return;
    try {
      await api("/admin/contest/advance", { method: "POST" });
      onChange();
    } catch (e) {
      setError(e.message);
    }
  };

  const saveDeadlines = async () => {
    setError("");
    setMsg("");
    const body = {};
    if (["draft", "submission"].includes(contest.phase)) body.submission_ends_at = fromLocalInput(sub);
    if (contest.phase !== "results") body.voting_ends_at = fromLocalInput(vote);
    try {
      await api("/admin/contest", { method: "PATCH", body });
      setMsg("Дедлайны сохранены");
      onChange();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="card">
      <h2>Текущий конкурс</h2>
      <PhaseSteps phases={contest.phases} current={contest.phase} />
      <p>
        Тема: <strong>{contest.theme}</strong> · фаза: {PHASE_LABELS[contest.phase]}
      </p>
      <p className="muted small">
        Правило голосования:{" "}
        {contest.voters_must_submit ? "оценивать могут только авторы работ" : "оценивать может любой участник"}
      </p>

      {contest.phase !== "results" && (
        <div className="grid2">
          {["draft", "submission"].includes(contest.phase) && (
            <label>
              Конец приёма работ
              <input type="datetime-local" value={sub} onChange={(e) => setSub(e.target.value)} />
            </label>
          )}
          <label>
            Конец оценивания
            <input type="datetime-local" value={vote} onChange={(e) => setVote(e.target.value)} />
          </label>
        </div>
      )}
      <div className="row">
        {contest.phase !== "results" && (
          <button onClick={saveDeadlines}>Сохранить дедлайны</button>
        )}
        {next && (
          <button className="primary" onClick={advance}>
            {next}
          </button>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p className="note">{msg}</p>}
    </div>
  );
}

function Invites() {
  const [list, setList] = useState([]);
  const [count, setCount] = useState(1);
  const [days, setDays] = useState("");
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api("/admin/invites").then(setList).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const link = (t) => `${window.location.origin}/register/${t}`;

  const create = async () => {
    setError("");
    try {
      await api("/admin/invites", {
        method: "POST",
        body: { count: Number(count), expires_in_days: days ? Number(days) : null },
      });
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const copy = async (t) => {
    try {
      await navigator.clipboard.writeText(link(t));
      setCopied(t);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      window.prompt("Скопируйте ссылку:", link(t));
    }
  };

  const remove = async (t) => {
    try {
      await api(`/admin/invites/${t}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="card">
      <h2>Приглашения</h2>
      <p className="muted small">Каждая ссылка одноразовая: по ней регистрируется один участник.</p>
      <div className="row">
        <label className="inline">
          Сколько
          <input type="number" min="1" max="50" value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className="inline">
          Срок действия, дней
          <input type="number" min="1" max="365" placeholder="без срока" value={days} onChange={(e) => setDays(e.target.value)} />
        </label>
        <button className="primary" onClick={create}>
          Создать ссылки
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <table className="ranking invites">
        <tbody>
          {list.map((i) => (
            <tr key={i.token}>
              <td className="mono">{i.token.slice(0, 8)}…</td>
              <td>
                {i.used ? (
                  <span className="ok">использована: {i.used_by}</span>
                ) : (
                  <span className="muted">
                    свободна{i.expires_at ? ` до ${formatDate(i.expires_at)}` : ""}
                  </span>
                )}
              </td>
              <td className="actions">
                {!i.used && (
                  <>
                    <button onClick={() => copy(i.token)}>{copied === i.token ? "Скопировано" : "Копировать ссылку"}</button>
                    <button className="danger" onClick={() => remove(i.token)}>
                      ×
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {list.length === 0 && (
            <tr>
              <td className="muted">Приглашений пока нет.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function Admin() {
  const [contest, setContest] = useState(undefined);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api("/contest/current"), api("/admin/stats")]);
      setContest(c);
      setStats(s);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  if (error) return <p className="error">{error}</p>;
  if (contest === undefined) return <p className="center">Загрузка…</p>;

  return (
    <>
      <h1>Кабинет организатора</h1>
      {stats && (
        <div className="stats">
          <div><b>{stats.participants}</b><span>участников</span></div>
          <div><b>{stats.stories}</b><span>рассказов</span></div>
          <div><b>{stats.ratings}</b><span>оценок</span></div>
          <div><b>{stats.stars}</b><span>звёзд</span></div>
          <div><b>{stats.invites_used}/{stats.invites_total}</b><span>приглашений использовано</span></div>
        </div>
      )}
      {(!contest || contest.phase === "results") && <CreateContest onDone={load} />}
      {contest && <ContestPanel contest={contest} stats={stats} onChange={load} />}
      <Invites />
    </>
  );
}
