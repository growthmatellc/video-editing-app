import { theme } from "@/theme/tokens";

export type StageStatus =
  | "not_started"
  | "running"
  | "draft"
  | "approved"
  | "rejected";

export function statusColor(status: StageStatus): string {
  switch (status) {
    case "approved":
      return theme.color.ok;
    case "draft":
      return theme.color.warn;
    case "running":
      return theme.color.accent;
    case "rejected":
      return "#E0654E";
    case "not_started":
    default:
      return theme.color.border;
  }
}

export function statusLabel(status: StageStatus): string {
  switch (status) {
    case "not_started":
      return "Not started";
    case "running":
      return "Running…";
    case "draft":
      return "Draft";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    default:
      return status;
  }
}
