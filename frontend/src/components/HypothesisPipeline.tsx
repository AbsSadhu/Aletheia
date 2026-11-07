import Flap from "./Flap";

const STAGES = [
  { key: "proposed", label: "Proposed", note: "an idea, not yet tested" },
  { key: "testing", label: "Testing", note: "evidence being gathered" },
  { key: "validated", label: "Validated", note: "held up against evidence" },
  { key: "rejected", label: "Rejected", note: "did not hold up" },
] as const;

/**
 * Where the research stands: four stage tiles with flip-cell counts, and one segmented bar that
 * shows the split at a glance. Counts come straight from the list it is given.
 */
export default function HypothesisPipeline({ statuses }: { statuses: string[] }) {
  const total = statuses.length;
  const count = (k: string) => statuses.filter((s) => s === k).length;
  return (
    <div className="pipeline" style={{ marginBottom: "var(--space-5)" }}>
      <div className="grid-4">
        {STAGES.map((s) => (
          <div className={`card pipe-${s.key}`} key={s.key}>
            <div className="stat-label" style={{ marginTop: 0 }}>{s.label}</div>
            <div className="pipe-figure">
              <Flap text={String(count(s.key))} hold={false} />
            </div>
            <div className="pipe-note">{s.note}</div>
          </div>
        ))}
      </div>
      {total > 0 && (
        <div className="pipe-bar" role="img" aria-label={STAGES.map((s) => `${count(s.key)} ${s.label.toLowerCase()}`).join(", ")}>
          {STAGES.map((s) => (
            <span key={s.key} className={`pipe-seg pipe-${s.key}`} style={{ flexGrow: count(s.key) }} />
          ))}
        </div>
      )}
    </div>
  );
}
