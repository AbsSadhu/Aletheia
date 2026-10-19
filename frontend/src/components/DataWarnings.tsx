interface DataWarningsProps {
  warnings?: string[];
}

/** Amber banner for run-level data-quality warnings (e.g. sample data used instead of live quotes). */
export default function DataWarnings({ warnings = [] }: DataWarningsProps) {
  if (warnings.length === 0) return null;
  return (
    <div
      role="alert"
      style={{
        fontSize: "var(--text-sm)",
        padding: "var(--space-3)",
        marginBottom: "var(--space-4)",
        background: "var(--amber-muted)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--amber)",
        color: "var(--amber)",
      }}
    >
      {warnings.map((w, i) => (
        <div key={i}>{w}</div>
      ))}
    </div>
  );
}
