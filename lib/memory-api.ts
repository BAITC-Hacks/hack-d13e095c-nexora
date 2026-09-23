export type MemoryKind =
  | "person"
  | "task"
  | "project"
  | "decision"
  | "deadline"
  | "document"
  | "meeting";
export type MemoryNode = {
  id: string;
  kind: MemoryKind;
  label: string;
  meeting_ids: string[];
  date?: string;
  status?: string;
  protocol?: boolean;
  legacy?: boolean;
};
export type MemoryEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  label: string;
  meeting_ids: string[];
};
export type MemoryGraph = {
  nodes: MemoryNode[];
  edges: MemoryEdge[];
  total_meetings: number;
  unindexed_meetings?: number;
  indexing_errors?: number;
  next_offset: number | null;
};
export type MemoryDetail = {
  id: string;
  kind: MemoryKind;
  label: string;
  meetings: { id: string; title: string; date: string }[];
  same_names: { id: string; label: string; meeting_id: string }[];
  protocol: boolean;
  legacy: boolean;
  task: {
    id: string;
    status: string;
    responsible: string | null;
    deadline: string | null;
  } | null;
  discussions: {
    id: string;
    meeting_id: string;
    quote: string;
    start: number | null;
    source: string;
    active: boolean;
    source_matches?: boolean;
    url?: string | null;
  }[];
  total: number;
  next_offset: number | null;
  neighborhood?: { nodes: MemoryNode[]; edges: MemoryEdge[] };
  neighborhood_partial?: boolean;
};
const KEY = "protocol-memory-team-key";
export function setMemoryKey(key: string) {
  sessionStorage.setItem(KEY, key);
}
export class MemoryError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function memoryApi<T>(path: string): Promise<T> {
  let key = "";
  try {
    key = sessionStorage.getItem(KEY) || "";
  } catch {}
  let response: Response;
  try {
    response = await fetch(`/api/v1/conferences/memory${path}`, {
      headers: { "X-Memory-Key": key },
      cache: "no-store",
    });
  } catch {
    throw new MemoryError(0, "Нет связи с сервером. Проверьте Docker и сеть.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    throw new MemoryError(
      response.status,
      typeof body?.detail === "string"
        ? body.detail
        : "Не удалось загрузить карту. Повторите запрос.",
    );
  }
  return response.headers.get("Content-Type")?.includes("application/json")
    ? response.json()
    : ((await response.blob()) as T);
}
export function mergeGraph(
  before: Pick<MemoryGraph, "nodes" | "edges">,
  after: Pick<MemoryGraph, "nodes" | "edges">,
) {
  function merge<T extends { id: string; meeting_ids: string[] }>(
    a: T[],
    b: T[],
  ) {
    const map = new Map(a.map((x) => [x.id, x]));
    for (const x of b) {
      const old = map.get(x.id);
      map.set(x.id, {
        ...old,
        ...x,
        meeting_ids: [
          ...new Set([...(old?.meeting_ids || []), ...x.meeting_ids]),
        ],
      });
    }
    return [...map.values()];
  }
  return {
    nodes: merge(before.nodes, after.nodes),
    edges: merge(before.edges, after.edges),
  };
}
