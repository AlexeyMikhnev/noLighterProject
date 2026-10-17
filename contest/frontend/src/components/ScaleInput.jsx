export default function ScaleInput({ label, hint, value, onChange }) {
  return (
    <div className="scale">
      <div className="scale-head">
        <strong>{label}</strong>
        <span className="muted small">{hint}</span>
      </div>
      <div className="scale-buttons" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            className={value === n ? "on" : ""}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
