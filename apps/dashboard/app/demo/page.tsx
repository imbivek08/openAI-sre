"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type DemoStatus } from "@/lib/api";

const ADMIN_KEY = process.env.NEXT_PUBLIC_DEMO_ADMIN_KEY ?? "";

export default function DemoLabPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [investigating, setInvestigating] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await api.demoStatus());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load demo status");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function trigger(scenario: string) {
    setBusy(scenario);
    setError("");
    try {
      await api.triggerScenario(scenario, ADMIN_KEY);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trigger failed");
    } finally {
      setBusy("");
    }
  }

  async function reset() {
    setBusy("reset");
    setError("");
    try {
      await api.resetDemo(ADMIN_KEY);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy("");
    }
  }

  async function startInvestigation() {
    setInvestigating(true);
    setError("");
    try {
      const incident = await api.createIncident({
        source: "runtime",
        title: "Demo runtime investigation",
        summary: "Investigation started from the demo lab",
        service: "demo-api",
      });
      await api.investigate(incident.id);
      window.location.href = `/incidents/${incident.id}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start investigation");
      setInvestigating(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Runtime Incident Lab</h1>
      <p className="text-sm text-neutral-400">
        Trigger controlled faults against the demo service, observe real logs and metrics, then run an
        AI investigation. All actions call the real backend.
      </p>

      {error && <div className="rounded bg-red-950 px-4 py-2 text-sm text-red-300">{error}</div>}

      <div className="grid gap-4 md:grid-cols-3">
        {status &&
          Object.entries(status.scenarios).map(([id, scenario]) => (
            <div key={id} className="rounded border border-neutral-800 bg-neutral-900 p-4">
              <h3 className="font-semibold">{scenario.title}</h3>
              <p className="mt-1 text-xs text-neutral-400">{scenario.description}</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => trigger(id)}
                  disabled={!!busy || (status.active_faults ?? []).includes(id)}
                  className="rounded bg-red-900 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-800 disabled:opacity-40"
                >
                  {busy === id ? "Triggering…" : (status.active_faults ?? []).includes(id) ? "Active" : "Trigger"}
                </button>
              </div>
            </div>
          ))}
      </div>

      <div className="flex items-center gap-4 rounded border border-neutral-800 bg-neutral-900 p-4">
        <button
          onClick={reset}
          disabled={!!busy}
          className="rounded bg-neutral-700 px-4 py-2 text-sm font-medium hover:bg-neutral-600 disabled:opacity-40"
        >
          {busy === "reset" ? "Resetting…" : "Reset Lab"}
        </button>
        <button
          onClick={startInvestigation}
          disabled={investigating}
          className="rounded bg-blue-700 px-4 py-2 text-sm font-medium hover:bg-blue-600 disabled:opacity-40"
        >
          {investigating ? "Starting…" : "Start Investigation"}
        </button>
        <span className="text-xs text-neutral-400">
          Active faults: {status ? (status.active_faults ?? []).join(", ") || "none" : "…"}
        </span>
      </div>

      {status && (
        <div className="rounded border border-neutral-800 bg-neutral-900 p-4 text-sm">
          <h3 className="mb-2 font-semibold">Service Health</h3>
          <pre className="overflow-auto text-xs text-neutral-300">
            {JSON.stringify(status.health ?? { status: "unknown" }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
