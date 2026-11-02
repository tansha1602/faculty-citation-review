import { useState } from "react";
import { api } from "../api";
import { Badge, En, Msg, useAsync } from "../components";
import { fmtDate } from "../labels";
import type { Case } from "../types";
import type { ScreenProps } from "./CaseWorkspace";

interface ExportInfo {
  filename: string;
  status: string;
  mode: string;
  publications_in_report: number;
  excluded: number;
  partial_cells: number;
  unmatched_template_rows: number[];
  appended: number;
}

export default function ExportScreen({ c, user, reloadCase }: ScreenProps) {
  const files = useAsync(() => api.get<{ filename: string; size: number; created: string }[]>(`/api/cases/${c.id}/exports`), [c.id]);
  const [info, setInfo] = useState<ExportInfo | null>(null);
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  const [busy, setBusy] = useState(false);

  async function uploadTemplate(f: File) {
    try {
      await api.upload<Case>(`/api/cases/${c.id}/template`, f);
      setMsg({ ok: "התבנית נשמרה." });
      reloadCase();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    }
  }

  async function exportNow() {
    setBusy(true);
    setMsg({});
    try {
      const r = await api.post<ExportInfo>(`/api/cases/${c.id}/export`);
      setInfo(r);
      files.reload();
      await api.download(`/api/cases/${c.id}/exports/${encodeURIComponent(r.filename)}`, r.filename);
    } catch (e) {
      setMsg({ err: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="two-col">
      <div className="card">
        <h2>מסך 7 — יצירת קובץ Excel</h2>
        <h3>תבנית הדוח</h3>
        <p className="small">
          {c.template_filename ? (
            <>תבנית התיק: <En>{c.template_filename}</En></>
          ) : (
            "לא הועלתה תבנית — תשמש תבנית ברירת המחדל (A פרסום · B–C WoS · D–E Scopus · F–G Scholar · H–I סיכום)."
          )}
        </p>
        {user.role !== "reviewer" && (
          <label className="upload">
            <input type="file" accept=".xlsx" onChange={(e) => e.target.files?.[0] && uploadTemplate(e.target.files[0])} />
            <span className="btn">העלאת תבנית Excel של הפקולטה</span>
          </label>
        )}
        <ul className="small">
          <li>אם התבנית כבר מכילה את רשימת הפרסומים — השורות ימולאו במקומן (התאמה לפי הטקסט), והסדר והקטגוריות יישמרו.</li>
          <li>אם התבנית ריקה — השורות ייבנו לפי סדר קורות החיים והקטגוריות שלהם.</li>
          <li>ערכים חסרים לא יוחלפו באפס: "לא נבדק", "לא מאונדקס", "דורש אימות"; תוצאות חלקיות יסומנו "זמני".</li>
          <li>יתווסף גיליון <En>Audit Trail</En> עם מקורות, קישורים, תאריכים, החלטות סיווג ויומן שינויים.</li>
        </ul>
        {!c.reviewed_by && <div className="msg msg-warn">התיק טרם אושר בבקרת איכות — הקובץ יסומן כטיוטה (draft).</div>}
        <button className="btn primary" onClick={exportNow} disabled={busy}>
          {busy ? "יוצר…" : "יצירת הדוח והורדה"}
        </button>
        <Msg ok={msg.ok} error={msg.err} />
        {info && (
          <div className="kv">
            <div>קובץ</div><div><En>{info.filename}</En></div>
            <div>סטטוס</div><div>{info.status === "final" ? <Badge kind="ok">סופי</Badge> : <Badge kind="warn">טיוטה</Badge>}</div>
            <div>פרסומים בדוח</div><div>{info.publications_in_report} (מוחרגים: {info.excluded}, מתועדים ב-Audit Trail)</div>
            <div>תאים חלקיים</div><div>{info.partial_cells}</div>
            <div>אופן מילוי</div><div>{info.mode === "fill" ? "מילוי שורות התבנית" : "בניית שורות לפי קו״ח"}</div>
            {info.unmatched_template_rows.length > 0 && (<><div>שורות תבנית שלא הותאמו</div><div className="warn-text">{info.unmatched_template_rows.join(", ")}</div></>)}
            {info.appended > 0 && (<><div>נוספו בסוף התבנית</div><div className="warn-text">{info.appended}</div></>)}
          </div>
        )}
      </div>
      <div className="card">
        <h3>קבצים שהופקו</h3>
        {files.data?.length ? (
          <ul className="files">
            {files.data.map((f) => (
              <li key={f.filename}>
                <button className="link" onClick={() => api.download(`/api/cases/${c.id}/exports/${encodeURIComponent(f.filename)}`, f.filename)}>
                  <En>{f.filename}</En>
                </button>
                <span className="small muted"> · {fmtDate(f.created)} · {Math.round(f.size / 1024)}KB</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">עדיין לא הופקו דוחות.</p>
        )}
      </div>
    </div>
  );
}
