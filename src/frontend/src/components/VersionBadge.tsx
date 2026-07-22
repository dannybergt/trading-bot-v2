import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api/client";

type VersionInfo = { version?: string; commit?: string; builtAt?: string };

/**
 * Shows the running backend build (version + short commit) so operators can
 * confirm which deploy is live. Reads the public /api/version endpoint; renders
 * nothing until it resolves or if the build metadata is a placeholder.
 */
export function VersionBadge({ className }: { className?: string }) {
  const { data } = useQuery({
    queryKey: ["version"],
    queryFn: () => apiFetch<VersionInfo>("/api/version", { skipAuth: true }),
    staleTime: Infinity,
    retry: false,
  });
  if (!data?.version) return null;
  const commit =
    data.commit && data.commit !== "unknown" ? data.commit.slice(0, 7) : null;
  return (
    <span className={className ?? "text-[10px] text-slate-600"} title={data.builtAt}>
      v{data.version}
      {commit ? ` · ${commit}` : ""}
    </span>
  );
}
