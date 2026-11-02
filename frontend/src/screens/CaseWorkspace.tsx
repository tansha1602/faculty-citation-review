import { useState } from "react";
import { api } from "../api";
import { En, Msg, useAsync } from "../components";
import type { Case, User } from "../types";
import CaseScreen from "./CaseScreen";
import ExtractionScreen from "./ExtractionScreen";
import PolicyScreen from "./PolicyScreen";
import DatabasesScreen from "./DatabasesScreen";
import CitingScreen from "./CitingScreen";
import QAScreen from "./QAScreen";
import ExportScreen from "./ExportScreen";

const STEPS = [
  "פתיחת תיק וקורות חיים",
  "בדיקת רשימת הפרסומים",
  "מדיניות",
  "טבלת פרסומים ומאגרים",
  "פרסומים מצטטים",
  "בקרת איכות ואישור",
  "יצירת דוח Excel",
];

export interface ScreenProps {
  c: Case;
  user: User;
  reloadCase: () => void;
  goto: (step: number, pubId?: number) => void;
}

export default function CaseWorkspace({ caseId, user, onBack }: { caseId: number; user: User; onBack: () => void }) {
  const { data: c, error, reload } = useAsync(() => api.get<Case>(`/api/cases/${caseId}`), [caseId]);
  const [step, setStep] = useState(0);
  const [focusPub, setFocusPub] = useState<number | undefined>();

  if (error) return <Msg error={error} />;
  if (!c) return <p className="muted">טוען…</p>;
  const props: ScreenProps = {
    c,
    user,
    reloadCase: reload,
    goto: (s, pubId) => {
      setFocusPub(pubId);
      setStep(s);
      window.scrollTo({ top: 0 });
    },
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <button className="link" onClick={onBack}>
            → כל התיקים
          </button>
          <h1>
            <En>{c.researcher_name_en}</En> {c.researcher_name_he && <span className="muted">· {c.researcher_name_he}</span>}
          </h1>
        </div>
        <div className="small muted">
          {c.reviewed_by ? `אושר על ידי ${c.reviewed_by}` : c.prepared_by ? `הוכן על ידי ${c.prepared_by} — ממתין לבודק` : "בעבודה"}
        </div>
      </div>
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "active" : ""}>
            <button onClick={() => props.goto(i)}>
              <span className="step-num">{i + 1}</span>
              <span>{s}</span>
            </button>
          </li>
        ))}
      </ol>
      <section className="screen">
        {step === 0 && <CaseScreen {...props} />}
        {step === 1 && <ExtractionScreen {...props} />}
        {step === 2 && <PolicyScreen {...props} />}
        {step === 3 && <DatabasesScreen {...props} />}
        {step === 4 && <CitingScreen {...props} initialPub={focusPub} />}
        {step === 5 && <QAScreen {...props} />}
        {step === 6 && <ExportScreen {...props} />}
      </section>
    </div>
  );
}
