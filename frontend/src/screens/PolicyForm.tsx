import { useState } from "react";
import { LANGUAGE_LABEL, STATUS_LABEL, SUMMARY_LABEL, TYPE_LABEL } from "../labels";
import type { Policy } from "../types";

type PolicyValues = Omit<Policy, "id" | "case_id" | "updated_at" | "updated_by">;

function Checks({
  options,
  value,
  onChange,
  disabled,
}: {
  options: Record<string, string>;
  value: string[];
  onChange: (v: string[]) => void;
  disabled: boolean;
}) {
  return (
    <div className="checks">
      {Object.entries(options).map(([k, l]) => (
        <label key={k} className="check">
          <input
            type="checkbox"
            checked={value.includes(k)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked ? [...value, k] : value.filter((x) => x !== k))}
          />
          {l}
        </label>
      ))}
    </div>
  );
}

export default function PolicyForm({
  policy,
  canEdit,
  onSave,
}: {
  policy: Policy;
  canEdit: boolean;
  onSave: (v: PolicyValues) => Promise<void>;
}) {
  const [v, setV] = useState<PolicyValues>({
    included_languages: policy.included_languages,
    included_statuses: policy.included_statuses,
    included_types: policy.included_types,
    self_citation_definition: policy.self_citation_definition,
    full_name_match_is_self: policy.full_name_match_is_self,
    summary_mode: policy.summary_mode,
  });
  const dis = !canEdit;
  return (
    <div className="policy">
      <fieldset>
        <legend>שפות הפרסום הנכללות</legend>
        <Checks options={LANGUAGE_LABEL} value={v.included_languages} disabled={dis} onChange={(x) => setV({ ...v, included_languages: x })} />
        <p className="hint">ברירת המחדל: אנגלית בלבד. השפה נקבעת לפי שפת הפרסום בפועל ולא לפי שפת הכותרת.</p>
      </fieldset>
      <fieldset>
        <legend>סטטוסי פרסום הנכללים</legend>
        <Checks options={STATUS_LABEL} value={v.included_statuses} disabled={dis} onChange={(x) => setV({ ...v, included_statuses: x })} />
        <p className="hint">פרסום שהתקבל (Accepted) עשוי כבר להיות זמין ברשת ולהיות מצוטט.</p>
      </fieldset>
      <fieldset>
        <legend>סוגי פרסום הנכללים</legend>
        <Checks options={TYPE_LABEL} value={v.included_types} disabled={dis} onChange={(x) => setV({ ...v, included_types: x })} />
      </fieldset>
      <fieldset>
        <legend>הגדרת ציטוט עצמי לדוח</legend>
        <label className="radio">
          <input type="radio" disabled={dis} checked={v.self_citation_definition === "A"} onChange={() => setV({ ...v, self_citation_definition: "A" })} />
          <span>
            <strong>הגדרה A</strong> — ציטוט עצמי של החוקר/ת הנבדק/ת: מופיע/ה גם בפרסום המצוטט וגם בפרסום המצטט.
          </span>
        </label>
        <label className="radio">
          <input type="radio" disabled={dis} checked={v.self_citation_definition === "B"} onChange={() => setV({ ...v, self_citation_definition: "B" })} />
          <span>
            <strong>הגדרה B</strong> — ציטוט עצמי של אחד ממחברי הפרסום: לפחות מחבר אחד משותף לפרסום המקורי ולמצטט.
          </span>
        </label>
        <p className="hint">שתי ההגדרות מחושבות תמיד ומוצגות בגיליון הביקורת; הדוח הרשמי משתמש בהגדרה שנבחרה כאן.</p>
        <label className="check">
          <input
            type="checkbox"
            disabled={dis}
            checked={v.full_name_match_is_self}
            onChange={(e) => setV({ ...v, full_name_match_is_self: e.target.checked })}
          />
          שם מלא זהה (שם פרטי + משפחה) ללא מזהה ייחודי נחשב התאמה. אם לא מסומן — מועבר לאימות ידני.
        </label>
        <p className="hint">התאמה לפי ראשי תיבות או שם משפחה בלבד תמיד מועברת לאימות ידני. מזהה שונה (ORCID/Scopus/ResearcherID) תמיד גובר.</p>
      </fieldset>
      <fieldset>
        <legend>עמודות H–I (סיכום)</legend>
        {Object.entries(SUMMARY_LABEL).map(([k, l]) => (
          <label key={k} className="radio">
            <input type="radio" disabled={dis} checked={v.summary_mode === k} onChange={() => setV({ ...v, summary_mode: k as Policy["summary_mode"] })} />
            <span>{l}</span>
          </label>
        ))}
        <p className="hint">
          "ייחודיים" מחושב רק כאשר רשימות המצטטים בכל המאגרים מלאות ומסווגות (הסרת כפילויות לפי DOI או כותרת+שנה זהות). בכל מקרה
          הדוח מציין במפורש אם מדובר בסכום או בספירה ייחודית.
        </p>
      </fieldset>
      {canEdit ? (
        <button className="btn primary" onClick={() => onSave(v)}>
          שמירת מדיניות
        </button>
      ) : (
        <p className="muted small">רק מנהל מערכת רשאי לשנות את המדיניות.</p>
      )}
    </div>
  );
}
