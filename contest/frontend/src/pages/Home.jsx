import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";
import PhaseSteps from "../components/PhaseSteps.jsx";
import Submission from "./Submission.jsx";
import Voting from "./Voting.jsx";
import Results from "./Results.jsx";

export default function Home() {
  const { user } = useAuth();
  const [contest, setContest] = useState(undefined); // undefined = грузится, null = конкурса нет
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setContest(await api("/contest/current"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  // Фаза может смениться по дедлайну, поэтому периодически перечитываем.
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (error) return <p className="error">{error}</p>;
  if (contest === undefined) return <p className="center">Загрузка…</p>;

  if (contest === null)
    return (
      <div className="card">
        <h1>Конкурса пока нет</h1>
        {user.role === "organizer" ? (
          <p>
            Создайте его в <Link to="/admin">кабинете организатора</Link>.
          </p>
        ) : (
          <p>Организатор ещё не создал конкурс. Загляните позже.</p>
        )}
      </div>
    );

  const isOrganizer = user.role === "organizer";

  return (
    <>
      <div className="hero">
        <PhaseSteps phases={contest.phases} current={contest.phase} />
        {contest.theme && (
          <>
            <div className="eyebrow">Тема конкурса</div>
            <h1 className="theme">{contest.theme}</h1>
          </>
        )}
      </div>

      {contest.phase === "draft" && (
        <div className="card">
          <p>
            {isOrganizer
              ? "Конкурс в подготовке. Запустите приём работ в кабинете организатора."
              : "Конкурс ещё не начался. Тема будет объявлена на старте приёма работ."}
          </p>
        </div>
      )}

      {contest.phase === "submission" &&
        (isOrganizer ? (
          <div className="card">
            <p>Идёт приём работ. Организатор в конкурсе не участвует.</p>
          </div>
        ) : (
          <Submission contest={contest} reload={load} />
        ))}

      {contest.phase === "voting" &&
        (isOrganizer ? (
          <div className="card">
            <p>Идёт оценивание. Авторов работ организатор тоже увидит только в финале.</p>
          </div>
        ) : (
          <Voting contest={contest} reload={load} />
        ))}

      {contest.phase === "results" && <Results contest={contest} />}
    </>
  );
}
