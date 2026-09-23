"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  LayoutDashboard,
  ListChecks,
  FileText,
  AudioLines,
  Plus,
  Bell,
  ChevronRight,
  Search,
  RotateCcw,
  ShieldCheck,
  AlertCircle,
  type WorkspaceIcon as LucideIcon,
} from "./icons";
import {
  Sidebar,
  SidebarProvider,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import {
  AssignmentTable,
  Badge,
  Choice,
  Empty,
  dateText,
  countLabel,
} from "./widgets";
import { CreateMeeting } from "./create-meeting";
import { HomeOverview } from "./home-overview";
import { MeetingDetail } from "./meeting-detail";
import { seedState, resetDemo } from "@/lib/seed";
import { loadState, saveState } from "@/lib/storage";
import { approveMeeting, dueSoon, statusOf, statusLabels } from "@/lib/domain";
import type { AppState, AssignmentStatus, Meeting } from "@/lib/types";
type View =
  "overview" | "meetings" | "protocols" | "assignments" | "notifications";
const navigation: [View, LucideIcon, string][] = [
  ["overview", LayoutDashboard, "Главная"],
  ["meetings", CalendarDays, "Совещания"],
  ["assignments", ListChecks, "Поручения"],
  ["protocols", FileText, "Протоколы"],
  ["notifications", Bell, "Уведомления"],
];
function NavButton({
  Icon,
  label,
  active,
  count,
  onClick,
}: {
  Icon: LucideIcon;
  label: string;
  active: boolean;
  count?: number;
  onClick: () => void;
}) {
  const { setOpenMobile } = useSidebar();
  return (
    <button
      className={"nav-item " + (active ? "active" : "")}
      aria-current={active ? "page" : undefined}
      onClick={() => {
        onClick();
        setOpenMobile(false);
      }}
    >
      <Icon size={19} />
      {label}
      {!!count && <span className="count">{count}</span>}
    </button>
  );
}
export default function Home() {
  const [data, setData] = useState<AppState | null>(null),
    [view, setView] = useState<View>("overview"),
    [selected, setSelected] = useState<string | null>(null),
    [create, setCreate] = useState(false),
    [busy, setBusy] = useState(false),
    [saving, setSaving] = useState(false),
    [storageError, setStorageError] = useState(""),
    [loadError, setLoadError] = useState(""),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState("all"),
    [owner, setOwner] = useState("all"),
    [meetingStatus, setMeetingStatus] = useState("all"),
    [, tick] = useState(0);
  const current = useRef<AppState | null>(null),
    queue = useRef(Promise.resolve()),
    revision = useRef(0),
    initializing = useRef(false);
  const init = useCallback(async () => {
    if (initializing.current) return;
    initializing.current = true;
    setLoadError("");
    try {
      const stored = await loadState();
      if (stored && stored.version !== 1)
        throw new Error("Версия локальных данных не поддерживается.");
      const state = stored || seedState();
      if (!stored) await saveState(state);
      current.current = state;
      setData(state);
    } catch {
      setLoadError(
        "Не удалось открыть локальную базу. Разрешите хранение данных для сайта и повторите.",
      );
    } finally {
      initializing.current = false;
    }
  }, []);
  useEffect(() => {
    void init();
    const timer = setInterval(() => tick((x) => x + 1), 60000);
    return () => clearInterval(timer);
  }, [init]);
  const persist = useCallback((next: AppState) => {
    const r = ++revision.current;
    setSaving(true);
    const task = queue.current.catch(() => {}).then(() => saveState(next));
    queue.current = task;
    task
      .then(() => {
        if (r === revision.current) {
          setSaving(false);
          setStorageError("");
        }
      })
      .catch(() => {
        if (r === revision.current) {
          setSaving(false);
          setStorageError(
            "Изменения не сохранены. Проверьте свободное место или настройки браузера.",
          );
        }
      });
    return task;
  }, []);
  const commit = useCallback(
    (update: (s: AppState) => AppState) => {
      if (!current.current)
        return Promise.reject(new Error("Данные ещё загружаются"));
      const next = update(current.current);
      current.current = next;
      setData(next);
      return persist(next);
    },
    [persist],
  );
  function changeMeeting(m: Meeting) {
    void commit((s) => ({
      ...s,
      meetings: s.meetings.map((x) => (x.id === m.id ? m : x)),
    })).catch(() => {});
  }
  function navigate(next: View, id: string | null = null) {
    if (busy) {
      toast.info("Сначала остановите запись или дождитесь обработки.");
      return;
    }
    setView(next);
    setSelected(id);
    setQuery("");
    setStatus("all");
    setOwner("all");
    setMeetingStatus("all");
  }
  function openMeeting(id: string) {
    navigate("meetings", id);
  }
  function changeStatus(id: string, status: AssignmentStatus) {
    void commit((s) => ({
      ...s,
      assignments: s.assignments.map((a) =>
        a.id === id ? { ...a, status } : a,
      ),
    }))
      .then(() => toast.success("Статус обновлён"))
      .catch(() => {});
  }
  useEffect(() => {
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: unknown,
            options: unknown,
          ) => Promise<void> | void;
        };
      }
    ).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(
        context.registerTool(
          {
            name: "list_meeting_assignments",
            description:
              "Read the current assignments and their computed execution statuses. Does not modify data.",
            inputSchema: {
              type: "object",
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            execute: (input: unknown) => {
              if (
                !input ||
                typeof input !== "object" ||
                Array.isArray(input) ||
                Object.keys(input).length
              )
                throw new Error("Expected an empty object");
              if (!current.current) throw new Error("Workspace is loading");
              return {
                assignments: current.current.assignments.map((a) => ({
                  ...a,
                  status: statusOf(a),
                })),
              };
            },
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {});
    } catch {}
    return () => lifecycle.abort();
  }, []);
  if (!data)
    return (
      <main className="loading-page">
        <span className="brand-icon">
          <AudioLines />
        </span>
        <h1>Протокол</h1>
        <p>{loadError || "Открываем рабочее пространство…"}</p>
        {loadError && (
          <button className="primary" onClick={() => void init()}>
            Повторить
          </button>
        )}
      </main>
    );
  const notices = data.assignments
    .filter((a) => dueSoon(a))
    .sort((a, b) => a.deadline.localeCompare(b.deadline));
  const selectedMeeting = data.meetings.find((m) => m.id === selected);
  const title = navigation.find((n) => n[0] === view)![2];
  const meetingList = data.meetings
    .filter(
      (m) =>
        (view !== "protocols" || m.protocol) &&
        m.title.toLowerCase().includes(query.toLowerCase()) &&
        (meetingStatus === "all" ||
          (meetingStatus === "review" &&
            m.protocol &&
            !m.protocol.approvedAt) ||
          (meetingStatus === "approved" && m.protocol?.approvedAt) ||
          (meetingStatus === "planned" && !m.protocol)),
    )
    .sort((a, b) => b.date.localeCompare(a.date));
  const assignments = data.assignments.filter(
    (a) =>
      (status === "all" || statusOf(a) === status) &&
      (owner === "all" || a.assignee === owner) &&
      (a.text + " " + a.department).toLowerCase().includes(query.toLowerCase()),
  );
  function meetingRow(m: Meeting) {
    return (
      <button
        key={m.id}
        className="meeting-row"
        onClick={() => openMeeting(m.id)}
      >
        <span className="date-tile">
          {new Date(m.date).getDate()}
          <small>
            {new Date(m.date)
              .toLocaleDateString("ru-RU", { month: "short" })
              .replace(".", "")
              .toUpperCase()}
          </small>
        </span>
        <div>
          <h3>{m.title}</h3>
          <p>
            {new Date(m.date).toLocaleTimeString("ru-RU", {
              hour: "2-digit",
              minute: "2-digit",
            })}
            <span className="meta-dot">·</span>
            {countLabel(m.participants.length, [
              "участник",
              "участника",
              "участников",
            ])}
            <span className="meta-dot">·</span>
            {countLabel(m.agenda.length, ["вопрос", "вопроса", "вопросов"])}
          </p>
        </div>
        <Badge
          status={
            m.protocol?.approvedAt
              ? "approved"
              : m.protocol
                ? "review"
                : "planned"
          }
        />
        <ChevronRight size={17} />
      </button>
    );
  }
  return (
    <SidebarProvider>
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <Sidebar className="no-print">
        <SidebarHeader>
          <div className="brand">
            <span className="brand-icon">
              <AudioLines size={23} />
            </span>
            Протокол
          </div>
          <div className="workspace-label">Встречи. Решения. Дела.</div>
        </SidebarHeader>
        <SidebarContent>
          <div className="nav-caption">Рабочее пространство</div>
          {navigation.map(([id, Icon, label]) => (
            <NavButton
              key={id}
              Icon={Icon}
              label={label}
              active={view === id}
              count={
                id === "notifications"
                  ? notices.length
                  : id === "assignments"
                    ? data.assignments.length
                    : undefined
              }
              onClick={() => navigate(id)}
            />
          ))}
        </SidebarContent>
        <SidebarFooter>
          <div className="demo-note">
            <span className="green-dot" />
            Демонстрационный режим
            <small>Данные хранятся в вашем браузере</small>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button className="reset-button" disabled={busy}>
                <RotateCcw size={14} />
                Восстановить демоданные
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Восстановить демоданные?</AlertDialogTitle>
                <AlertDialogDescription>
                  Изменения и аудиозаписи в демонстрационных совещаниях будут
                  удалены. Созданные вами совещания и их поручения сохранятся.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Отмена</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    void commit(resetDemo)
                      .then(() => toast.success("Демоданные восстановлены"))
                      .catch(() => {});
                    setSelected(null);
                  }}
                >
                  Восстановить
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </SidebarFooter>
      </Sidebar>
      <div className="app-body">
        <header className="topbar no-print">
          <div>
            <SidebarTrigger aria-label="Меню навигации" />
            <span className="breadcrumb-root">Рабочее пространство</span>
            <ChevronRight size={13} />
            <strong>{title}</strong>
          </div>
          <div>
            <span className="header-date">
              {new Date().toLocaleDateString("ru-RU", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </span>
            <button
              className="notification-button"
              aria-label={`Уведомления: ${notices.length}`}
              onClick={() => navigate("notifications")}
            >
              <Bell size={19} />
              {notices.length > 0 && <i />}
            </button>
          </div>
        </header>
        <main className="content" id="main-content" tabIndex={-1}>
          {storageError && (
            <div className="error-note no-print" role="alert">
              {storageError}{" "}
              <button
                className="text-link"
                onClick={() =>
                  current.current &&
                  void persist(current.current).catch(() => {})
                }
              >
                Повторить сохранение
              </button>
            </div>
          )}
          {selectedMeeting ? (
            <MeetingDetail
              key={selectedMeeting.id}
              meeting={selectedMeeting}
              onChange={changeMeeting}
              onBack={() => navigate("meetings")}
              busy={busy}
              onBusy={setBusy}
              onApprove={() => {
                void commit((s) => approveMeeting(s, selectedMeeting.id))
                  .then(() =>
                    toast.success("Протокол утверждён. Поручения созданы."),
                  )
                  .catch(() =>
                    toast.error(
                      "Не удалось сохранить утверждение. Повторите сохранение.",
                    ),
                  );
              }}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    {view === "overview"
                      ? "Ваш рабочий день"
                      : "Рабочее пространство"}
                  </div>
                  <h1>{view === "overview" ? "С возвращением" : title}</h1>
                  <p>
                    {view === "overview"
                      ? "Продолжите встречу или начните новую."
                      : view === "meetings"
                        ? "Встречи, повестки и решения вашей команды."
                        : view === "protocols"
                          ? "Проверьте проекты и утвердите решения совещаний."
                          : view === "assignments"
                            ? "Ответственные, сроки и ход исполнения решений."
                            : "Ближайшие сроки и поручения, требующие внимания."}
                  </p>
                </div>
                {(view === "overview" || view === "meetings") && (
                  <button className="primary" onClick={() => setCreate(true)}>
                    <Plus size={17} />
                    Новое совещание
                  </button>
                )}
              </div>
              {view === "overview" ? (
                <HomeOverview
                  meetings={data.meetings}
                  notices={notices}
                  onMeetings={() => navigate("meetings")}
                  onReview={() => {
                    navigate("protocols");
                    setMeetingStatus("review");
                  }}
                  onTasks={() => navigate("assignments")}
                  onTask={(a) => {
                    navigate("assignments");
                    setQuery(a.text);
                  }}
                  renderMeeting={meetingRow}
                />
              ) : view === "meetings" || view === "protocols" ? (
                <section className="panel">
                  <div className="list-toolbar">
                    <label className="search-box">
                      <Search size={17} />
                      <input
                        aria-label="Поиск совещаний"
                        placeholder="Найти совещание…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <Choice
                      value={meetingStatus}
                      onChange={setMeetingStatus}
                      label="Статус совещания"
                      items={[
                        ["all", "Все статусы"],
                        ["review", "На проверке"],
                        ["approved", "Утверждён"],
                        ...(view === "meetings"
                          ? [["planned", "Запланировано"] as [string, string]]
                          : []),
                      ]}
                    />
                    <span className="list-count">
                      Найдено: {meetingList.length}
                    </span>
                    {(query || meetingStatus !== "all") && (
                      <button
                        className="text-link"
                        onClick={() => {
                          setQuery("");
                          setMeetingStatus("all");
                        }}
                      >
                        Сбросить фильтры
                      </button>
                    )}
                  </div>
                  {meetingList.length ? (
                    meetingList.map(meetingRow)
                  ) : (
                    <Empty
                      title="Совещания не найдены"
                      description="Измените фильтры или создайте новое совещание."
                    />
                  )}
                </section>
              ) : view === "assignments" ? (
                <section className="panel">
                  <div className="list-toolbar">
                    <label className="search-box">
                      <Search size={17} />
                      <input
                        aria-label="Поиск поручений"
                        placeholder="Найти поручение…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <Choice
                      value={status}
                      onChange={setStatus}
                      label="Фильтр статуса"
                      items={[
                        ["all", "Все статусы"],
                        ...Object.entries(statusLabels),
                      ]}
                    />
                    <Choice
                      value={owner}
                      onChange={setOwner}
                      label="Фильтр ответственного"
                      items={[
                        ["all", "Все ответственные"],
                        ...Array.from(
                          new Set(data.assignments.map((a) => a.assignee)),
                        ).map((n) => [n, n] as [string, string]),
                      ]}
                    />
                  </div>
                  <AssignmentTable
                    items={assignments}
                    filtered={
                      query !== "" || status !== "all" || owner !== "all"
                    }
                    onStatus={changeStatus}
                    onMeeting={openMeeting}
                  />
                  <div className="table-footer">
                    Поручений: {assignments.length}
                    {query || status !== "all" || owner !== "all" ? (
                      <button
                        className="text-link"
                        onClick={() => {
                          setQuery("");
                          setStatus("all");
                          setOwner("all");
                        }}
                      >
                        Сбросить фильтры
                      </button>
                    ) : (
                      <span>Статус можно изменить прямо в списке</span>
                    )}
                  </div>
                </section>
              ) : (
                <section className="panel">
                  <div className="section-heading">
                    <h2>Требуют внимания</h2>
                    <span className="badge">{notices.length}</span>
                  </div>
                  {notices.length ? (
                    notices.map((a) => (
                      <button
                        className="notification-row"
                        key={a.id}
                        onClick={() => {
                          navigate("assignments");
                          setQuery(a.text);
                        }}
                      >
                        <span
                          className={`notice-icon ${statusOf(a) === "overdue" ? "red" : ""}`}
                        >
                          <AlertCircle size={21} />
                        </span>
                        <div>
                          <h3>
                            {statusOf(a) === "overdue"
                              ? "Срок исполнения истёк"
                              : "Приближается срок исполнения"}
                          </h3>
                          <p>{a.text}</p>
                          <small>
                            {a.assignee} · {dateText(a.deadline)}
                          </small>
                        </div>
                        <ChevronRight size={17} />
                      </button>
                    ))
                  ) : (
                    <Empty
                      title="Нет срочных уведомлений"
                      description="Здесь появятся поручения со сроком в ближайшие три дня и просроченные задачи."
                    />
                  )}
                </section>
              )}
            </>
          )}
          <footer className="workspace-footer no-print">
            <span>
              <ShieldCheck size={13} />
              Данные остаются в вашем браузере
            </span>
            <span aria-live="polite">
              {storageError
                ? "Ошибка сохранения"
                : saving
                  ? "Сохраняем…"
                  : "Сохранено локально"}
            </span>
          </footer>
        </main>
      </div>
      <CreateMeeting
        key={String(create)}
        open={create}
        onOpenChange={setCreate}
        onCreate={(m) => {
          void commit((s) => ({ ...s, meetings: [m, ...s.meetings] }))
            .then(() => toast.success("Совещание создано"))
            .catch(() => {});
          setCreate(false);
          openMeeting(m.id);
        }}
      />
      <Toaster position="bottom-right" richColors />
    </SidebarProvider>
  );
}
