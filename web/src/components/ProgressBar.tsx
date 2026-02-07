import type { MaturityLevel } from "@/lib/progress/types";
import { maturityColor, maturityLabel } from "@/lib/ui/colors";

export function ProgressBar({
  label,
  score,
  maturity,
  note,
}: {
  label: string;
  score: number;
  maturity: MaturityLevel;
  note?: string;
}) {
  const color = maturityColor(maturity);
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold tracking-wide text-white/85">
            {label}
          </div>
          {note ? (
            <div className="mt-1 text-xs leading-5 text-white/45">{note}</div>
          ) : null}
        </div>
        <div className="text-right">
          <div className="text-xs font-semibold text-white/90">
            {score.toFixed(1)}
          </div>
          <div className="text-[11px] text-white/50">{maturityLabel(maturity)}</div>
        </div>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(0, Math.min(100, score))}%`,
            background: `linear-gradient(90deg, ${color}, rgba(255,255,255,0.15))`,
            boxShadow: `0 0 18px ${color}55`,
          }}
        />
      </div>
    </div>
  );
}

