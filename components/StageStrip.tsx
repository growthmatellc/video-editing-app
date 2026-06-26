import { statusColor, type StageStatus } from "@/lib/stage-ui";

interface Props {
  stages: { stageKey: string; stageOrder: number; status: StageStatus }[];
  className?: string;
}

/** A per-stage progress strip: one segment per pipeline stage, colored by status. */
export function StageStrip({ stages, className = "" }: Props) {
  const ordered = [...stages].sort((a, b) => a.stageOrder - b.stageOrder);
  return (
    <div className={`flex gap-1 ${className}`} aria-label="Pipeline progress">
      {ordered.map((s) => (
        <span
          key={s.stageKey}
          title={`${s.stageKey}: ${s.status}`}
          className="h-1.5 flex-1 rounded-full"
          style={{ background: statusColor(s.status) }}
        />
      ))}
    </div>
  );
}
