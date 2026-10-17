import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Home from "./pages/Home.jsx";
import Admin from "./pages/Admin.jsx";
import Profile from "./pages/Profile.jsx";

function Header() {
  const { user, logout } = useAuth();
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        ✒ Писательский конкурс
      </Link>
      {user && (
        <nav>
          {user.role === "organizer" ? (
            <Link to="/admin">Кабинет организатора</Link>
          ) : (
            <Link to="/profile">Личный кабинет</Link>
          )}
          <span className="muted">{user.nickname}</span>
          <button className="link" onClick={logout}>
            Выйти
          </button>
        </nav>
      )}
    </header>
  );
}

function Private({ children, organizer = false }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="center">Загрузка…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (organizer && user.role !== "organizer") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <>
      <Header />
      <main className="page">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register/:token" element={<Register />} />
          <Route path="/" element={<Private><Home /></Private>} />
          <Route path="/profile" element={<Private><Profile /></Private>} />
          <Route path="/admin" element={<Private organizer><Admin /></Private>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
