import { IconCheck, IconHelp, IconX } from "@tabler/icons-react";
import type { Prescore } from "@/lib/types";

const ICONS = {
  pass: <IconCheck size={15} className="pos" />,
  fail: <IconX size={15} className="neg" />,
  unknown: <IconHelp size={15} className="warn" />,
} as const;

/** The 8 deterministic strategy checks with evidence (backend prescore). */
export default function PrescoreChecklist({ prescore }: { prescore: Prescore }) {
  const badgeTone =
    prescore.passed >= 6 ? "success" : prescore.passed >= 4 ? "warning" : "danger";

  return (
    <div className="card">
      <p style={{ fontWeight: 500, marginBottom: 8 }}>
        Wynik reguł{" "}
        <span className={`badge ${badgeTone}`}>
          {prescore.passed} / {prescore.total}
        </span>
      </p>
      <div className="checklist">
        {prescore.checks.map((check) => (
          <div className="check" key={check.id}>
            {ICONS[check.verdict]}
            <span>
              {check.name} <span className="evidence">{check.evidence}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
