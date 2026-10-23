export default function Disclaimer({ text }) {
  if (!text) return null;
  return (
    <aside className="disclaimer">
      <strong>Дисклеймер автора</strong>
      <p>{text}</p>
    </aside>
  );
}
