import { useState } from "react";
import { api } from "../api";
import { Badge, En, Field, Msg, useAsync } from "../components";
import { ROLE_LABEL, fmtDate } from "../labels";
import type { Policy, ProvidersInfo, User } from "../types";
import PolicyForm from "./PolicyForm";

interface AuditRow { id: number; ts: string; username: string; case_id: number | null; entity: string; action: string; details: unknown }

export default function AdminScreen({ user }: { user: User }) {
  const users = useAsync(() => api.get<User[]>("/api/users"), []);
  const policy = useAsync(() => api.get<Policy>("/api/policy/default"), []);
  const prov = useAsync(() => api.get<ProvidersInfo>("/api/providers"), []);
  const audit = useAsync(() => api.get<AuditRow[]>("/api/audit?limit=200"), []);
  const [nu, setNu] = useState({ username: "", display_name: "", role: "librarian", password: "" });
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg({});
    try {
      await fn();
      setMsg({ ok });
      users.reload();
      audit.reload();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    }
  };

  return (
    <div>
      <h1>ניהול מערכת</h1>
      <Msg ok={msg.ok} error={msg.err} />
      <div className="two-col">
        <div className="card">
          <h2>משתמשים והרשאות</h2>
          <table className="table">
            <thead><tr><th>משתמש</th><th>תפקיד</th><th>פעיל</th><th></th></tr></thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td><En>{u.username}</En> <span className="small muted">{u.display_name}</span></td>
                  <td>
                    <select value={u.role} disabled={u.id === user.id}
                      onChange={(e) => run(() => api.patch(`/api/users/${u.id}`, { role: e.target.value }), "התפקיד עודכן")}>
                      {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  </td>
                  <td>{u.active ? <Badge kind="ok">פעיל</Badge> : <Badge kind="muted">מושבת</Badge>}</td>
                  <td>
                    {u.id !== user.id && (
                      <button className="btn small-btn" onClick={() => run(() => api.patch(`/api/users/${u.id}`, { active: !u.active }), "עודכן")}>
                        {u.active ? "השבתה" : "הפעלה"}
                      </button>
                    )}{" "}
                    <button className="btn small-btn ghost" onClick={() => {
                      const p = prompt("סיסמה חדשה (לפחות 8 תווים):");
                      if (p) run(() => api.patch(`/api/users/${u.id}`, { password: p }), "הסיסמה עודכנה");
                    }}>איפוס סיסמה</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>הוספת משתמש</h3>
          <div className="grid-form">
            <Field label="שם משתמש"><input dir="ltr" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} /></Field>
            <Field label="שם לתצוגה"><input value={nu.display_name} onChange={(e) => setNu({ ...nu, display_name: e.target.value })} /></Field>
            <Field label="תפקיד">
              <select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>
                {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <Field label="סיסמה ראשונית"><input dir="ltr" type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} /></Field>
          </div>
          <button className="btn primary" onClick={() => run(async () => {
            await api.post("/api/users", nu);
            setNu({ username: "", display_name: "", role: "librarian", password: "" });
          }, "המשתמש נוצר")}>יצירה</button>
          <p className="hint">עובד/ת ספרייה: הכנת תיקים · בודק/ת: אישור שני ושינוי סיווג · מנהל: מדיניות, משתמשים וגיבוי.</p>
        </div>
        <div className="card">
          <h2>חיבור למאגרים</h2>
          {prov.data && (
            <>
              <div className="provider-chips">
                <Badge kind={prov.data.scopus.configured ? "ok" : "warn"}>Scopus: {prov.data.scopus.configured ? "מוגדר" : "לא מוגדר"}</Badge>
                <Badge kind={prov.data.wos.configured ? "ok" : "warn"}>WoS Starter: {prov.data.wos.configured ? "מוגדר" : "לא מוגדר"}</Badge>
                <Badge kind={prov.data.wos.citing_api ? "ok" : "idle"}>WoS Expanded: {prov.data.wos.citing_api ? "מוגדר" : "לא מוגדר"}</Badge>
              </div>
              <ul className="small">
                {[...prov.data.scopus.requirements, ...prov.data.wos.requirements].map((r) => <li key={r}>{r}</li>)}
              </ul>
              <p className="small">המפתחות מוגדרים כמשתני סביבה בקובץ <En>.env</En> במחשב השרת (ראו README) ואינם נשמרים בקוד, בבסיס הנתונים או בדוחות.</p>
            </>
          )}
          <h2>גיבוי</h2>
          <p className="small muted">יוצר קובץ ZIP בתיקיית data/backups עם בסיס הנתונים, הקבצים שהועלו והדוחות (נשמרים 30 האחרונים).</p>
          <button className="btn" onClick={() => run(() => api.post("/api/admin/backup"), "הגיבוי נוצר")}>יצירת גיבוי עכשיו</button>
        </div>
      </div>
      <div className="card">
        <h2>מדיניות ברירת מחדל מוסדית</h2>
        <p className="small muted">חלה על תיקים חדשים. תיקים קיימים שומרים על המדיניות שלהם.</p>
        {policy.data && (
          <PolicyForm key={policy.data.updated_at} policy={policy.data} canEdit
            onSave={async (v) => run(async () => policy.setData(await api.put<Policy>("/api/policy/default", v)), "מדיניות ברירת המחדל נשמרה")} />
        )}
      </div>
      <div className="card">
        <h2>יומן שינויים (200 אחרונים)</h2>
        <div className="table-wrap">
          <table className="table small">
            <thead><tr><th>זמן</th><th>משתמש</th><th>תיק</th><th>ישות</th><th>פעולה</th><th>פרטים</th></tr></thead>
            <tbody>
              {audit.data?.map((a) => (
                <tr key={a.id}>
                  <td>{fmtDate(a.ts)}</td><td>{a.username}</td><td>{a.case_id ?? ""}</td><td>{a.entity}</td><td>{a.action}</td>
                  <td><En><span className="mono">{JSON.stringify(a.details).slice(0, 160)}</span></En></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
