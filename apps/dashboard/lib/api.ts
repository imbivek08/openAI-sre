/** Typed API client for the OpenSRE AI backend. */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Incident {
  id: string;
  source: string;
  title: string;
  summary: string;
  service: string;
  repository: string;
  external_run_id: string;
  severity: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Finding {
  id: string;
  hypothesis: string;
  confidence: number;
  confidence_rationale: string;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  explanation: string;
  next_diagnostics: string[];
  remediation: string[];
  human_approval_required: boolean;
  is_primary: boolean;
}

export interface Investigation {
  id: string;
  incident_id: string;
  provider: string;
  model: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  iterations: number;
  tool_calls: number;
  error: string;
  limits_reached: boolean;
  report: Record<string, unknown> | null;
  findings: Finding[];
}

export interface InvestigationEvent {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface Evidence {
  id: string;
  source_type: string;
  source_id: string;
  excerpt: string;
  retrieved_at: string | null;
  tool: string;
  metadata: Record<string, unknown>;
  content_hash: string;
  sensitivity: string;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  dependencies: { name: string; status: string; detail: string }[];
  llm: {
    provider: string;
    model: string;
    tool_calling: boolean;
    configured: boolean;
    base_url: string;
  };
}

export interface DemoStatus {
  reachable: boolean;
  scenarios: Record<string, { title: string; description: string }>;
  active_faults: string[];
  health: Record<string, unknown> | null;
  error: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/health"),

  listIncidents: (params?: { source?: string; status?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams();
    if (params?.source) q.set("source", params.source);
    if (params?.status) q.set("status", params.status);
    if (params?.page) q.set("page", String(params.page));
    if (params?.page_size) q.set("page_size", String(params.page_size));
    return request<Paginated<Incident>>(`/api/v1/incidents?${q.toString()}`);
  },

  getIncident: (id: string) => request<Incident>(`/api/v1/incidents/${id}`),

  createIncident: (body: { source: string; title: string; summary: string; service?: string; severity?: string }) =>
    request<Incident>("/api/v1/incidents", { method: "POST", body: JSON.stringify(body) }),

  investigate: (incidentId: string) =>
    request<{ investigation_id: string; incident_id: string; status: string }>(
      `/api/v1/incidents/${incidentId}/investigate`,
      { method: "POST" }
    ),

  getInvestigation: (id: string) => request<Investigation>(`/api/v1/investigations/${id}`),

  getInvestigationEvents: (id: string) =>
    request<Paginated<InvestigationEvent>>(`/api/v1/investigations/${id}/events`),

  getInvestigationEvidence: (id: string) =>
    request<Paginated<Evidence>>(`/api/v1/investigations/${id}/evidence`),

  demoStatus: () => request<DemoStatus>("/api/v1/demo/status"),

  triggerScenario: (scenario: string, adminKey: string) =>
    request<{ scenario: string; status: string }>(`/api/v1/demo/scenarios/${scenario}/trigger`, {
      method: "POST",
      headers: { "X-API-Key": adminKey },
    }),

  resetDemo: (adminKey: string) =>
    request<{ status: string }>("/api/v1/demo/reset", {
      method: "POST",
      headers: { "X-API-Key": adminKey },
    }),
};
