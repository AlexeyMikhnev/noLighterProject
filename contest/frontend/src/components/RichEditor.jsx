import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";

// Только то, что умеет и принимает сервер (backend/app/richtext.py): жирный, курсив, подчёркнутый,
// зачёркнутый, подзаголовок, цитата, списки, разделитель. Ссылок, картинок и стилей нет.
const extensions = [
  StarterKit.configure({
    heading: { levels: [2] },
    code: false,
    codeBlock: false,
  }),
  Underline,
];

/** Число знаков видимого текста (абзацы разделены одним переводом строки) — как считает сервер. */
export function textLength(editor) {
  const doc = editor.state.doc;
  return doc.textBetween(0, doc.content.size, "\n", "").length;
}

function stats(editor) {
  const words = editor.getText().split(/\s+/).filter(Boolean).length;
  return [editor.getHTML(), textLength(editor), words];
}

function Btn({ editor, label, title, active, run, disabled }) {
  return (
    <button
      type="button"
      className={active ? "on" : ""}
      title={title}
      aria-label={title}
      aria-pressed={Boolean(active)}
      disabled={disabled}
      // mousedown, а не click: иначе кнопка забирает фокус и выделение в тексте теряется
      onMouseDown={(e) => {
        e.preventDefault();
        run(editor.chain().focus()).run();
      }}
      // с клавиатуры (Enter/Space) приходит только click, у него detail === 0
      onClick={(e) => {
        if (e.detail === 0) run(editor.chain().focus()).run();
      }}
    >
      {label}
    </button>
  );
}

/**
 * Редактор рассказа. Значение живёт внутри редактора; наружу отдаётся HTML.
 *  - onReady(html, length, words) — один раз при создании (HTML в том виде, как его нормализовал редактор);
  - onChange(html, length, words) — при каждой правке пользователя.
 */
export default function RichEditor({ initialHtml, onReady, onChange }) {
  const editor = useEditor({
    extensions,
    content: initialHtml || "",
    editorProps: {
      attributes: { class: "rte-content story-body", "aria-label": "Текст рассказа" },
    },
    onCreate: ({ editor }) => onReady?.(...stats(editor)),
    onUpdate: ({ editor }) => onChange?.(...stats(editor)),
  });

  if (!editor) return null;
  const b = (label, title, mark, run) => (
    <Btn editor={editor} label={label} title={title} active={editor.isActive(mark)} run={run} />
  );

  return (
    <div className="rte">
      <div className="rte-toolbar" role="toolbar" aria-label="Форматирование">
        {b(<b>Ж</b>, "Жирный (Ctrl+B)", "bold", (c) => c.toggleBold())}
        {b(<i>К</i>, "Курсив (Ctrl+I)", "italic", (c) => c.toggleItalic())}
        {b(<u>Ч</u>, "Подчёркнутый (Ctrl+U)", "underline", (c) => c.toggleUnderline())}
        {b(<s>З</s>, "Зачёркнутый", "strike", (c) => c.toggleStrike())}
        <span className="sep" />
        {b("Заголовок", "Подзаголовок", "heading", (c) => c.toggleHeading({ level: 2 }))}
        {b("❝", "Цитата", "blockquote", (c) => c.toggleBlockquote())}
        {b("• Список", "Маркированный список", "bulletList", (c) => c.toggleBulletList())}
        {b("1. Список", "Нумерованный список", "orderedList", (c) => c.toggleOrderedList())}
        <Btn editor={editor} label="* * *" title="Разделитель сцен" run={(c) => c.setHorizontalRule()} />
        <span className="sep" />
        <Btn editor={editor} label="↶" title="Отменить (Ctrl+Z)" run={(c) => c.undo()} disabled={!editor.can().undo()} />
        <Btn editor={editor} label="↷" title="Повторить (Ctrl+Shift+Z)" run={(c) => c.redo()} disabled={!editor.can().redo()} />
      </div>
      <EditorContent editor={editor} />
    </div>
  );
}
