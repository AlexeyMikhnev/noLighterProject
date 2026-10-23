/** Пустые ответы опросника (то же, что «не ответил»). */
export const emptySurvey = { genres: [], settings: [], hero_gender: null, about_children: null, about_animals: null, someone_died: null, has_guns: null };

/** Канонический вид ответов: для сравнения с сохранённым и для отправки. */
export function normSurvey(questions, v = {}) {
  const out = {};
  for (const q of questions) {
    if (q.type === "multi") out[q.key] = [...(v[q.key] ?? [])].sort();
    else out[q.key] = v[q.key] ?? null;
  }
  return out;
}

const BOOL = [
  { key: true, label: "Да" },
  { key: false, label: "Нет" },
];

function Chips({ options, isOn, onPick, label }) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.key)} type="button" className={isOn(o.key) ? "on" : ""} aria-pressed={isOn(o.key)} onClick={() => onPick(o.key)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Опросник для статистики. Все вопросы необязательны; повторное нажатие снимает выбор. */
export default function SurveyForm({ questions, value, onChange }) {
  const set = (key, v) => onChange({ ...value, [key]: v });
  return (
    <div className="survey">
      {questions.map((q) => (
        <div className="survey-q" key={q.key}>
          <strong>{q.label}</strong>
          {q.type === "multi" && (
            <Chips
              label={q.label}
              options={q.options}
              isOn={(k) => (value[q.key] ?? []).includes(k)}
              onPick={(k) => {
                const cur = value[q.key] ?? [];
                set(q.key, cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]);
              }}
            />
          )}
          {q.type === "single" && (
            <Chips
              label={q.label}
              options={q.options}
              isOn={(k) => value[q.key] === k}
              onPick={(k) => set(q.key, value[q.key] === k ? null : k)}
            />
          )}
          {q.type === "bool" && (
            <Chips
              label={q.label}
              options={BOOL}
              isOn={(k) => value[q.key] === k}
              onPick={(k) => set(q.key, value[q.key] === k ? null : k)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
