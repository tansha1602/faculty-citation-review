import { useState } from "react";
import { api } from "../api";
import { Badge, En, Field, MetricCell, Msg, useAsync } from "../components";
import { CHECK_LABEL, PROVIDER_LABEL, fmtDate } from "../labels";
import { PROVIDERS, type Provider, type ProvidersInfo, type Publication } from "../types";
import type { ScreenProps } from "./CaseWorkspace";

export default function DatabasesScreen({ c, user, goto }: ScreenProps) {
  const pubs = useAsync(() => api.get<Publication[]>(`/api/cases/${c.id}/publications?detail=true`), [c.id]);
  const prov = useAsync(() => api.get<ProvidersInfo>("/api/providers"), []);
  const [open, setOpen] = useState<{ pub: number; provider: Provider } | null>(null);
  const [showExcluded, setShowExcluded] = useState(false);
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});
  const [busy, setBusy] = useState<string | null>(null);
  const canEdit = user.role !== "reviewer";

  if (pubs.error) return <Msg error={pubs.error} />;
  if (!pubs.data || !prov.data) return <p className="muted">טוען…</p>;
  const list = pubs.data.filter((p) => showExcluded || p.included);
  const openPub = open ? pubs.data.find((p) => p.id === open.pub) : undefined;

  async function bulk(provider: Provider) {
    setBusy(provider);
    setMsg({});
    try {
      const r = await api.post<{ searched: number; errors: string[] }>(`/api/cases/${c.id}/search/${provider}`);
      setMsg({ ok: `${PROVIDER_LABEL[provider]}: בוצע חיפוש ל-${r.searched} פרסומים. רשומות לא חד-משמעיות ממתינות לבחירה ידנית.`, err: r.errors.join("; ") || undefined });
      pubs.reload();
    } catch (e) {
      setMsg({ err: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <ProviderStatus info={prov.data} />
      <div className="card toolbar">
        <label className="check">
          <input type="checkbox" checked={showExcluded} onChange={(e) => setShowExcluded(e.target.checked)} />
          הצגת פרסומים מוחרגים
        </label>
        {canEdit && (
          <div className="actions">
            <button className="btn" disabled={!prov.data.scopus.configured || !!busy} onClick={() => bulk("scopus")}
              title={prov.data.scopus.configured ? "" : "Scopus אינו מוגדר"}>
              {busy === "scopus" ? "מחפש…" : "חיפוש כל הפרסומים ב-Scopus"}
            </button>
            <button className="btn" disabled={!prov.data.wos.configured || !!busy} onClick={() => bulk("wos")}
              title={prov.data.wos.configured ? "" : "Web of Science אינו מוגדר"}>
              {busy === "wos" ? "מחפש…" : "חיפוש כל הפרסומים ב-WoS"}
            </button>
          </div>
        )}
      </div>
      <Msg ok={msg.ok} error={msg.err} />
      <div className="table-wrap">
        <table className="table db-table">
          <thead>
            <tr>
              <th>#</th>
              <th>פרסום</th>
              {PROVIDERS.map((p) => (
                <th key={p}>{PROVIDER_LABEL[p]}</th>
              ))}
              <th>סיכום (H–I)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id} className={p.included ? "" : "excluded"}>
                <td>{p.seq}</td>
                <td className="pub-cell">
                  <En block>
                    <strong>{p.title || p.raw_text.slice(0, 120)}</strong>
                    <div className="small muted">
                      {p.authors.slice(0, 3).join("; ")}
                      {p.authors.length > 3 ? " et al." : ""} {p.year ? `(${p.year})` : ""} {p.doi && `· doi:${p.doi}`}
                    </div>
                  </En>
                  {!p.included && <div className="small warn-text">{p.exclusion_reason}</div>}
                </td>
                {PROVIDERS.map((pr) => (
                  <td key={pr} className="metric-td">
                    <MetricCell m={p.metrics?.[pr]} />
                    {canEdit && (
                      <button className="link small" onClick={() => setOpen({ pub: p.id, provider: pr })}>
                        {p.metrics?.[pr]?.status === "found" ? "עריכה" : "בדיקה"}
                      </button>
                    )}
                  </td>
                ))}
                <td className="small">
                  {p.summary && p.summary.non_self !== null ? (
                    <span className={p.summary.complete ? "" : "warn-text"} title={`${p.summary.label}\n${p.summary.note}`}>
                      {p.summary.complete ? "" : "זמני: "}
                      {p.summary.non_self} / {p.summary.self}
                    </span>
                  ) : (
                    <span className="muted" title={p.summary?.note}>—</span>
                  )}
                </td>
                <td>
                  <button className="btn small-btn" onClick={() => goto(4, p.id)}>
                    מצטטים
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && openPub && (
        <ProviderPanel
          pub={openPub}
          provider={open.provider}
          info={prov.data}
          onClose={() => setOpen(null)}
          onChange={(np) => pubs.setData(pubs.data!.map((x) => (x.id === np.id ? np : x)))}
        />
      )}
    </div>
  );
}

function ProviderStatus({ info }: { info: ProvidersInfo }) {
  const [show, setShow] = useState(!info.scopus.configured || !info.wos.configured);
  return (
    <div className="card">
      <div className="toolbar">
        <div className="provider-chips">
          <Badge kind={info.scopus.configured ? "ok" : "warn"}>Scopus API: {info.scopus.configured ? "מוגדר" : "לא מוגדר"}</Badge>
          <Badge kind={info.wos.configured ? "ok" : "warn"}>WoS Starter API: {info.wos.configured ? "מוגדר" : "לא מוגדר"}</Badge>
          <Badge kind={info.wos.citing_api ? "ok" : "idle"}>WoS Expanded (מצטטים): {info.wos.citing_api ? "מוגדר" : "לא מוגדר"}</Badge>
          <Badge kind="info">Google Scholar: הזנה ידנית</Badge>
        </div>
        <button className="link" onClick={() => setShow(!show)}>
          {show ? "הסתרת" : "הצגת"} ההרשאות הנדרשות
        </button>
      </div>
      {show && (
        <div className="requirements small">
          <p>
            לפני חיבור לשירותים חיצוניים יש להגדיר את המפתחות כמשתני סביבה בקובץ <En>.env</En> (לא בקוד ולא בדוחות). ללא מפתח — ניתן
            להזין נתונים ידנית ולייבא קובצי ייצוא מהמאגרים.
          </p>
          <ul>
            {[...info.scopus.requirements, ...info.wos.requirements, ...info.scholar.requirements].map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="muted">{info.external_ai.note}</p>
        </div>
      )}
    </div>
  );
}

function ProviderPanel({
  pub,
  provider,
  info,
  onClose,
  onChange,
}: {
  pub: Publication;
  provider: Provider;
  info: ProvidersInfo;
  onClose: () => void;
  onChange: (p: Publication) => void;
}) {
  const m = pub.metrics?.[provider];
  const chk = pub.checks?.[provider];
  const cands = (pub.candidates || []).filter((r) => r.provider === provider);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [total, setTotal] = useState("");
  const [url, setUrl] = useState("");
  const [rid, setRid] = useState("");
  const [notes, setNotes] = useState("");
  const configured = provider === "scopus" ? info.scopus.configured : provider === "wos" ? info.wos.configured : false;

  async function run<T>(fn: () => Promise<T>) {
    setBusy(true);
    setErr(null);
    try {
      const r = (await fn()) as unknown as Publication;
      if (r && "id" in r) onChange(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drawer-back" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={PROVIDER_LABEL[provider]}>
        <div className="drawer-head">
          <h2>
            {PROVIDER_LABEL[provider]} · פרסום #{pub.seq}
          </h2>
          <button className="link" onClick={onClose} aria-label="סגירה">
            ✕
          </button>
        </div>
        <En block>
          <div className="raw small">{pub.raw_text}</div>
        </En>
        <div className="kv">
          <div>מצב</div>
          <div>
            <Badge kind={chk?.status === "found" ? "ok" : "warn"}>{CHECK_LABEL[chk?.status || "not_checked"]}</Badge>
          </div>
          <div>נבדק</div>
          <div>
            {fmtDate(chk?.checked_at)} {chk?.checked_by}
          </div>
          {chk?.notes && (
            <>
              <div>הערה</div>
              <div>{chk.notes}</div>
            </>
          )}
          {m?.status === "found" && (
            <>
              <div>סך ציטוטים</div>
              <div>{m.total ?? "—"}</div>
              <div>מזהה רשומה</div>
              <div className="mono">{m.record_id || "—"}</div>
            </>
          )}
        </div>
        <Msg error={err} />

        {provider !== "scholar" && (
          <section>
            <h3>חיפוש ב-API</h3>
            {configured ? (
              <button className="btn primary" disabled={busy} onClick={() => run(() => api.post(`/api/publications/${pub.id}/search/${provider}`))}>
                {busy ? "מחפש…" : pub.doi ? "חיפוש לפי DOI" : "חיפוש לפי כותרת, מחבר ושנה"}
              </button>
            ) : (
              <p className="small warn-text">ה-API אינו מוגדר. ניתן להזין רשומה מאומתת ידנית (למטה) לאחר בדיקה באתר המאגר.</p>
            )}
          </section>
        )}

        {provider === "scholar" && (
          <section>
            <h3>תהליך מונחה — Google Scholar</h3>
            <ol className="small">
              <li>
                פתחו את החיפוש:{" "}
                <a href={pub.scholar_search_url} target="_blank" rel="noreferrer">
                  חיפוש הפרסום ב-Google Scholar ↗
                </a>
              </li>
              <li>ודאו שהרשומה היא הפרסום המקורי (ולא גרסה מוקדמת, פרסום כנס או כותרת דומה).</li>
              <li>לחצו על "Cited by" והעתיקו את כתובת הדף ואת המספר.</li>
              <li>לרשימת המצטטים: הזינו ידנית או ייבאו קובץ שהושג בדרך מותרת (מסך 5).</li>
            </ol>
            <p className="hint">המערכת אינה מבצעת scraping ואינה עוקפת CAPTCHA או חסימות.</p>
          </section>
        )}

        {cands.length > 0 && (
          <section>
            <h3>רשומות שנמצאו</h3>
            <p className="hint">בחירה אוטומטית מתבצעת רק בהתאמה חד-משמעית. בכל מקרה אחר — בחרו ידנית.</p>
            {cands.map((r) => (
              <div key={r.id} className={`cand ${r.record_status === "selected" ? "selected" : ""}`}>
                <En block>
                  <strong>{r.found_title}</strong>
                  <div className="small">
                    {r.found_authors.map((a) => a.name).slice(0, 5).join("; ")} {r.found_year && `(${r.found_year})`} {r.found_doi && `· ${r.found_doi}`}
                  </div>
                </En>
                <div className="small">
                  ציון התאמה <strong>{Math.round(r.confidence * 100)}%</strong> — {r.confidence_explanation} · ציטוטים: {r.total_citations ?? "—"} ·{" "}
                  {r.method === "manual" ? `ידני (${r.entered_by})` : "API"} · {fmtDate(r.retrieved_at)}
                </div>
                <div className="actions">
                  {r.source_url && (
                    <a href={r.source_url} target="_blank" rel="noreferrer" className="small">
                      פתיחת הרשומה ↗
                    </a>
                  )}
                  {r.record_status === "selected" ? (
                    <Badge kind="ok">נבחרה</Badge>
                  ) : (
                    <button className="btn small-btn" disabled={busy}
                      onClick={() => run(() => api.post(`/api/publications/${pub.id}/select/${provider}`, { record_id: r.id }))}>
                      זו הרשומה הנכונה
                    </button>
                  )}
                </div>
              </div>
            ))}
          </section>
        )}

        <section>
          <h3>הזנה ידנית של רשומה מאומתת</h3>
          <div className="grid-form">
            <Field label="סך ציטוטים במאגר *">
              <input dir="ltr" inputMode="numeric" value={total} onChange={(e) => setTotal(e.target.value.replace(/\D/g, ""))} />
            </Field>
            <Field label={provider === "scholar" ? "קישור לדף Cited by" : "קישור לרשומה"}>
              <input dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
            </Field>
            <Field label={provider === "scopus" ? "Scopus EID" : provider === "wos" ? "WoS UID" : "מזהה (cluster) — אופציונלי"}>
              <input dir="ltr" value={rid} onChange={(e) => setRid(e.target.value)} />
            </Field>
            <Field label="הערה">
              <input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </Field>
          </div>
          <button className="btn primary" disabled={busy || total === ""}
            onClick={() => run(() => api.post(`/api/publications/${pub.id}/manual/${provider}`,
              { total_citations: Number(total), source_url: url, record_id: rid, notes }))}>
            שמירת רשומה מאומתת
          </button>
          <p className="hint">0 פירושו שהפרסום אותר ונבדק ולא נמצאו ציטוטים. אם הפרסום לא נמצא — סמנו "לא מאונדקס".</p>
        </section>

        <section>
          <h3>סימון מצב</h3>
          <div className="actions">
            <button className="btn" disabled={busy}
              onClick={() => run(() => api.post(`/api/publications/${pub.id}/status/${provider}`, { status: "not_indexed", notes: notes || "לא נמצא במאגר" }))}>
              לא מאונדקס
            </button>
            <button className="btn" disabled={busy}
              onClick={() => run(() => api.post(`/api/publications/${pub.id}/status/${provider}`, { status: "needs_verification", notes }))}>
              דורש אימות
            </button>
            <button className="btn ghost" disabled={busy}
              onClick={() => run(() => api.post(`/api/publications/${pub.id}/status/${provider}`, { status: "not_checked", notes }))}>
              איפוס ל"לא נבדק"
            </button>
          </div>
        </section>
      </aside>
    </div>
  );
}
