"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Network,
  Search,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  ZoomIn,
  ZoomOut,
  FileText,
} from "lucide-react";
import {
  memoryApi,
  MemoryError,
  setMemoryKey,
  mergeGraph,
  type MemoryDetail,
  type MemoryGraph,
  type MemoryNode,
  type MemoryKind,
} from "@/lib/memory-api";

const labels: Record<MemoryKind, string> = {
  person: "Люди",
  task: "Задачи",
  project: "Проекты",
  decision: "Решения",
  deadline: "Сроки",
  document: "Документы",
  meeting: "Встречи",
};
const statusLabels: Record<string, string> = {
  NEW: "Новая",
  IN_PROGRESS: "В работе",
  OVERDUE: "Просрочена",
  COMPLETED: "Выполнена",
  CANCELLED: "Отменена",
};
const empty: MemoryGraph = {
  nodes: [],
  edges: [],
  total_meetings: 0,
  next_offset: null,
};
function title(node: Pick<MemoryNode, "kind" | "label">) {
  return node.kind === "deadline"
    ? new Date(node.label).toLocaleDateString("ru-RU")
    : node.label;
}
function time(value: number | null) {
  return value === null
    ? ""
    : `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
}

export function CorporateMemory({
  openMeeting,
}: {
  openMeeting: (id: string) => void;
}) {
  const [data, setData] = useState<MemoryGraph>(empty),
    [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(""),
    [detailError, setDetailError] = useState(""),
    [locked, setLocked] = useState(false);
  const [query, setQuery] = useState(""),
    [kind, setKind] = useState("all"),
    [results, setResults] = useState<MemoryNode[] | null>(null),
    [searching, setSearching] = useState(false),
    [moreResults, setMoreResults] = useState(false);
  const [neighborPage, setNeighborPage] = useState(0),
    [zoom, setZoom] = useState(0.9),
    [downloading, setDownloading] = useState(false);
  const sequence = useRef(0),
    searchSequence = useRef(0),
    graphSequence = useRef(0);
  const select = useCallback(async (id: string) => {
    const request = ++sequence.current;
    setSelected(id);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    setNeighborPage(0);
    try {
      const next = await memoryApi<MemoryDetail>(
        `/object?id=${encodeURIComponent(id)}`,
      );
      if (request !== sequence.current) return;
      setDetail(next);
      if (next.neighborhood)
        setData((previous) => ({
          ...previous,
          ...mergeGraph(previous, next.neighborhood!),
        }));
    } catch (e) {
      if (request === sequence.current) {
        setDetailError((e as Error).message);
        if (e instanceof MemoryError && e.status === 401) setLocked(true);
      }
    } finally {
      if (request === sequence.current) setDetailLoading(false);
    }
  }, []);
  const load = useCallback(
    async (offset = 0) => {
      const request = ++graphSequence.current;
      setLoading(true);
      setError("");
      try {
        const next = await memoryApi<MemoryGraph>(`/graph?offset=${offset}`);
        if (request !== graphSequence.current) return;
        setLocked(false);
        setData((previous) =>
          offset ? { ...next, ...mergeGraph(previous, next) } : next,
        );
        if (!offset) {
          const first = next.nodes.find((n) => n.kind === "meeting");
          if (first) void select(first.id);
          else {
            sequence.current++;
            setDetailLoading(false);
            setSelected(null);
            setDetail(null);
          }
        }
      } catch (e) {
        if (request === graphSequence.current) {
          setError((e as Error).message);
          if (e instanceof MemoryError && e.status === 401) {
            setLocked(true);
            setData(empty);
            setDetail(null);
          }
        }
      } finally {
        if (request === graphSequence.current) setLoading(false);
      }
    },
    [select],
  );
  useEffect(() => {
    void load();
    return () => {
      sequence.current++;
      graphSequence.current++;
      searchSequence.current++;
    };
  }, [load]);
  useEffect(() => {
    const request = ++searchSequence.current;
    if (query.trim().length < 2) {
      setResults(null);
      setMoreResults(false);
      setSearching(false);
      return;
    }
    // A failed request must not leave matches from a different query visible.
    setResults(null);
    setMoreResults(false);
    setSearching(true);
    const timer = setTimeout(() => {
      void memoryApi<{ nodes: MemoryNode[]; more: boolean }>(
        `/search?q=${encodeURIComponent(query.trim())}`,
      )
        .then((next) => {
          if (request === searchSequence.current) {
            setResults(next.nodes);
            setMoreResults(next.more);
          }
        })
        .catch((e) => {
          if (request === searchSequence.current) {
            setResults([]);
            setMoreResults(false);
            setError((e as Error).message);
          }
        })
        .finally(() => {
          if (request === searchSequence.current) setSearching(false);
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);
  const byId = useMemo(
    () => new Map(data.nodes.map((n) => [n.id, n])),
    [data.nodes],
  );
  const center = selected
    ? byId.get(selected) ||
      (detail
        ? {
            id: detail.id,
            kind: detail.kind,
            label: detail.label,
            meeting_ids: detail.meetings.map((m) => m.id),
          }
        : null)
    : null;
  const adjacent = useMemo(() => {
    if (!selected) return [];
    const map = new Map<
      string,
      { node: MemoryNode; edge: MemoryGraph["edges"][number] }
    >();
    for (const edge of data.edges) {
      const id =
        edge.source === selected
          ? edge.target
          : edge.target === selected
            ? edge.source
            : null;
      const node = id ? byId.get(id) : null;
      if (node && !map.has(node.id)) map.set(node.id, { node, edge });
    }
    return [...map.values()];
  }, [selected, data.edges, byId]);
  const visible = adjacent.slice(neighborPage * 8, neighborPage * 8 + 8);
  const catalog = (results || data.nodes).filter(
    (n) => kind === "all" || n.kind === kind,
  );
  async function moreDiscussion() {
    if (!detail || detail.next_offset === null) return;
    const identity = detail.id;
    const request = sequence.current;
    setDetailLoading(true);
    try {
      const next = await memoryApi<MemoryDetail>(
        `/object?id=${encodeURIComponent(identity)}&offset=${detail.next_offset}`,
      );
      setDetail((old) =>
        old?.id === identity
          ? {
              ...old,
              discussions: [...old.discussions, ...next.discussions],
              next_offset: next.next_offset,
            }
          : old,
      );
    } catch (e) {
      if (request === sequence.current) setDetailError((e as Error).message);
    } finally {
      if (request === sequence.current) setDetailLoading(false);
    }
  }
  async function download(format: "pdf" | "docx") {
    if (!detail?.protocol) return;
    setDownloading(true);
    setDetailError("");
    try {
      const blob = await memoryApi<Blob>(
        `/protocol/${detail.meetings[0].id}/${format}`,
      );
      const url = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = url;
      a.download = `protocol.${format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }
  if (locked)
    return (
      <section className="memory-lock">
        <Network size={32} />
        <h1>Память команды</h1>
        <p>
          Общая карта содержит обсуждения всех встреч. Введите ключ команды.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const values = new FormData(e.currentTarget);
            try {
              setMemoryKey(String(values.get("key") || ""));
              void load();
            } catch {
              setError("Разрешите хранение данных для этой вкладки.");
            }
          }}
        >
          <label>
            Ключ карты
            <input type="password" name="key" autoComplete="off" required />
          </label>
          <button className="primary" disabled={loading}>
            Открыть карту
          </button>
        </form>
        {error && <p role="alert">{error}</p>}
      </section>
    );
  return (
    <section className="corporate-memory" aria-labelledby="memory-title">
      <header className="memory-heading">
        <div>
          <h1 id="memory-title">Память команды</h1>
          <p>
            Corporate Memory Graph · От решения — к людям, документам и
            следующему разговору.
          </p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => void load()}
        >
          <RefreshCw size={16} />
          Обновить
        </button>
      </header>
      <p className="memory-access">
        Общая карта команды: обсуждения всех встреч. Связи ИИ подтверждаются
        цитатами.
      </p>
      {!!data.unindexed_meetings && (
        <p className="memory-note" role="status">
          Ещё {data.unindexed_meetings} встреч ожидают извлечения проектов и
          документов. Обработка идёт в фоне через Ollama.
          {data.indexing_errors
            ? " Есть ошибки: проверьте ИИ-сервис. Повтор выполняется через пять минут."
            : ""}{" "}
          Нажмите «Обновить», чтобы увидеть новые связи.
        </p>
      )}
      {error && (
        <div className="live-error" role="alert">
          {error}
        </div>
      )}
      <div className="memory-search">
        <Search size={18} />
        <label className="sr-only" htmlFor="memory-search">
          Найти объект во всей истории
        </label>
        <input
          id="memory-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Человек, задача, название проекта или документа…"
        />
        <span role="status">
          {searching ? "Ищем…" : `${data.total_meetings} встреч`}
        </span>
      </div>
      <div className="memory-filters" aria-label="Тип объекта">
        <button aria-pressed={kind === "all"} onClick={() => setKind("all")}>
          Все объекты
        </button>
        {Object.entries(labels).map(([id, label]) => (
          <button
            key={id}
            aria-pressed={kind === id}
            onClick={() => setKind(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && !data.nodes.length ? (
        <p role="status">Собираем связи из сохранённых данных…</p>
      ) : !data.nodes.length && !results ? (
        <div className="memory-empty">
          <Network size={38} />
          <h2>Карта начинается с первого разговора</h2>
          <p>
            Создайте встречу и включите запись. После анализа ИИ добавит
            названные проекты и документы, а задачи и сроки свяжутся с
            участниками.
          </p>
        </div>
      ) : (
        <>
          <div className="memory-workspace">
            <aside className="memory-catalog" aria-label="Объекты карты">
              <h2>
                {results ? "Результаты поиска" : "Объекты карты"}{" "}
                <span>{catalog.length}</span>
              </h2>
              {catalog.map((node) => (
                <button
                  key={node.id}
                  aria-pressed={selected === node.id}
                  onClick={() => void select(node.id)}
                >
                  <span className={`memory-dot ${node.kind}`} />
                  <span>
                    <small>{labels[node.kind]}</small>
                    <strong>{title(node)}</strong>
                  </span>
                </button>
              ))}
              {!catalog.length && (
                <p>Объекты не найдены. Попробуйте другое название.</p>
              )}
              {moreResults && <p>Найдено больше объектов. Уточните запрос.</p>}
              {data.next_offset !== null && (
                <button
                  className="secondary"
                  disabled={loading}
                  onClick={() => void load(data.next_offset!)}
                >
                  {loading ? "Загружаем…" : "Загрузить более ранние встречи"}
                </button>
              )}
            </aside>
            <div className="memory-explorer">
              <div className="memory-map-toolbar">
                <span>Выберите объект — карта покажет его связи</span>
                <div>
                  <button
                    aria-label="Уменьшить карту"
                    disabled={zoom <= 0.5}
                    onClick={() => setZoom((z) => Math.max(0.5, z - 0.1))}
                  >
                    <ZoomOut size={18} />
                  </button>
                  <button
                    aria-label="Увеличить карту"
                    disabled={zoom >= 1.3}
                    onClick={() => setZoom((z) => Math.min(1.3, z + 0.1))}
                  >
                    <ZoomIn size={18} />
                  </button>
                </div>
              </div>
              <div
                className="memory-map-scroll"
                ref={(element) => {
                  if (element)
                    element.scrollLeft = Math.max(
                      0,
                      (960 * zoom - element.clientWidth) / 2,
                    );
                }}
                tabIndex={0}
                aria-label="Карта связей, прокручивается по горизонтали"
              >
                <div style={{ width: 960 * zoom, height: 570 * zoom }}>
                  <div
                    className="memory-map"
                    style={{ transform: `scale(${zoom})` }}
                  >
                    <svg width="960" height="570" aria-hidden="true">
                      <defs>
                        <marker
                          id="memory-arrow"
                          markerWidth="8"
                          markerHeight="8"
                          refX="7"
                          refY="4"
                          orient="auto"
                        >
                          <path d="M0,0 L8,4 L0,8" fill="#a0a9b7" />
                        </marker>
                      </defs>
                      {visible.map(({ node, edge }, index) => {
                        const angle =
                          (index * 2 * Math.PI) / Math.max(visible.length, 1) -
                          Math.PI / 2;
                        const x = 480 + 330 * Math.cos(angle),
                          y = 285 + 220 * Math.sin(angle);
                        const from = edge.source === selected;
                        const dx = x - 480,
                          dy = y - 285;
                        const inset = Math.min(
                          99 / Math.max(Math.abs(dx), 0.001),
                          39 / Math.max(Math.abs(dy), 0.001),
                        );
                        const a = `${480 + dx * inset},${285 + dy * inset}`;
                        const b = `${x - dx * inset},${y - dy * inset}`;
                        return (
                          <path
                            key={node.id}
                            d={from ? `M${a} L${b}` : `M${b} L${a}`}
                            stroke="#cdd2dc"
                            strokeWidth="1.5"
                            strokeDasharray={
                              edge.relation === "same_discussion"
                                ? "5 5"
                                : undefined
                            }
                            markerEnd="url(#memory-arrow)"
                          />
                        );
                      })}
                    </svg>
                    {center && (
                      <div
                        className={`memory-map-node center ${center.kind}`}
                        style={{ left: 385, top: 250 }}
                      >
                        <small>{labels[center.kind]}</small>
                        <strong title={center.label}>{title(center)}</strong>
                      </div>
                    )}
                    {visible.map(({ node }, index) => {
                      const angle =
                        (index * 2 * Math.PI) / Math.max(visible.length, 1) -
                        Math.PI / 2;
                      return (
                        <button
                          className={`memory-map-node ${node.kind}`}
                          key={node.id}
                          style={{
                            left: 480 + 330 * Math.cos(angle) - 95,
                            top: 285 + 220 * Math.sin(angle) - 35,
                          }}
                          onClick={() => void select(node.id)}
                          title={title(node)}
                        >
                          <small>{labels[node.kind]}</small>
                          <strong>{title(node)}</strong>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
              <div className="memory-map-footer">
                <span>
                  {adjacent.length} связей · пунктир означает общую реплику, а
                  не зависимость
                </span>
                {adjacent.length > 8 && (
                  <div>
                    <button
                      aria-label="Предыдущие связи"
                      disabled={!neighborPage}
                      onClick={() => setNeighborPage((p) => p - 1)}
                    >
                      <ArrowLeft size={18} />
                    </button>
                    <span>
                      {neighborPage + 1} / {Math.ceil(adjacent.length / 8)}
                    </span>
                    <button
                      aria-label="Следующие связи"
                      disabled={(neighborPage + 1) * 8 >= adjacent.length}
                      onClick={() => setNeighborPage((p) => p + 1)}
                    >
                      <ArrowRight size={18} />
                    </button>
                  </div>
                )}
              </div>
              <section
                className="memory-detail"
                aria-live="polite"
                aria-busy={detailLoading}
              >
                {detailLoading && !detail && (
                  <p role="status">Загружаем обсуждения…</p>
                )}
                {detailError && (
                  <p className="live-error" role="alert">
                    {detailError}
                  </p>
                )}
                {detail && (
                  <>
                    <header>
                      <small>{labels[detail.kind]}</small>
                      <h2>{title(detail)}</h2>
                    </header>
                    {detail.kind === "person" && (
                      <p className="memory-note">
                        Это профиль участника конкретной встречи. Люди с
                        одинаковым именем не объединяются автоматически.
                      </p>
                    )}
                    {(detail.kind === "project" ||
                      (detail.kind === "document" && !detail.protocol)) && (
                      <p className="memory-note">
                        Упоминания объединены по точному названию.{" "}
                        {detail.kind === "document"
                          ? "Упоминание не означает, что файл загружен в систему."
                          : "Разные названия не склеиваются по догадке модели."}
                      </p>
                    )}
                    {detail.legacy && (
                      <p className="memory-note">
                        Решение сохранено до появления карты. Точная цитата не
                        сохранена — ниже расшифровка встречи.
                      </p>
                    )}
                    {detail.task && (
                      <p className="memory-task-state">
                        {statusLabels[detail.task.status] || detail.task.status}{" "}
                        · {detail.task.responsible || "Ответственный не указан"}
                        {detail.task.deadline
                          ? ` · срок ${new Date(detail.task.deadline).toLocaleDateString("ru-RU")}`
                          : ""}
                      </p>
                    )}
                    {detail.protocol && (
                      <div className="live-inline-actions">
                        <button
                          className="secondary"
                          disabled={downloading}
                          onClick={() => void download("pdf")}
                        >
                          <FileText size={16} />
                          PDF
                        </button>
                        <button
                          className="secondary"
                          disabled={downloading}
                          onClick={() => void download("docx")}
                        >
                          DOCX
                        </button>
                      </div>
                    )}
                    {!!adjacent.length && (
                      <details className="memory-relations">
                        <summary>Все связи объекта ({adjacent.length})</summary>
                        <ul>
                          {adjacent.map(({ node, edge }) => (
                            <li key={node.id}>
                              <span>{edge.label}</span>
                              <button
                                className="text-link"
                                onClick={() => void select(node.id)}
                              >
                                {title(node)}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                    {detail.neighborhood_partial && (
                      <p className="memory-note">
                        На карте связи из последних 60 связанных встреч. Список
                        обсуждений ниже доступен полностью, по страницам.
                      </p>
                    )}
                    {!!detail.same_names.length && (
                      <details className="memory-relations">
                        <summary>
                          Одноимённые участники других встреч (
                          {detail.same_names.length})
                        </summary>
                        <p>
                          Это возможные совпадения, а не подтверждённая
                          личность.
                        </p>
                        <ul>
                          {detail.same_names.map((p) => (
                            <li key={p.id}>
                              <button
                                className="text-link"
                                onClick={() => void select(p.id)}
                              >
                                {p.label} · {p.meeting_id.slice(0, 8)}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                    <h3>
                      Связанные встречи <span>{detail.meetings.length}</span>
                    </h3>
                    <div className="memory-meetings">
                      {detail.meetings.map((m) => (
                        <div key={m.id}>
                          <button
                            className="text-link"
                            onClick={() => void select(`meeting:${m.id}`)}
                          >
                            {m.title}
                          </button>
                          <time>
                            {new Date(m.date).toLocaleString("ru-RU")}
                          </time>
                          <button
                            className="text-link"
                            onClick={() => openMeeting(m.id)}
                          >
                            Открыть комнату
                          </button>
                        </div>
                      ))}
                    </div>
                    <h3>
                      Обсуждения <span>{detail.total}</span>
                    </h3>
                    {!detail.discussions.length && (
                      <p>
                        Сохранённых реплик пока нет. Они появятся после записи и
                        распознавания.
                      </p>
                    )}
                    <ol className="memory-discussions">
                      {detail.discussions.map((d) => (
                        <li key={d.id}>
                          <div>
                            <span>
                              {
                                detail.meetings.find(
                                  (m) => m.id === d.meeting_id,
                                )?.title
                              }
                            </span>
                            <span>
                              {time(d.start)} · {d.source}
                            </span>
                          </div>
                          <blockquote>{d.quote}</blockquote>
                          {!d.active && (
                            <p className="memory-note">
                              Архив: не подтверждено последним анализом.
                            </p>
                          )}
                          {d.source_matches === false && (
                            <p className="memory-note">
                              Исходная расшифровка изменилась; показана
                              сохранённая цитата предыдущего анализа.
                            </p>
                          )}
                          {d.url && /^https?:\/\//i.test(d.url) && (
                            <a
                              href={d.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Открыть упомянутую ссылку
                            </a>
                          )}
                        </li>
                      ))}
                    </ol>
                    {detail.next_offset !== null && (
                      <button
                        className="secondary"
                        disabled={detailLoading}
                        onClick={() => void moreDiscussion()}
                      >
                        {detailLoading
                          ? "Загружаем…"
                          : "Показать ещё обсуждения"}
                      </button>
                    )}
                  </>
                )}
              </section>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
