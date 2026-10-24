/** Что именно не выполнено: «оценил 2 из 4 работ», «раздал 1 из 3 звёзд». */
export function violationText(v) {
  const parts = [];
  if (v.ratings) parts.push(`оценил ${v.ratings.done} из ${v.ratings.required} работ`);
  if (v.stars) parts.push(`раздал ${v.stars.done} из ${v.stars.required} звёзд`);
  return parts.join(", ");
}

/** Плашка над рассказом автора, нарушившего правила оценивания. */
export default function Violation({ violation }) {
  if (!violation) return null;
  return (
    <p className="violation-banner" role="alert">
      ⚠ Автор нарушил правила конкурса: не выполнил обязательное при оценивании ({violationText(violation)}).
    </p>
  );
}
