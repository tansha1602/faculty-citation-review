import { useState } from "react";
import { api } from "../api";
import { Badge, En, Field, MetricCell, Msg, useAsync } from "../components";
import { CLASS_LABEL, LIST_STATUS_LABEL, PROVIDER_LABEL } from "../labels";
import { PROVIDERS, type Author, type Citing, type Policy, type Provider, type Publication } from "../types";
import type { ScreenProps } from "./CaseWorkspace";

const CLS_KIND: Record<string, string> = { self: "warn", non_self: "ok", needs_verification: "error" };

export default function CitingScreen({ c, user, initialPub }: ScreenProps & { initialPub?: number }) {
  const pubs = useAsync(() => api.get<Publication[]>(`/api/cases/${c.id}/publications`), [c.id]);
  const policy = useAsync(() => api.get<Policy>(`/api/cases/${c.id}/policy`), [c.id]);
  const [pubId, setPubId] = useState<number | undefined>(initialPub);
  const [provider, setProvider] = useState<Provider>("scopus");
  const included = (pubs.data || []).filter((p) => p.included);
  const current = pubId ?? included[0]?.id;

  if (pubs.error) return <Msg error={pubs.error} />;
  if (!pubs.data || !policy.data) return <p className="muted">טוען…</p>;
  if (!included.length) return <div className="card">אין פרסומים נכללים.</div>;

  return (
    <div>
      <div className="card toolbar">
        <Field label="פרסום">
          <select value={current} onChange={(e) => setPubId(Number(e.target.value))} className="wide-select">
            {included.map((p) => (
              <option key={p.id} value={p.id}>
                #{p.seq} — {p.title.slice(0, 90) || p.raw_text.slice(0, 90)}
              </option>
            ))}
          </select>
        </Field>
        <div className="seg">
          {PROVIDERS.map((p) => (
            <button key={p} className={provider === p ? "on" : ""} onClick={() => setProvider(p)}>
              {PROVIDER_LABEL[p]}
            </button>
          ))}
        </div>
      </div>
      {current && (
        <CitingPanel key={`${current}-${provider}`} pubId={current} provider={provider} canEdit={user.role !== "reviewer"}
          canReview definition={policy.data.self_citation_definition} />
      )}
    </div>
  );
}

function CitingPanel({ pubId, provider, canEdit, definition }: {
  pubId: number; provider: Provider; canEdit: boolean; canReview: boolean; definition: "A" | "B";
}) {
  const pub = useAsync(() => api.get<Publication>(`/api/publications/${pubId}`), [pubId]);
  const citing = useAsync(() => api.get<Citing[]>(`/api/publications/${pubId}/citing?provider=${provider}`), [pubId, provider]);
  const [msg, setMsg] = useState<{ ok?: string; err?: string; warn?: string[] }>({});
  const [complete, setComplete] = useState(false);
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState<"all" | "verify" | "self">("all");
  const reload = () => (pub.reload(), citing.reload());

  if (pub.error || citing.error) return <Msg error={pub.error || citing.error} />;
  if (!pub.data || !citing.data) return <p className="muted">טוען…</p>;
  const m = pub.data.metrics?.[provider];
  const chk = pub.data.checks?.[provider];
  const finalKey = definition === "A" ? "final_a" : "final_b";
  const rows = citing.data.filter((r) =>
    filter === "all" ? true : filter === "verify" ? r.final_a === "needs_verification" || r.final_b === "needs_verification" : r[finalKey] === "self");

  async function importFile(f: File) {
    setMsg({});
    try {
      const r = await api.upload<{ added: number; skipped_duplicates: number; warnings: string[] }>(
        `/api/publications/${pubId}/citing/${provider}/import`, f, { list_complete: String(complete) });
      setMsg({ ok: `יובאו ${r.added} רשומות (${r.skipped_duplicates} כפולות דולגו).`, warn: r.warnings });
      reload();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    }
  }

  async function fetchApi() {
    setMsg({});
    try {
      const r = await api.post<{ added: number; skipped_duplicates: number; status: string; note: string }>(
        `/api/publications/${pubId}/citing/${provider}/fetch`);
      setMsg({ ok: `נמשכו ${r.added} רשומות · רשימה ${LIST_STATUS_LABEL[r.status]} · ${r.note}` });
      reload();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    }
  }

  return (
    <div>
      <div className="card">
        <En block>
          <div className="raw small">{pub.data.raw_text}</div>
        </En>
        <div className="summary-row">
          <div>
            <div className="muted small">{PROVIDER_LABEL[provider]}</div>
            <MetricCell m={m} />
          </div>
          {m && m.status === "found" && (
            <table className="mini">
              <thead>
                <tr><th></th><th>הגדרה A (החוקר/ת)</th><th>הגדרה B (מחבר משותף)</th></tr>
              </thead>
              <tbody>
                <tr><td>עצמיים</td><td>{m.self_a}</td><td>{m.self_b}</td></tr>
                <tr><td>לא עצמיים (מסווגים)</td><td>{m.non_self_a}</td><td>{m.non_self_b}</td></tr>
                <tr><td>דורשים אימות</td><td>{m.unresolved_a}</td><td>{m.unresolved_b}</td></tr>
                <tr><td>חסרים ברשימה (סה״כ − רשומות)</td><td colSpan={2}>{m.missing_records}</td></tr>
              </tbody>
            </table>
          )}
        </div>
        {m?.warnings.map((w) => <div key={w} className="small warn-text">⚠ {w}</div>)}
        {m && !m.complete && m.status === "found" && (
          <div className="msg msg-warn">בדיקה לא הושלמה — התוצאה חלקית וזמנית. הגדרה בדוח: {definition}.</div>
        )}
      </div>

      {canEdit && (
        <div className="card">
          <h3>הוספת רשימת מצטטים</h3>
          {m?.status !== "found" && <p className="small warn-text">יש לאמת את הרשומה במאגר (מסך 4) לפני משיכה מה-API. ייבוא קובץ אפשרי בכל מקרה.</p>}
          <div className="actions wrap">
            {provider !== "scholar" && (
              <button className="btn" onClick={fetchApi} disabled={m?.status !== "found"}>
                משיכת מצטטים מה-API
              </button>
            )}
            <label className="upload">
              <input type="file" accept=".csv,.tsv,.txt,.xlsx" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
              <span className="btn">ייבוא קובץ (CSV / Excel / ייצוא WoS או Scopus)</span>
            </label>
            <label className="check small">
              <input type="checkbox" checked={complete} onChange={(e) => setComplete(e.target.checked)} />
              הקובץ מכיל את כל המצטטים
            </label>
            <button className="btn" onClick={() => setAdding(!adding)}>+ הוספה ידנית</button>
            <span className="small">
              מצב הרשימה:{" "}
              <select value={chk?.citing_list_status || "none"} onChange={async (e) => {
                await api.post(`/api/publications/${pubId}/citing/${provider}/list-status`, { citing_list_status: e.target.value });
                reload();
              }}>
                {Object.entries(LIST_STATUS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </span>
          </div>
          {provider === "scholar" && (
            <p className="hint">Google Scholar: ייבוא רק של קובץ שהושג בדרך מותרת ובהתאם לרישיון. המערכת אינה ממציאה רשימת מצטטים.</p>
          )}
          {adding && <AddCiting pubId={pubId} provider={provider} onDone={() => (setAdding(false), reload())} />}
          <Msg ok={msg.ok} error={msg.err} />
          {msg.warn && msg.warn.length > 0 && <ul className="warn-list">{msg.warn.map((w) => <li key={w}>{w}</li>)}</ul>}
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <h3>פרסומים מצטטים ({citing.data.length})</h3>
          <div className="seg">
            <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>הכול</button>
            <button className={filter === "verify" ? "on" : ""} onClick={() => setFilter("verify")}>דורשים אימות</button>
            <button className={filter === "self" ? "on" : ""} onClick={() => setFilter("self")}>עצמיים ({definition})</button>
          </div>
        </div>
        {rows.length === 0 && <p className="muted">אין רשומות.</p>}
        {rows.map((r) => <CitingRow key={r.id} r={r} canEdit={canEdit} onChange={reload} />)}
      </div>
    </div>
  );
}

function authorLabel(a: Author) {
  const id = a.orcid ? `ORCID ${a.orcid}` : a.scopus_id ? `Scopus ${a.scopus_id}` : a.researcher_id ? `RID ${a.researcher_id}` : "";
  return id ? `${a.name} [${id}]` : a.name;
}

function CitingRow({ r, canEdit, onChange }: { r: Citing; canEdit: boolean; onChange: () => void }) {
  const [edit, setEdit] = useState(false);
  const [a, setA] = useState(r.manual_a || "");
  const [b, setB] = useState(r.manual_b || "");
  const [note, setNote] = useState(r.manual_note);
  const [err, setErr] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    try {
      await api.patch(`/api/citing/${r.id}`, body);
      setEdit(false);
      setErr(null);
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="citing">
      <div className="citing-main">
        <En block>
          <strong>{r.title}</strong> {r.year && <span className="muted">({r.year})</span>}
          <div className="small">
            {r.authors.length ? r.authors.map(authorLabel).join("; ") : <span className="warn-text">אין פרטי מחברים</span>}
            {!r.authors_complete && r.authors.length > 0 && <span className="warn-text"> · רשימת מחברים חלקית</span>}
          </div>
          <div className="small muted">
            {r.doi && <>doi:{r.doi} · </>}
            {r.external_id && <>{r.external_id} · </>}
            {r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">קישור ↗</a>}
          </div>
        </En>
        <div className="small muted">מקור: {r.origin} {r.origin_detail}</div>
      </div>
      <div className="citing-cls">
        {(["a", "b"] as const).map((k) => {
          const fin = k === "a" ? r.final_a : r.final_b;
          const manual = k === "a" ? r.manual_a : r.manual_b;
          return (
            <div key={k} className="cls">
              <span className="small muted">{k === "a" ? "A" : "B"}:</span>{" "}
              <Badge kind={CLS_KIND[fin]}>{CLASS_LABEL[fin]}</Badge> {manual && <Badge kind="info">ידני</Badge>}
              <div className="small muted">{k === "a" ? r.explain_a : r.explain_b}</div>
            </div>
          );
        })}
        {r.manual_note && <div className="small">הערה: {r.manual_note}</div>}
        {r.manually_confirmed && <div className="small"><Badge kind="ok">אושר ידנית · {r.confirmed_by}</Badge></div>}
        {canEdit && !edit && (
          <div className="actions">
            <button className="btn small-btn" onClick={() => setEdit(true)}>שינוי סיווג</button>
            {!r.manually_confirmed && <button className="btn small-btn" onClick={() => patch({ confirm: true })}>אישור הסיווג</button>}
            <button className="btn small-btn ghost" onClick={async () => {
              if (confirm("למחוק רשומה זו (למשל רשומה שיובאה בטעות)?")) {
                await api.del(`/api/citing/${r.id}`);
                onChange();
              }
            }}>מחיקה</button>
          </div>
        )}
        {edit && (
          <div className="grid-form edit-box">
            <Field label="סיווג לפי הגדרה A">
              <select value={a} onChange={(e) => setA(e.target.value)}>
                <option value="">אוטומטי ({CLASS_LABEL[r.class_a]})</option>
                {Object.entries(CLASS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <Field label="סיווג לפי הגדרה B">
              <select value={b} onChange={(e) => setB(e.target.value)}>
                <option value="">אוטומטי ({CLASS_LABEL[r.class_b]})</option>
                {Object.entries(CLASS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <Field label="נימוק (חובה בשינוי ידני)">
              <input value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            <div className="actions span-2">
              <button className="btn primary" onClick={() => patch({
                manual_a: a || null, manual_b: b || null, clear_a: !a, clear_b: !b, manual_note: note, confirm: true,
              })}>שמירה ואישור</button>
              <button className="btn" onClick={() => setEdit(false)}>ביטול</button>
            </div>
          </div>
        )}
        <Msg error={err} />
      </div>
    </div>
  );
}

function AddCiting({ pubId, provider, onDone }: { pubId: number; provider: Provider; onDone: () => void }) {
  const [v, setV] = useState({ title: "", doi: "", year: "", url: "", authors: "", complete: true });
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="grid-form edit-box">
      <Field label="כותרת המצטט *"><input dir="ltr" value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
      <Field label="DOI"><input dir="ltr" value={v.doi} onChange={(e) => setV({ ...v, doi: e.target.value })} /></Field>
      <Field label="שנה"><input dir="ltr" value={v.year} onChange={(e) => setV({ ...v, year: e.target.value })} /></Field>
      <Field label="קישור"><input dir="ltr" value={v.url} onChange={(e) => setV({ ...v, url: e.target.value })} /></Field>
      <Field label="מחברים — שורה לכל מחבר" hint="אפשר להוסיף מזהה אחרי |: ORCID, Scopus Author ID או ResearcherID">
        <textarea dir="ltr" rows={3} value={v.authors} onChange={(e) => setV({ ...v, authors: e.target.value })} />
      </Field>
      <label className="check">
        <input type="checkbox" checked={v.complete} onChange={(e) => setV({ ...v, complete: e.target.checked })} />
        רשימת המחברים מלאה
      </label>
      <Msg error={err} />
      <div className="actions span-2">
        <button className="btn primary" disabled={!v.title.trim()} onClick={async () => {
          const authors: Author[] = v.authors.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
            const [name, id] = l.split("|").map((s) => s.trim());
            if (!id) return { name };
            if (/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/i.test(id)) return { name, orcid: id };
            if (/^\d{6,}$/.test(id)) return { name, scopus_id: id };
            return { name, researcher_id: id };
          });
          try {
            await api.post(`/api/publications/${pubId}/citing/${provider}`, {
              title: v.title, doi: v.doi, year: v.year ? Number(v.year) : null, source_url: v.url, authors,
              authors_complete: v.complete,
            });
            onDone();
          } catch (e) {
            setErr((e as Error).message);
          }
        }}>הוספה</button>
      </div>
    </div>
  );
}
