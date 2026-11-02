import { useEffect, useState, type ReactNode } from "react";
import type { Metrics } from "./types";

export function En({ children, block }: { children: ReactNode; block?: boolean }) {
  return block ? (
    <div dir="ltr" className="en">
      {children}
    </div>
  ) : (
    <bdi dir="ltr" className="en">
      {children}
    </bdi>
  );
}

export function Msg({ error, ok }: { error?: string | null; ok?: string | null }) {
  if (error) return <div className="msg msg-error" role="alert">{error}</div>;
  if (ok) return <div className="msg msg-ok" role="status">{ok}</div>;
  return null;
}

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge badge-${kind}`}>{children}</span>;
}

export function MetricCell({ m }: { m?: Metrics }) {
  if (!m) return <span className="muted">—</span>;
  if (m.status !== "found") {
    const kind = m.status === "not_indexed" ? "muted" : m.status === "needs_verification" ? "warn" : "idle";
    return <Badge kind={kind}>{m.status_label}</Badge>;
  }
  if (m.total === null) return <Badge kind="warn">חסר סך ציטוטים</Badge>;
  return (
    <div className="metric">
      <div>
        <strong>{m.total}</strong> <span className="muted">סה״כ</span>
      </div>
      {m.complete ? (
        <div className="small">
          לא עצמי {m.non_self_formula} · עצמי {m.self_selected}
        </div>
      ) : (
        <div className="small warn-text" title={m.warnings.join("\n")}>
          זמני: ≥{m.non_self_selected} / ≥{m.self_selected} · {m.unresolved_selected} לא מסווגים
        </div>
      )}
      {m.source_url && (
        <a href={m.source_url} target="_blank" rel="noreferrer" className="small">
          קישור לרשומה ↗
        </a>
      )}
    </div>
  );
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}
