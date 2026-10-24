import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function Register() {
  const { token } = useParams();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [valid, setValid] = useState(null); // null = проверяем
  const [form, setForm] = useState({ email: "", nickname: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/auth/invite/${token}`)
      .then((r) => setValid(r.valid))
      .catch(() => setValid(false));
  }, [token]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register({ invite_token: token, ...form });
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (valid === null) return <p className="center">Проверяем приглашение…</p>;
  if (!valid)
    return (
      <div className="card narrow">
        <h1>Приглашение недействительно</h1>
        <p>Ссылка уже использована, истекла или введена неверно. Попросите организатора выдать новую.</p>
        <Link to="/login">Войти</Link>
      </div>
    );

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>Регистрация</h1>
      <p className="muted small">
        Регистрируясь, вы соглашаетесь с <Link to="/rules">правилами конкурса</Link>.
      </p>
      <p className="muted">
        Псевдоним будет скрыт от других участников до публикации результатов.
      </p>
      <label>
        Email
        <input type="email" value={form.email} onChange={set("email")} required autoFocus />
      </label>
      <label>
        Псевдоним
        <input value={form.nickname} onChange={set("nickname")} minLength={2} maxLength={32} required />
      </label>
      <label>
        Пароль (от 8 символов)
        <input type="password" value={form.password} onChange={set("password")} minLength={8} required />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy}>
        Зарегистрироваться
      </button>
    </form>
  );
}
