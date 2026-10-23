/**
 * Текст рассказа для чтения. Сервер отдаёт HTML, уже очищенный по белому списку тегов
 * (backend/app/richtext.py), поэтому его можно вставлять как есть. Старые рассказы,
 * сохранённые обычным текстом (без тегов), показываем с сохранением переносов.
 */
export default function StoryBody({ html }) {
  if (!html) return null;
  if (!html.includes("<")) return <article className="story-body plain">{html}</article>;
  return <article className="story-body" dangerouslySetInnerHTML={{ __html: html }} />;
}
