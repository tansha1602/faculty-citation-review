import { useState } from "react";
import { api } from "../api";
import { Badge, En, Field, Msg, useAsync } from "../components";
import { LANGUAGE_LABEL, STATUS_LABEL, TYPE_LABEL } from "../labels";
import type { Publication } from "../types";
import type { ScreenProps } from "./CaseWorkspace";

export default function ExtractionScreen({ c, user, reloadCase, goto }: ScreenProps) {
  const { data, error, reload, setData } = useAsync(() => api.get<Publication[]>(`/api/cases/${c.id}/publications`), [c.id]);
  const [editing, setEditing] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "included" | "excluded">("all");
  const [adding, setAdding] = useState(false);
  const canEdit = user.role !== "reviewer";

  if (error) return <Msg error={error} />;
  if (!data) return <p className="muted">טוען…</p>;
  if (!data.length)
    return (
      <div className="card">
        <p>לא חולצו פרסומים. העלו קורות חיים במסך 1.</p>
      </div>
    );

  const shown = data.filter((p) => filter === "all" || (filter === "included" ? p.included : !p.included));
  let lastSub = "";

  return (
    <div>
      <div className="card toolbar">
        <div>
          <strong>{data.length}</strong> פרסומים · <strong>{data.filter((p) => p.included).length}</strong> נכללים ·{" "}
          <strong>{data.filter((p) => !p.included).length}</strong> מוחרגים (נשמרים עם סיבה)
        </div>
        <div className="seg">
          {(["all", "included", "excluded"] as const).map((f) => (
            <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
              {f === "all" ? "הכול" : f === "included" ? "נכללים" : "מוחרגים"}
            </button>
          ))}
        </div>
        <div className="actions">
          {canEdit && (
            <button className="btn" onClick={() => setAdding(!adding)}>
              + הוספת פרסום שלא חולץ
            </button>
          )}
          {c.extraction_confirmed ? (
            <Badge kind="ok">הרשימה אושרה</Badge>
          ) : (
            canEdit && (
              <button
                className="btn primary"
                onClick={async () => {
                  await api.post(`/api/cases/${c.id}/confirm-extraction`);
                  reloadCase();
                  goto(2);
                }}
              >
                אישור הרשימה והמשך
              </button>
            )
          )}
        </div>
      </div>
      <p className="small muted">
        הטקסט המקורי מקורות החיים נשמר תמיד ללא שינוי. השדות המובנים (כותרת, מחברים, שנה…) חולצו אוטומטית — יש לבדוק ולתקן לפני
        החיפוש במאגרים. רשומות אינן מאוחדות אוטומטית גם אם כותרותיהן דומות.
      </p>
      {adding && <AddPublication caseId={c.id} onDone={() => (setAdding(false), reload(), reloadCase())} />}
      <Msg error={err} />
      <div className="pub-list">
        {shown.map((p) => {
          const sub = p.subsection || p.section;
          const header = sub !== lastSub ? <h3 className="sub-head">{sub}</h3> : null;
          lastSub = sub;
          return (
            <div key={p.id}>
              {header}
              <div className={`pub-card ${p.included ? "" : "excluded"}`}>
                <div className="pub-head">
                  <span className="pub-num">#{p.seq}</span>
                  <span className="small muted">
                    מס׳ בקו״ח: {p.original_number || "—"} · עמוד {p.cv_page ?? "—"}
                  </span>
                  <Badge kind={p.language === "english" ? "idle" : "warn"}>{LANGUAGE_LABEL[p.language]}</Badge>
                  <Badge kind={p.pub_status === "published" ? "idle" : "warn"}>{STATUS_LABEL[p.pub_status]}</Badge>
                  <Badge kind="idle">{TYPE_LABEL[p.pub_type]}</Badge>
                  {p.manually_edited && <Badge kind="info">תוקן ידנית</Badge>}
                  {p.included ? <Badge kind="ok">נכלל</Badge> : <Badge kind="muted">מוחרג</Badge>}
                </div>
                <En block>
                  <div className="raw">{p.raw_text}</div>
                </En>
                {!p.included && <div className="small warn-text">{p.exclusion_reason}</div>}
                {p.included && p.manual_include && <div className="small">{p.exclusion_reason}</div>}
                {editing === p.id ? (
                  <EditPublication
                    p={p}
                    onCancel={() => setEditing(null)}
                    onSaved={(np) => {
                      setData(data.map((x) => (x.id === np.id ? np : x)));
                      setEditing(null);
                    }}
                    onError={setErr}
                  />
                ) : (
                  <div className="pub-fields">
                    <div>
                      <span className="muted">כותרת:</span> <En>{p.title || "—"}</En>
                    </div>
                    <div>
                      <span className="muted">מחברים:</span> <En>{p.authors.join("; ") || "—"}</En>
                    </div>
                    <div>
                      <span className="muted">שנה:</span> {p.year ?? "—"} · <span className="muted">מקום פרסום:</span>{" "}
                      <En>{p.venue || "—"}</En> · <span className="muted">DOI:</span> <En>{p.doi || "—"}</En>
                    </div>
                    <div className="small muted">
                      שפה: {p.language_evidence} · סטטוס: {p.status_evidence}
                    </div>
                    {canEdit && (
                      <div className="actions">
                        <button className="btn small-btn" onClick={() => setEditing(p.id)}>
                          תיקון נתונים
                        </button>
                        <button
                          className="btn small-btn ghost"
                          title="רק לשגיאת חילוץ (למשל כותרת שזוהתה כפרסום). להחרגה יש להשתמש בתיקון נתונים."
                          onClick={async () => {
                            if (!confirm("למחוק את הרשומה כשגיאת חילוץ? (להחרגה של פרסום אמיתי יש להשתמש ב'החרגה ידנית')")) return;
                            try {
                              await api.del(`/api/publications/${p.id}`);
                              reload();
                              reloadCase();
                            } catch (e) {
                              setErr((e as Error).message);
                            }
                          }}
                        >
                          מחיקת שגיאת חילוץ
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EditPublication({
  p,
  onCancel,
  onSaved,
  onError,
}: {
  p: Publication;
  onCancel: () => void;
  onSaved: (p: Publication) => void;
  onError: (e: string) => void;
}) {
  const [v, setV] = useState({
    title: p.title,
    authors: p.authors.join("\n"),
    year: p.year?.toString() ?? "",
    venue: p.venue,
    doi: p.doi,
    pub_type: p.pub_type,
    language: p.language,
    pub_status: p.pub_status,
    original_number: p.original_number,
    cv_page: p.cv_page?.toString() ?? "",
    subsection: p.subsection,
    include: p.manual_include === null ? "policy" : p.manual_include ? "yes" : "no",
    reason: p.manual_include_reason,
    notes: p.notes,
  });
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setV({ ...v, [k]: e.target.value });

  async function save() {
    const body: Record<string, unknown> = {
      title: v.title,
      authors: v.authors.split("\n").map((s) => s.trim()).filter(Boolean),
      year: v.year ? Number(v.year) : null,
      venue: v.venue,
      doi: v.doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//, ""),
      pub_type: v.pub_type,
      language: v.language,
      pub_status: v.pub_status,
      original_number: v.original_number,
      cv_page: v.cv_page ? Number(v.cv_page) : null,
      subsection: v.subsection,
      notes: v.notes,
    };
    if (v.include === "policy") body.clear_manual_include = p.manual_include !== null;
    else {
      body.manual_include = v.include === "yes";
      body.manual_include_reason = v.reason;
    }
    try {
      onSaved(await api.patch<Publication>(`/api/publications/${p.id}`, body));
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <div className="grid-form edit-box">
      <Field label="כותרת">
        <input dir="ltr" value={v.title} onChange={set("title")} />
      </Field>
      <Field label="מחברים (שורה לכל מחבר)" hint="רצוי שם מלא: Surname, Given name">
        <textarea dir="ltr" rows={3} value={v.authors} onChange={set("authors")} />
      </Field>
      <Field label="שנה">
        <input dir="ltr" value={v.year} onChange={set("year")} inputMode="numeric" />
      </Field>
      <Field label="כתב עת / ספר">
        <input dir="ltr" value={v.venue} onChange={set("venue")} />
      </Field>
      <Field label="DOI">
        <input dir="ltr" value={v.doi} onChange={set("doi")} />
      </Field>
      <Field label="סוג פרסום">
        <select value={v.pub_type} onChange={set("pub_type")}>
          {Object.entries(TYPE_LABEL).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </Field>
      <Field label="שפת הפרסום (בפועל, לא לפי הכותרת)">
        <select value={v.language} onChange={set("language")}>
          {Object.entries(LANGUAGE_LABEL).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </Field>
      <Field label="סטטוס פרסום">
        <select value={v.pub_status} onChange={set("pub_status")}>
          {Object.entries(STATUS_LABEL).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </Field>
      <Field label="מספר בקורות החיים">
        <input dir="ltr" value={v.original_number} onChange={set("original_number")} />
      </Field>
      <Field label="עמוד בקורות החיים">
        <input dir="ltr" value={v.cv_page} onChange={set("cv_page")} inputMode="numeric" />
      </Field>
      <Field label="קטגוריה (תת-פרק)">
        <input dir="ltr" value={v.subsection} onChange={set("subsection")} />
      </Field>
      <Field label="הכללה">
        <select value={v.include} onChange={set("include")}>
          <option value="policy">לפי המדיניות</option>
          <option value="yes">הכללה ידנית</option>
          <option value="no">החרגה ידנית</option>
        </select>
      </Field>
      {v.include !== "policy" && (
        <Field label="סיבת ההכללה/ההחרגה (חובה)">
          <input value={v.reason} onChange={set("reason")} required />
        </Field>
      )}
      <Field label="הערות">
        <textarea rows={2} value={v.notes} onChange={set("notes")} />
      </Field>
      <div className="actions span-2">
        <button className="btn primary" onClick={save}>
          שמירה
        </button>
        <button className="btn" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </div>
  );
}

function AddPublication({ caseId, onDone }: { caseId: number; onDone: () => void }) {
  const [raw, setRaw] = useState("");
  const [sub, setSub] = useState("");
  const [num, setNum] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="card grid-form">
      <Field label="הטקסט הביבליוגרפי המלא, כפי שמופיע בקורות החיים">
        <textarea dir="ltr" rows={3} value={raw} onChange={(e) => setRaw(e.target.value)} />
      </Field>
      <Field label="קטגוריה">
        <input dir="ltr" value={sub} onChange={(e) => setSub(e.target.value)} />
      </Field>
      <Field label="מספר בקורות החיים">
        <input dir="ltr" value={num} onChange={(e) => setNum(e.target.value)} />
      </Field>
      <Msg error={err} />
      <div className="actions span-2">
        <button
          className="btn primary"
          disabled={raw.trim().length < 10}
          onClick={async () => {
            try {
              await api.post(`/api/cases/${caseId}/publications`, { raw_text: raw, subsection: sub, original_number: num });
              onDone();
            } catch (e) {
              setErr((e as Error).message);
            }
          }}
        >
          הוספה בסוף הרשימה
        </button>
      </div>
    </div>
  );
}
