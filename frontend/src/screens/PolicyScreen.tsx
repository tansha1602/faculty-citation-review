import { useState } from "react";
import { api } from "../api";
import { Msg, useAsync } from "../components";
import { fmtDate } from "../labels";
import type { Policy } from "../types";
import type { ScreenProps } from "./CaseWorkspace";
import PolicyForm from "./PolicyForm";

export default function PolicyScreen({ c, user, goto }: ScreenProps) {
  const { data, error, setData } = useAsync(() => api.get<Policy>(`/api/cases/${c.id}/policy`), [c.id]);
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  if (error) return <Msg error={error} />;
  if (!data) return <p className="muted">טוען…</p>;
  return (
    <div className="card">
      <h2>מסך 3 — מדיניות התיק</h2>
      <p className="small muted">
        עודכן לאחרונה: {fmtDate(data.updated_at)} · {data.updated_by}. המדיניות מועתקת מברירת המחדל המוסדית בעת פתיחת התיק.
      </p>
      <PolicyForm
        key={data.updated_at}
        policy={data}
        canEdit={user.role === "admin"}
        onSave={async (v) => {
          try {
            setData(await api.put<Policy>(`/api/cases/${c.id}/policy`, v));
            setMsg({ ok: "המדיניות נשמרה ונרשמה ביומן השינויים." });
          } catch (e) {
            setMsg({ err: (e as Error).message });
          }
        }}
      />
      <Msg ok={msg.ok} error={msg.err} />
      <button className="btn" onClick={() => goto(3)}>
        המשך לטבלת הפרסומים ←
      </button>
    </div>
  );
}
