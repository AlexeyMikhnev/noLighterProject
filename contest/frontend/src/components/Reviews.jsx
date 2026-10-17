// Список анонимных рецензий: только текст, без авторов (их нет даже в ответе API).
export default function Reviews({ reviews, title = "Рецензии" }) {
  return (
    <section className="reviews">
      <h3>
        {title} <span className="muted small">({reviews.length})</span>
      </h3>
      {reviews.length === 0 ? (
        <p className="muted">Рецензий пока нет.</p>
      ) : (
        reviews.map((r, i) => (
          <blockquote key={i} className="review">
            <div className="eyebrow">Анонимный рецензент</div>
            <p>{r.body}</p>
          </blockquote>
        ))
      )}
    </section>
  );
}
