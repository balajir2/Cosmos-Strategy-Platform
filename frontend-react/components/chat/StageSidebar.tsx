import { StageProgress } from "@/lib/api-client";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

type StageStatus = "done" | "current" | "upcoming";

interface StageSidebarProps {
  stages: StageProgress[];
  currentQuestionIndex: number;
  isComplete: boolean;
}

export function computeStageStatuses(
  stages: StageProgress[],
  currentQuestionIndex: number,
  isComplete: boolean
): Array<{ stage: StageProgress; status: StageStatus }> {
  let cumulative = 0;
  return stages.map((stage) => {
    const start = cumulative;
    const end = cumulative + stage.question_count;
    cumulative = end;
    if (isComplete || currentQuestionIndex >= end) {
      return { stage, status: "done" as const };
    }
    if (currentQuestionIndex >= start && currentQuestionIndex < end) {
      return { stage, status: "current" as const };
    }
    return { stage, status: "upcoming" as const };
  });
}

export default function StageSidebar({ stages, currentQuestionIndex, isComplete }: StageSidebarProps) {
  if (stages.length === 0) return null;
  const items = computeStageStatuses(stages, currentQuestionIndex, isComplete);

  return (
    <nav className={styles.sidebar} aria-label="Engagement stages">
      {items.map(({ stage, status }) => (
        <div
          key={stage.id}
          className={[
            styles.stageItem,
            status === "done" ? styles.stageItemDone : "",
            status === "current" ? styles.stageItemCurrent : "",
          ].join(" ")}
        >
          {status === "done" && <i className="fa-solid fa-circle-check" style={{ marginRight: 6 }}></i>}
          {stage.name}
        </div>
      ))}
    </nav>
  );
}
