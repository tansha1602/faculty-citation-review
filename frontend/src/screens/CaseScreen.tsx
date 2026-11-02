import { useState } from "react";
import { api } from "../api";
import { En, Msg } from "../components";
import { fmtDate } from "../labels";
import type { Case } from "../types";
import CaseForm from "./CaseForm";
import type { ScreenProps } from "./CaseWorkspace";

export default function CaseScreen({ c, user, reloadCase, goto }: ScreenProps) {
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const canEdit = user.role !== "reviewer";

  async function uploadCv(f: File) {
    if (c.publication_count && !confirm("העלאה חדשה תחליף את רשימת הפרסומים ואת כל נתוני הבדיקה של התיק. להמשיך?")) return;
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const r = await api.upload<{ count: number; section_found: boolean; section_heading: string; warnings: string[] }>(
        `/api/cases/${c.id}/cv`,
        f,
      );
      setOk(`חולצו ${r.count} פרסומים${r.section_found ? ` מתוך הפרק "${r.section_heading}"` : ""}. יש לעבור לבדיקת הרשימה.`);
      setWarnings(r.warnings);
      reloadCase();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="two-col">
      <div className="card">
        <h2>פרטי החוקר/ת</h2>
        <p className="small muted">המזהים הייחודיים משמשים לזיהוי ציטוטים עצמיים ולהבחנה בין אנשים בעלי שם זהה.</p>
        <CaseForm
          key={c.id + (c.researcher_name_en || "")}
          initial={c}
          disabled={!canEdit}
          submitLabel="שמירת פרטים"
          onSubmit={async (v) => {
            try {
              await api.put<Case>(`/api/cases/${c.id}`, v);
              setOk("הפרטים נשמרו. הסיווג של ציטוטים עצמיים חושב מחדש.");
              reloadCase();
            } catch (e) {
              setErr((e as Error).message);
            }
          }}
        />
      </div>
      <div className="card">
        <h2>קורות חיים</h2>
        <p className="small muted">PDF או Word (DOCX). החילוץ מתבצע במחשב זה בלבד. הקובץ נשמר בתיק עם חתימת SHA-256 לצורכי ביקורת.</p>
        {c.cv_filename ? (
          <div className="kv">
            <div>קובץ</div>
            <div>
              <En>{c.cv_filename}</En>
            </div>
            <div>הועלה</div>
            <div>{fmtDate(c.cv_uploaded_at)}</div>
            <div>SHA-256</div>
            <div className="mono small">{c.cv_sha256.slice(0, 16)}…</div>
            <div>פרסומים שחולצו</div>
            <div>{c.publication_count}</div>
          </div>
        ) : (
          <p className="muted">טרם הועלו קורות חיים.</p>
        )}
        {canEdit && (
          <label className="upload">
            <input type="file" accept=".pdf,.docx" disabled={busy} onChange={(e) => e.target.files?.[0] && uploadCv(e.target.files[0])} />
            <span className="btn primary">{busy ? "מחלץ…" : c.cv_filename ? "העלאת גרסה חדשה" : "העלאת קורות חיים"}</span>
          </label>
        )}
        <Msg error={err} ok={ok} />
        {warnings.length > 0 && (
          <ul className="warn-list">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        {!!c.publication_count && (
          <button className="btn" onClick={() => goto(1)}>
            המשך לבדיקת הרשימה ←
          </button>
        )}
      </div>
    </div>
  );
}
