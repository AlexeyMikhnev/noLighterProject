import { useCallback, useEffect, useState } from "react";

const KEY = "theme";
const mq = () => window.matchMedia("(prefers-color-scheme: dark)");

function stored() {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

/** Текущая тема: явный выбор пользователя, иначе системная. */
export function useTheme() {
  const [choice, setChoice] = useState(stored);
  const [system, setSystem] = useState(() => (mq().matches ? "dark" : "light"));

  useEffect(() => {
    const m = mq();
    const on = (e) => setSystem(e.matches ? "dark" : "light");
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);

  const theme = choice ?? system;

  useEffect(() => {
    if (choice) document.documentElement.dataset.theme = choice;
    else delete document.documentElement.dataset.theme;
  }, [choice]);

  const toggle = useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    setChoice(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {}
  }, [theme]);

  return { theme, toggle };
}
