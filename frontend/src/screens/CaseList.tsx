import { useState } from "react";
import { api } from "../api";
import { En, Msg, useAsync } from "../components";
import { fmtDate } from "../labels";
import type { Case, User } from "../types";
import CaseForm, { emptyCase } from "./CaseForm";

export default function CaseList({ user, onOpen }: { user: User; onOpen: (c: Case) => void }) {
  const { data, error, loading } = useAsync(() => api.get<Case[]>("/api/cases"), []);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canEdit = user.role !== "reviewer";

  return (
    <div>
      <div className="page-head">
        <h1>תיקי חוקרים</h1>
        {canEdit && !creating && (
          <button className="btn primary" onClick={() => setCreating(true)}>
            + פתיחת תיק חדש
          </button>
        )}
      </div>
      {creating && (
        <div className="card">
          <h2>מסך 1 — פתיחת תיק חוקר</h2>
          <CaseForm
            initial={emptyCase}
            submitLabel="פתיחת התיק"
            onCancel={() => setCreating(false)}
            onSubmit={async (v) => {
              try {
                const c = await api.post<Case>("/api/cases", v);
                onOpen(c);
              } catch (e) {
                setErr((e as Error).message);
              }
            }}
          />
          <Msg error={err} />
        </div>
      )}
      <Msg error={error} />
      {loading ? (
        <p className="muted">טוען…</p>
      ) : data && data.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>חוקר/ת</th>
              <th>פרסומים</th>
              <th>קורות חיים</th>
              <th>נוצר</th>
              <th>סטטוס</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.id}>
                <td>
                  <En>{c.researcher_name_en}</En>
                  {c.researcher_name_he && <div className="small muted">{c.researcher_name_he}</div>}
                </td>
                <td>{c.publication_count}</td>
                <td className="small">{c.cv_filename ? <En>{c.cv_filename}</En> : <span className="muted">לא הועלו</span>}</td>
                <td className="small">
                  {fmtDate(c.created_at)} · {c.created_by}
                </td>
                <td>
                  {c.reviewed_by ? (
                    <span className="badge badge-ok">אושר ({c.reviewed_by})</span>
                  ) : c.prepared_by ? (
                    <span className="badge badge-warn">ממתין לאישור בודק</span>
                  ) : (
                    <span className="badge badge-idle">בעבודה</span>
                  )}
                </td>
                <td>
                  <button className="btn" onClick={() => onOpen(c)}>
                    פתיחה
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">אין עדיין תיקים.</p>
      )}
    </div>
  );
}
