import { useState } from "react";
import { api } from "../api";
import { Badge, Field, Msg, useAsync } from "../components";
import { PROVIDER_LABEL, fmtDate } from "../labels";
import type { QAResult } from "../types";
import type { ScreenProps } from "./CaseWorkspace";

const LEVEL = { error: { label: "שגיאה", kind: "error" }, warning: { label: "אזהרה", kind: "warn" }, info: { label: "מידע", kind: "info" } };

export default function QAScreen({ c, user, reloadCase, goto }: ScreenProps) {
  const qa = useAsync(() => api.get<QAResult>(`/api/cases/${c.id}/qa`), [c.id, c.prepared_at, c.reviewed_at]);
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  const [level, setLevel] = useState<"all" | "error" | "warning" | "info">("all");

  if (qa.error) return <Msg error={qa.error} />;
  if (!qa.data) return <p className="muted">מריץ בדיקות…</p>;
  const d = qa.data;
  const issues = d.issues.filter((i) => level === "all" || i.level === level);
  const STAT: Record<string, string> = {
    publications: "פרסומים בקו״ח", included: "נכללים", excluded: "מוחרגים", complete_cells: "תאים שהושלמו",
    partial_cells: "תאים חלקיים", not_checked: "לא נבדקו", needs_verification: "דורשים אימות", not_indexed: "לא מאונדקסים",
  };

  async function act(path: string) {
    setMsg({});
    try {
      await api.post(`/api/cases/${c.id}/${path}`, { note, acknowledge_warnings: ack });
      setMsg({ ok: path === "prepare" ? "התיק סומן כמוכן ומועבר לבודק/ת." : "התיק אושר." });
      reloadCase();
      qa.reload();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    }
  }

  return (
    <div>
      <div className="stats">
        {Object.entries(STAT).map(([k, l]) => (
          <div key={k} className="stat">
            <div className="stat-n">{d.stats[k] ?? 0}</div>
            <div className="small muted">{l}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="toolbar">
          <h2>
            מסך 6 — בקרת איכות{" "}
            {d.ready ? <Badge kind="ok">אין שגיאות חוסמות</Badge> : <Badge kind="error">{d.errors} שגיאות</Badge>}{" "}
            {d.warnings > 0 && <Badge kind="warn">{d.warnings} אזהרות</Badge>}
          </h2>
          <div className="seg">
            {(["all", "error", "warning", "info"] as const).map((l) => (
              <button key={l} className={level === l ? "on" : ""} onClick={() => setLevel(l)}>
                {l === "all" ? "הכול" : LEVEL[l].label}
              </button>
            ))}
          </div>
        </div>
        <ul className="issues">
          {issues.map((i, n) => (
            <li key={n} className={`issue issue-${i.level}`}>
              <Badge kind={LEVEL[i.level].kind}>{LEVEL[i.level].label}</Badge> {i.message}
              {i.provider && <span className="muted small"> · {PROVIDER_LABEL[i.provider]}</span>}
              {i.publication_id && (
                <button className="link small" onClick={() => goto(i.provider ? 3 : 1, i.publication_id!)}>
                  מעבר לתיקון
                </button>
              )}
            </li>
          ))}
          {issues.length === 0 && <li className="muted">אין פריטים.</li>}
        </ul>
      </div>
      <div className="card">
        <h2>אישורים</h2>
        <p className="small muted">לפי הנוהל: העובד/ת המכין/ה מסמן/ת שהתיק מוכן, ועובד/ת נוסף/ת (בודק/ת) מאשר/ת את המקרים החריגים ואת הדוח.</p>
        <div className="kv">
          <div>הוכן על ידי</div>
          <div>{c.prepared_by ? `${c.prepared_by} · ${fmtDate(c.prepared_at)}` : "—"}</div>
          <div>אושר על ידי</div>
          <div>{c.reviewed_by ? `${c.reviewed_by} · ${fmtDate(c.reviewed_at)}` : "—"}</div>
          {c.review_note && (<><div>הערת בודק</div><div>{c.review_note}</div></>)}
        </div>
        <Field label="הערה">
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {d.warnings > 0 && (
          <label className="check">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            בדקתי את כל האזהרות ({d.warnings}) ואני מאשר/ת אותן
          </label>
        )}
        <div className="actions">
          {user.role !== "reviewer" && (
            <button className="btn primary" disabled={!d.ready} onClick={() => act("prepare")}>
              סימון "התיק הוכן"
            </button>
          )}
          {(user.role === "reviewer" || user.role === "admin") && (
            <button className="btn primary" disabled={!d.ready || !c.prepared_by || c.prepared_by === user.username}
              title={c.prepared_by === user.username ? "האישור חייב להינתן על ידי עובד אחר" : ""} onClick={() => act("review")}>
              אישור בודק/ת שני/ה
            </button>
          )}
        </div>
        <Msg ok={msg.ok} error={msg.err} />
      </div>
    </div>
  );
}
