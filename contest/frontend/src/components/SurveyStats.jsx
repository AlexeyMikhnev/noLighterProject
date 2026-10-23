/** Итоги опросника: сколько читателей выбрали каждый вариант (доля от ответивших на вопрос). */
export default function SurveyStats({ stats, title = "Опросник читателей" }) {
  if (!stats || stats.respondents === 0) return null;
  return (
    <details className="survey-stats" open>
      <summary>
        <strong>{title}</strong> <span className="muted small">· ответили: {stats.respondents}</span>
      </summary>
      {stats.questions
        .filter((q) => q.answered > 0)
        .map((q) => (
          <div key={q.key} className="stat-q">
            <div className="stat-title">
              {q.label} <span className="muted small">({q.answered})</span>
            </div>
            {q.options.map((o) => {
              const pct = Math.round((o.count / q.answered) * 100);
              return (
                <div key={o.key} className="stat-row">
                  <span className="stat-label">{o.label}</span>
                  <span className="stat-bar" aria-hidden="true">
                    <span style={{ width: `${pct}%` }} />
                  </span>
                  <span className="stat-val">
                    {pct}% <span className="muted small">({o.count})</span>
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      <p className="muted small">Опросник заполняют читатели по желанию, на оценки и топы он не влияет.</p>
    </details>
  );
}
