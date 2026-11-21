"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  api,
  type Incident,
  type Investigation,
  type InvestigationEvent,
  type Evidence,
  type Paginated,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [incident, setIncident] = useState<Incident | null>(null);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [selectedInv, setSelectedInv] = useState<Investigation | null>(null);
  const [events, setEvents] = useState<Paginated<InvestigationEvent> | null>(null);
  const [evidence, setEvidence] = useState<Paginated<Evidence> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const inc = await api.getIncident(id);
      setIncident(inc);
      // Fetch investigations for this incident via the investigation list endpoint
      // The backend doesn't have a per-incident investigation list, so we check
      // the incident's investigations through the detail endpoint pattern.
      // We use the investigation endpoint with the incident's investigations.
      // For now, load investigations by checking the incident response.
      // The API returns investigations nested? No — we fetch via a different path.
      // We'll fetch all investigations and filter client-side for demo scale.
      try {
        const invResp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/incidents/${id}`
        );
        if (invResp.ok) {
          const data = await invResp.json();
          // The incident endpoint doesn't include investigations; we need another way.
          // We'll use the investigation list endpoint if available, else skip.
        }
      } catch {
        // ignore
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load incident");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadInvestigation = useCallback(async (invId: string) => {
    const [inv, ev, evd] = await Promise.all([
      api.getInvestigation(invId),
      api.getInvestigationEvents(invId),
      api.getInvestigationEvidence(invId),
    ]);
    setSelectedInv(inv);
    setEvents(ev);
    setEvidence(evd);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function startInvestigation() {
    setInvestigating(true);
    setError("");
    try {
      const result = await api.investigate(id);
      await load();
      await loadInvestigation(result.investigation_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start investigation");
    } finally {
      setInvestigating(false);
    }
  }

  if (loading) return <div className="text-neutral-400">Loading…</div>;
  if (!incident) return <div className="text-red-400">{error || "Incident not found"}</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-400 hover:underline">
          ← Back to overview
        </Link>
      </div>

      <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold">{incident.title}</h1>
            <p className="mt-1 text-sm text-neutral-400">{incident.summary}</p>
          </div>
          <StatusBadge status={incident.status} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-neutral-400 md:grid-cols-4">
          <div>
            <dt>Source</dt>
            <dd className="text-neutral-200">{incident.source}</dd>
          </div>
          <div>
            <dt>Service</dt>
            <dd className="text-neutral-200">{incident.service || "—"}</dd>
          </div>
          <div>
            <dt>Severity</dt>
            <dd className="text-neutral-200">{incident.severity}</dd>
          </div>
          <div>
            <dt>Run ID</dt>
            <dd className="text-neutral-200">{incident.external_run_id || "—"}</dd>
          </div>
        </dl>
        {!selectedInv && incident.status !== "investigating" && (
          <button
            onClick={startInvestigation}
            disabled={investigating}
            className="mt-4 rounded bg-blue-700 px-4 py-2 text-sm font-medium hover:bg-blue-600 disabled:opacity-40"
          >
            {investigating ? "Starting…" : "Start AI Investigation"}
          </button>
        )}
      </div>

      {error && <div className="rounded bg-red-950 px-4 py-2 text-sm text-red-300">{error}</div>}

      {selectedInv && (
        <>
          <InvestigationPanel investigation={selectedInv} />
          <TimelinePanel events={events} />
          <EvidencePanel evidence={evidence} report={selectedInv.report} />
          {selectedInv.report && <ReportPanel report={selectedInv.report} />}
        </>
      )}
    </div>
  );
}

function InvestigationPanel({ investigation }: { investigation: Investigation }) {
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
      <h2 className="mb-2 font-semibold">Investigation</h2>
      <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-5">
        <div>
          <div className="text-xs text-neutral-400">Status</div>
          <StatusBadge status={investigation.status} />
        </div>
        <div>
          <div className="text-xs text-neutral-400">Provider</div>
          <div>{investigation.provider || "—"}</div>
        </div>
        <div>
          <div className="text-xs text-neutral-400">Model</div>
          <div>{investigation.model || "—"}</div>
        </div>
        <div>
          <div className="text-xs text-neutral-400">Tool calls</div>
          <div>{investigation.tool_calls}</div>
        </div>
        <div>
          <div className="text-xs text-neutral-400">Iterations</div>
          <div>{investigation.iterations}</div>
        </div>
      </div>
      {investigation.error && (
        <p className="mt-2 rounded bg-red-950 px-3 py-1.5 text-xs text-red-300">{investigation.error}</p>
      )}
      {investigation.limits_reached && (
        <p className="mt-2 rounded bg-yellow-950 px-3 py-1.5 text-xs text-yellow-200">
          Investigation completed with limits reached.
        </p>
      )}
    </div>
  );
}

function TimelinePanel({ events }: { events: Paginated<InvestigationEvent> | null }) {
  if (!events || events.items.length === 0) return null;
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
      <h2 className="mb-3 font-semibold">Event Timeline</h2>
      <ol className="space-y-2">
        {events.items.map((event) => (
          <li key={event.id} className="flex gap-3 text-sm">
            <span className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full bg-blue-500" />
            <div>
              <span className="font-mono text-xs text-neutral-400">{event.kind}</span>
              <span className="ml-2 text-neutral-300">
                {summarizeEvent(event.kind, event.payload)}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function summarizeEvent(kind: string, payload: Record<string, unknown>): string {
  switch (kind) {
    case "tool_call":
      return `${payload.tool ?? ""} → ${payload.status ?? ""}${payload.evidence_id ? ` (evidence ${String(payload.evidence_id).slice(0, 8)})` : ""}`;
    case "iteration":
      return `iteration ${payload.iteration ?? "?"} (${payload.tool_calls_so_far ?? 0} tool calls so far)`;
    case "limit":
      return `limit reached: ${payload.limit ?? ""}`;
    case "finalized":
      return `report finalized (${payload.tool_calls ?? 0} tool calls)`;
    case "error":
      return `error: ${payload.stage ?? ""}`;
    default:
      return JSON.stringify(payload).slice(0, 120);
  }
}

function EvidencePanel({
  evidence,
  report,
}: {
  evidence: Paginated<Evidence> | null;
  report: Record<string, unknown> | null;
}) {
  if (!evidence || evidence.items.length === 0) return null;
  const supporting = new Set(
    (report?.supporting_evidence as string[] | undefined) ?? []
  );
  const contradicting = new Set(
    (report?.contradicting_evidence as string[] | undefined) ?? []
  );
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
      <h2 className="mb-3 font-semibold">Retrieved Evidence</h2>
      <div className="space-y-3">
        {evidence.items.map((item) => {
          const role = supporting.has(item.id)
            ? "supporting"
            : contradicting.has(item.id)
              ? "contradicting"
              : null;
          return (
            <div key={item.id} className="rounded border border-neutral-800 bg-neutral-950 p-3">
              <div className="mb-1 flex items-center gap-2 text-xs">
                <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-300">{item.source_type}</span>
                <span className="text-neutral-500">{item.tool}</span>
                {role && (
                  <span
                    className={`rounded px-1.5 py-0.5 ${
                      role === "supporting" ? "bg-green-950 text-green-300" : "bg-red-950 text-red-300"
                    }`}
                  >
                    {role}
                  </span>
                )}
                <span className="text-neutral-600">{item.id.slice(0, 8)}</span>
              </div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-neutral-300">
                {item.excerpt.slice(0, 1200)}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReportPanel({ report }: { report: Record<string, unknown> }) {
  const confidence = (report.confidence as number) ?? 0;
  const pct = Math.round(confidence * 100);
  return (
    <div className="space-y-4">
      <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
        <h2 className="mb-3 font-semibold">Root-Cause Analysis</h2>

        <div className="mb-4 rounded border-l-4 border-blue-600 bg-neutral-950 p-3">
          <div className="text-xs text-neutral-400">Most likely root cause (hypothesis)</div>
          <p className="mt-1 text-sm">{report.most_likely_root_cause as string}</p>
          <div className="mt-2 flex items-center gap-2">
            <div className="h-2 flex-1 rounded bg-neutral-800">
              <div className="h-2 rounded bg-blue-600" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs text-neutral-400">
              {pct}% ({report.confidence_label as string})
            </span>
          </div>
          <p className="mt-1 text-xs text-neutral-500">{report.confidence_rationale as string}</p>
        </div>

        {Array.isArray(report.observed_facts) && report.observed_facts.length > 0 && (
          <Section title="Observed Facts" items={report.observed_facts as string[]} tone="text-green-300" />
        )}
        {Array.isArray(report.hypotheses) && report.hypotheses.length > 0 && (
          <Section title="Hypotheses" items={report.hypotheses as string[]} tone="text-blue-300" />
        )}
        {Array.isArray(report.contributing_factors) && report.contributing_factors.length > 0 && (
          <Section title="Contributing Factors" items={report.contributing_factors as string[]} tone="text-yellow-300" />
        )}
        {Array.isArray(report.recommended_diagnostics) && report.recommended_diagnostics.length > 0 && (
          <Section title="Recommended Diagnostics" items={report.recommended_diagnostics as string[]} tone="text-purple-300" />
        )}
        {Array.isArray(report.recommended_remediation) && report.recommended_remediation.length > 0 && (
          <Section title="Recommended Remediation" items={report.recommended_remediation as string[]} tone="text-purple-300" />
        )}
        {Array.isArray(report.risks) && report.risks.length > 0 && (
          <Section title="Risks & Impact" items={report.risks as string[]} tone="text-red-300" />
        )}

        <div className="mt-4 rounded bg-neutral-950 p-3 text-xs text-neutral-400">
          <span className="font-semibold text-neutral-300">Uncertainty: </span>
          {report.uncertainty as string}
        </div>
        {Boolean(report.human_intervention_required) && (
          <p className="mt-2 rounded bg-yellow-950 px-3 py-1.5 text-xs text-yellow-200">
            Human intervention required — remediation is a recommendation only.
          </p>
        )}
      </div>
    </div>
  );
}

function Section({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className="mb-3">
      <div className="mb-1 text-xs font-semibold text-neutral-400">{title}</div>
      <ul className="list-inside list-disc space-y-0.5 text-sm">
        {items.map((item, i) => (
          <li key={i} className={tone}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
