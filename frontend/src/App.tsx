import { useEffect, useState } from "react";
import { api, hasToken, setToken, setUnauthorizedHandler } from "./api";
import { Field, Msg } from "./components";
import { ROLE_LABEL } from "./labels";
import type { Case, User } from "./types";
import CaseList from "./screens/CaseList";
import CaseWorkspace from "./screens/CaseWorkspace";
import AdminScreen from "./screens/AdminScreen";

type View = { name: "cases" } | { name: "case"; id: number } | { name: "admin" };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [view, setView] = useState<View>({ name: "cases" });

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      setUser(null);
    });
    (async () => {
      try {
        const s = await api.get<{ needs_setup: boolean }>("/api/setup/status");
        setNeedsSetup(s.needs_setup);
        if (hasToken()) setUser(await api.get<User>("/api/me"));
      } catch {
        setUser(null);
      } finally {
        setChecking(false);
      }
    })();
  }, []);

  if (checking) return <div className="center muted">טוען…</div>;
  if (!user)
    return (
      <Login
        setup={needsSetup}
        onLogin={(u) => {
          setNeedsSetup(false);
          setUser(u);
        }}
      />
    );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => setView({ name: "cases" })} role="button" tabIndex={0}>
          <span className="brand-title">בדיקת ציטוטים לתיקי קידום</span>
          <span className="brand-sub">ספריית הפקולטה לארכיטקטורה ובינוי ערים</span>
        </div>
        <nav className="topnav">
          <button className={view.name !== "admin" ? "link active" : "link"} onClick={() => setView({ name: "cases" })}>
            תיקי חוקרים
          </button>
          {user.role === "admin" && (
            <button className={view.name === "admin" ? "link active" : "link"} onClick={() => setView({ name: "admin" })}>
              ניהול
            </button>
          )}
          <span className="user-chip">
            {user.display_name} · {ROLE_LABEL[user.role]}
          </span>
          <button
            className="link"
            onClick={async () => {
              await api.post("/api/logout").catch(() => {});
              setToken(null);
              setUser(null);
            }}
          >
            יציאה
          </button>
        </nav>
      </header>
      <main className="content">
        {view.name === "cases" && <CaseList user={user} onOpen={(c: Case) => setView({ name: "case", id: c.id })} />}
        {view.name === "case" && <CaseWorkspace caseId={view.id} user={user} onBack={() => setView({ name: "cases" })} />}
        {view.name === "admin" && user.role === "admin" && <AdminScreen user={user} />}
      </main>
      <footer className="footer muted small">
        הנתונים נשמרים מקומית בלבד. קורות החיים אינם נשלחים לשירותי AI חיצוניים. Google Scholar — הזנה ידנית בלבד, ללא scraping.
      </footer>
    </div>
  );
}

function Login({ setup, onLogin }: { setup: boolean; onLogin: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = setup
        ? await api.post<{ token: string; user: User }>("/api/setup", { username, password, display_name: displayName })
        : await api.post<{ token: string; user: User }>("/api/login", { username, password });
      setToken(r.token);
      onLogin(r.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1>בדיקת ציטוטים לתיקי קידום</h1>
        <p className="muted">ספריית הפקולטה לארכיטקטורה ובינוי ערים</p>
        {setup && <div className="msg msg-info">הפעלה ראשונה: צרו משתמש מנהל מערכת.</div>}
        <Field label="שם משתמש">
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required dir="ltr" />
        </Field>
        {setup && (
          <Field label="שם לתצוגה">
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
        )}
        <Field label="סיסמה" hint={setup ? "לפחות 8 תווים" : undefined}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={setup ? "new-password" : "current-password"}
            required
            minLength={setup ? 8 : undefined}
            dir="ltr"
          />
        </Field>
        <Msg error={error} />
        <button className="btn primary" disabled={busy}>
          {setup ? "יצירת מנהל והתחברות" : "התחברות"}
        </button>
      </form>
    </div>
  );
}
