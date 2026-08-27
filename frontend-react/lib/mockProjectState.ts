const STORAGE_PREFIX = "cosmos_mock_";

// Stopgap localStorage-backed state standing in for Phase A/B's real
// Projects/Auth persistence. Every function here should be REPLACED, not
// extended, once Phase A/B ship - see the React frontend migration design
// spec's Open Items.

export type ProjectStatus = "Draft" | "Active";

export function getProjectStatus(caseId: string): ProjectStatus {
  if (typeof window === "undefined") return "Draft";
  return (localStorage.getItem(`${STORAGE_PREFIX}status_${caseId}`) as ProjectStatus) || "Draft";
}

export function setProjectStatus(caseId: string, status: ProjectStatus): void {
  localStorage.setItem(`${STORAGE_PREFIX}status_${caseId}`, status);
}

export function getSessionId(caseId: string): number | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}session_${caseId}`);
  return raw ? parseInt(raw, 10) : null;
}

export function setSessionId(caseId: string, sessionId: number): void {
  localStorage.setItem(`${STORAGE_PREFIX}session_${caseId}`, String(sessionId));
}

export interface ProjectSetupData {
  industryContext: string;
  assignedClient: string;
}

const DEFAULT_SETUP: ProjectSetupData = {
  industryContext: "",
  assignedClient: "",
};

export function getProjectSetup(caseId: string): ProjectSetupData {
  if (typeof window === "undefined") return DEFAULT_SETUP;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}setup_${caseId}`);
  return raw ? JSON.parse(raw) : DEFAULT_SETUP;
}

export function setProjectSetup(caseId: string, data: ProjectSetupData): void {
  localStorage.setItem(`${STORAGE_PREFIX}setup_${caseId}`, JSON.stringify(data));
}

export type ArtifactPurpose = "reference" | "case_study_external" | "case_study_internal" | "case_study_resolution";
export type ArtifactStatus = "Uploaded" | "Processing" | "Indexed" | "Transcript Needed";

export interface MockArtifact {
  filename: string;
  purpose: ArtifactPurpose;
  status: ArtifactStatus;
}

const DEFAULT_ARTIFACTS: MockArtifact[] = [
  { filename: "Market_Sizing.pdf", purpose: "reference", status: "Indexed" },
  { filename: "External_Case_Study.docx", purpose: "case_study_external", status: "Indexed" },
  { filename: "Internal_Case_Study.pptx", purpose: "case_study_internal", status: "Processing" },
  { filename: "Board_Debrief_Recording.mp3", purpose: "case_study_resolution", status: "Transcript Needed" },
];

export function getArtifacts(caseId: string): MockArtifact[] {
  if (typeof window === "undefined") return DEFAULT_ARTIFACTS;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}artifacts_${caseId}`);
  return raw ? JSON.parse(raw) : DEFAULT_ARTIFACTS;
}

export function setArtifacts(caseId: string, artifacts: MockArtifact[]): void {
  localStorage.setItem(`${STORAGE_PREFIX}artifacts_${caseId}`, JSON.stringify(artifacts));
}
