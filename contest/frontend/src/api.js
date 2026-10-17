const TOKEN_KEY = "contest_token";

// localStorage может быть недоступен (приватный режим), поэтому всё в try/catch.
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

function errorText(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return fallback;
}

export async function api(path, { method = "GET", body } = {}) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch("/api" + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* тело не JSON */
  }
  if (!res.ok) {
    if (res.status === 401 && token) window.dispatchEvent(new Event("auth:expired"));
    const err = new Error(errorText(data?.detail, res.statusText));
    err.status = res.status;
    throw err;
  }
  return data;
}

// ISO (UTC) -> значение для <input type="datetime-local">
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// значение <input type="datetime-local"> -> ISO (UTC) или null
export function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : null;
}

export function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" }) : "";
}

export function countWords(text) {
  const t = text.trim();
  return t ? t.split(/\s+/).length : 0;
}
