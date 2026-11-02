import type { Provider } from "./types";

export const PROVIDER_LABEL: Record<Provider, string> = {
  wos: "Web of Science",
  scopus: "Scopus",
  scholar: "Google Scholar",
};

export const LANGUAGE_LABEL: Record<string, string> = {
  english: "אנגלית",
  hebrew: "עברית",
  german: "גרמנית",
  other: "אחר",
};

export const STATUS_LABEL: Record<string, string> = {
  published: "פורסם (Published)",
  online_first: "פורסם מקוון (Online first)",
  accepted: "התקבל (Accepted)",
  submitted: "הוגש (Submitted)",
  unpublished: "לא פורסם (Unpublished)",
};

export const TYPE_LABEL: Record<string, string> = {
  journal_article: "מאמר בכתב עת",
  book: "ספר",
  book_chapter: "פרק בספר",
  conference: "כנס",
  report: "דוח",
  other: "אחר",
};

export const CHECK_LABEL: Record<string, string> = {
  not_checked: "לא נבדק",
  found: "נמצא",
  not_indexed: "לא מאונדקס",
  needs_verification: "דורש אימות",
};

export const CLASS_LABEL: Record<string, string> = {
  self: "עצמי",
  non_self: "לא עצמי",
  needs_verification: "דורש אימות",
};

export const LIST_STATUS_LABEL: Record<string, string> = {
  none: "לא הוזנה",
  partial: "חלקית",
  complete: "מלאה",
  unavailable: "לא זמינה",
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "מנהל",
  librarian: "עובד/ת ספרייה",
  reviewer: "בודק/ת",
};

export const SUMMARY_LABEL: Record<string, string> = {
  sum: "סכום המאגרים (לא ייחודי)",
  unique: "ציטוטים ייחודיים (לאחר הסרת כפילויות)",
  max: "המאגר עם הערך הגבוה (לא ייחודי)",
  empty: "השארת H–I ריקות",
};

export function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short" });
}
