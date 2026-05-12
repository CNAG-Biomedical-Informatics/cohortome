import { useQuery } from "@tanstack/react-query";
import type { PhenoFile } from "../../api/types";

export function PhenoTextPreview({ file, maxLines = 40 }: { file: PhenoFile; maxLines?: number }) {
  const query = useQuery({
    queryKey: ["pheno-file", file.url],
    queryFn: async () => {
      const response = await fetch(file.url, { credentials: "same-origin" });
      if (!response.ok) throw new Error("Unable to load output preview.");
      return response.text();
    },
  });

  if (query.isLoading) return <div className="empty">Loading preview...</div>;
  if (query.error) return <div className="empty">{(query.error as Error).message}</div>;

  const text = query.data || "";
  const preview = text.split(/\r?\n/).slice(0, maxLines).join("\n");
  return <pre>{preview || "File is empty."}</pre>;
}
