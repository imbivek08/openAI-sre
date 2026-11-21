"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api, type Incident, type Paginated } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function OverviewPage() {
  const [data, setData] = useState<Paginated<Incident> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.listIncidents({
        source: sourceFilter || undefined,
        status: statusFilter || undefined,
        page: 1,
        page_size: 25,
      });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, [sourceFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = data
    ? {
        total: data.total,
        open: data.items.filter((i) => i.status === "open").length,
        investigating: data.items.filter((i) => i.status === "investigating").length,
        completed: data.items.filter((i) => i.status === "completed").length,
        failed: data.items.filter((i) => i.status === "failed").length,
      }
    : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Incident Overview</h1>

      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <StatCard label="Total" value={stats.total} />
          <StatCard label="Open" value={stats.open} color="text-yellow-400" />
          <StatCard label="Investigating" value={stats.investigating} color="text-blue-400" />
          <StatCard label="Completed" value={stats.completed} color="text-green-400" />
          <StatCard label="Failed" value={stats.failed} color="text-red-400" />
        </div>
      )}

      <div className="flex gap-3">
        <select
          className="rounded border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
        >
          <option value="">All sources</option>
          <option value="runtime">Runtime</option>
          <option value="github_actions">GitHub Actions</option>
          <option value="manual">Manual</option>
        </select>
        <select
          className="rounded border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {error && <div className="rounded bg-red-950 px-4 py-2 text-sm text-red-300">{error}</div>}
      {loading && <div className="text-neutral-400">Loading…</div>}

      {data && data.items.length === 0 && !loading && (
        <div className="rounded border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
          No incidents yet. Trigger a demo scenario or wait for a webhook.
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-hidden rounded border border-neutral-800">
          <table className="w-full text-sm">
            <thead className="bg-neutral-900 text-left text-neutral-400">
              <tr>
                <th className="px-4 py-2">Title</th>
                <th className="px-4 py-2">Source</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Severity</th>
                <th className="px-4 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((incident) => (
                <tr key={incident.id} className="border-t border-neutral-800 hover:bg-neutral-900">
                  <td className="px-4 py-2">
                    <Link href={`/incidents/${incident.id}`} className="text-blue-400 hover:underline">
                      {incident.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-neutral-400">{incident.source}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={incident.status} />
                  </td>
                  <td className="px-4 py-2 text-neutral-400">{incident.severity}</td>
                  <td className="px-4 py-2 text-neutral-500">
                    {incident.created_at ? new Date(incident.created_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color = "text-white" }: { label: string; value: number; color?: string }) {
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 p-4">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-neutral-400">{label}</div>
    </div>
  );
}
