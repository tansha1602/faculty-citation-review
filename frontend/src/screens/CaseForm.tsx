import { useState } from "react";
import { Field } from "../components";

export interface CaseValues {
  researcher_name_en: string;
  researcher_name_he: string;
  name_variants: string[];
  orcid: string;
  scopus_author_id: string;
  wos_researcher_id: string;
  notes: string;
}

export const emptyCase: CaseValues = {
  researcher_name_en: "",
  researcher_name_he: "",
  name_variants: [],
  orcid: "",
  scopus_author_id: "",
  wos_researcher_id: "",
  notes: "",
};

export default function CaseForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
  disabled,
}: {
  initial: CaseValues;
  onSubmit: (v: CaseValues) => Promise<void>;
  onCancel?: () => void;
  submitLabel: string;
  disabled?: boolean;
}) {
  const [v, setV] = useState<CaseValues>(initial);
  const [variants, setVariants] = useState((initial.name_variants || []).join("\n"));
  const [busy, setBusy] = useState(false);
  const set = (k: keyof CaseValues) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setV({ ...v, [k]: e.target.value });

  return (
    <form
      className="grid-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSubmit({ ...v, name_variants: variants.split("\n").map((s) => s.trim()).filter(Boolean) });
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field label="שם החוקר/ת באנגלית *" hint="כפי שמופיע בפרסומים, לדוגמה: Dana Example">
        <input dir="ltr" value={v.researcher_name_en} onChange={set("researcher_name_en")} required disabled={disabled} />
      </Field>
      <Field label="שם בעברית">
        <input value={v.researcher_name_he} onChange={set("researcher_name_he")} disabled={disabled} />
      </Field>
      <Field label="ORCID" hint="0000-0000-0000-0000">
        <input dir="ltr" value={v.orcid} onChange={set("orcid")} disabled={disabled} />
      </Field>
      <Field label="Scopus Author ID">
        <input dir="ltr" value={v.scopus_author_id} onChange={set("scopus_author_id")} disabled={disabled} />
      </Field>
      <Field label="Web of Science ResearcherID">
        <input dir="ltr" value={v.wos_researcher_id} onChange={set("wos_researcher_id")} disabled={disabled} />
      </Field>
      <Field label="וריאנטים של השם (שורה לכל וריאנט)" hint="למשל: Example, D. · שם נעורים · איות חלופי">
        <textarea dir="ltr" rows={3} value={variants} onChange={(e) => setVariants(e.target.value)} disabled={disabled} />
      </Field>
      <Field label="הערות">
        <textarea rows={2} value={v.notes} onChange={set("notes")} disabled={disabled} />
      </Field>
      {!disabled && (
        <div className="actions span-2">
          <button className="btn primary" disabled={busy}>
            {submitLabel}
          </button>
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              ביטול
            </button>
          )}
        </div>
      )}
    </form>
  );
}
