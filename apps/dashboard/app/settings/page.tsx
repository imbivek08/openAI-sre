"use client";

import { useEffect, useState } from "react";
import { api, type HealthResponse } from "@/lib/api";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load health"));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings & Integration Status</h1>
      <p className="text-sm text-neutral-400">
        Provider and integration status. Sensitive values (API keys, webhook secrets) are never shown.
      </p>

      {error && <div className="rounded bg-red-950 px-4 py-2 text-sm text-red-300">{error}</div>}

      {health && (
        <div className="space-y-4">
          <section className="rounded border border-neutral-800 bg-neutral-900 p-4">
            <h2 className="mb-3 font-semibold">Dependencies</h2>
            <ul className="space-y-2 text-sm">
              {health.dependencies.map((dep) => (
                <li key={dep.name} className="flex items-center gap-3">
                  <span
                    className={`inline-block h-2.5 w-2.5 rounded-full ${
                      dep.status === "up" ? "bg-green-500" : dep.status === "down" ? "bg-red-500" : "bg-yellow-500"
                    }`}
                  />
                  <span className="font-medium">{dep.name}</span>
                  <span className="text-neutral-500">{dep.status}</span>
                  {dep.detail && <span className="text-xs text-neutral-500">{dep.detail}</span>}
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded border border-neutral-800 bg-neutral-900 p-4">
            <h2 className="mb-3 font-semibold">AI Model Provider</h2>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="text-neutral-400">Provider:</dt>
                <dd>{health.llm.provider}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-neutral-400">Model:</dt>
                <dd>{health.llm.model}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-neutral-400">Base URL:</dt>
                <dd>{health.llm.base_url}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-neutral-400">Tool calling:</dt>
                <dd>{health.llm.tool_calling ? "enabled" : "disabled"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-neutral-400">Configured:</dt>
                <dd>{health.llm.configured ? "yes" : "no"}</dd>
              </div>
            </dl>
            {!health.llm.configured && (
              <p className="mt-3 rounded bg-yellow-950 px-3 py-2 text-xs text-yellow-200">
                No LLM provider configured. Set LLM_PROVIDER, LLM_BASE_URL, and LLM_MODEL in the backend
                environment. Infrastructure and webhook features remain available without a model.
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
