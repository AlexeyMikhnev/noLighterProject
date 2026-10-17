export const PHASE_LABELS = {
  draft: "Подготовка",
  submission: "Приём работ",
  voting: "Оценивание",
  results: "Результаты",
};

export default function PhaseSteps({ phases, current }) {
  const idx = phases.indexOf(current);
  return (
    <ol className="steps">
      {phases.map((p, i) => (
        <li key={p} className={i < idx ? "done" : i === idx ? "active" : ""}>
          {PHASE_LABELS[p]}
        </li>
      ))}
    </ol>
  );
}
