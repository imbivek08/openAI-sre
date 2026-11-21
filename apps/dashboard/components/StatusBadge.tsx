export function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    open: "bg-yellow-950 text-yellow-300",
    investigating: "bg-blue-950 text-blue-300",
    completed: "bg-green-950 text-green-300",
    failed: "bg-red-950 text-red-300",
    queued: "bg-neutral-800 text-neutral-300",
    running: "bg-blue-950 text-blue-300",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${colors[status] ?? "bg-neutral-800 text-neutral-300"}`}>
      {status}
    </span>
  );
}
