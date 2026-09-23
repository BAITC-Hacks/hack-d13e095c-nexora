"use client";
import { useCallback, useEffect, useState } from "react";
import {
  conferenceApi,
  ApiError,
  forgetRoom,
  savedRooms,
  saveRoom,
  type RoomSession,
  type RoomSnapshot,
} from "@/lib/conference-api";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ConferenceRoom, TaskCard } from "./conference-room";
import {
  Mic,
  CalendarDays,
  Users,
  Headphones,
  FileText,
  AudioLines,
  ArrowRight,
  X,
  Bell,
  Plus,
} from "./icons";

type Invitation = { id: string; invite: string };
export function ConferenceApp() {
  const [sessions, setSessions] = useState<RoomSession[]>([]),
    [current, setCurrent] = useState<RoomSession | null>(null),
    [view, setView] = useState("home"),
    [dialog, setDialog] = useState<"start" | "schedule" | "join" | null>(null),
    [invitation, setInvitation] = useState<Invitation | null>(null),
    [name, setName] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [snapshots, setSnapshots] = useState<Record<string, RoomSnapshot>>({}),
    [ready, setReady] = useState(false);
  const remember = useCallback((session: RoomSession) => {
    try {
      saveRoom(session);
      setSessions(savedRooms());
    } catch {
      setSessions((s) => [session, ...s.filter((x) => x.id !== session.id)]);
      setError(
        "Браузер не сохраняет доступ к встречам. Разрешите локальное хранилище, прежде чем закрывать вкладку.",
      );
    }
  }, []);
  useEffect(() => {
    const existing = savedRooms();
    setSessions(existing);
    try {
      setName(localStorage.getItem("protocol-display-name") || "");
    } catch {}
    const params = new URLSearchParams(location.search),
      hash = new URLSearchParams(location.hash.slice(1)),
      id = params.get("room"),
      invite = hash.get("invite");
    if (id) {
      const own = existing.find((s) => s.id === id);
      if (own) setCurrent(own);
      else if (invite) {
        setInvitation({ id, invite });
        setDialog("join");
      } else
        setError(
          "Нет доступа к этой встрече. Попросите организатора прислать полную ссылку приглашения.",
        );
    }
    setReady(true);
  }, []);
  const update = useCallback(
    (r: RoomSnapshot) => setSnapshots((s) => ({ ...s, [r.id]: r })),
    [],
  );
  const refreshAll = useCallback(async () => {
    const results = await Promise.allSettled(
      sessions.map(async (s) => {
        const r = await conferenceApi<RoomSnapshot>(`/${s.id}`, s.token);
        update(r);
        return r;
      }),
    );
    const inaccessible = sessions.filter((_, index) => {
      const result = results[index];
      return (
        result.status === "rejected" &&
        result.reason instanceof ApiError &&
        [403, 404].includes(result.reason.status)
      );
    });
    if (inaccessible.length) {
      const ids = new Set(inaccessible.map((s) => s.id));
      for (const id of ids) {
        try {
          forgetRoom(id);
        } catch {}
      }
      setSessions((previous) => previous.filter((s) => !ids.has(s.id)));
      setSnapshots((previous) =>
        Object.fromEntries(
          Object.entries(previous).filter(([id]) => !ids.has(id)),
        ),
      );
    }
    if (
      typeof Notification !== "undefined" &&
      Notification.permission === "granted"
    )
      for (const result of results) {
        if (result.status !== "fulfilled") continue;
        for (const t of result.value.tasks) {
          if (!t.deadline || ["COMPLETED", "CANCELLED"].includes(t.status))
            continue;
          const diff = Date.parse(t.deadline) - Date.now();
          if (diff > 3 * 86400000) continue;
          const key = `protocol-reminder:${t.id}:${t.deadline}:${new Date().toISOString().slice(0, 10)}`;
          try {
            if (localStorage.getItem(key)) continue;
            new Notification(
              diff < 0 ? "Поручение просрочено" : "Приближается срок поручения",
              {
                body: `${t.description} · ${t.responsible_name || "Ответственный не указан"}`,
              },
            );
            localStorage.setItem(key, "1");
          } catch {}
        }
      }
  }, [sessions, update]);
  useEffect(() => {
    if (current) return;
    void refreshAll();
    const t = setInterval(() => void refreshAll(), 30000);
    return () => clearInterval(t);
  }, [refreshAll, current]);
  function open(session: RoomSession) {
    setCurrent(session);
    history.replaceState(
      null,
      "",
      `/?room=${session.id}${session.invite ? "#invite=" + encodeURIComponent(session.invite) : ""}`,
    );
  }
  function closeRoom() {
    setCurrent(null);
    history.replaceState(null, "", "/");
    void refreshAll();
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const person = String(data.get("name") || "").trim();
      if (!person) throw new Error("Введите ваше имя");
      const consent = data.get("consent") === "on";
      let result: { token: string; invite?: string; room: RoomSnapshot };
      if (dialog === "join") {
        let target = invitation;
        if (!target) {
          let url: URL;
          try {
            url = new URL(String(data.get("link")));
          } catch {
            throw new Error("Вставьте полную ссылку приглашения");
          }
          const id = url.searchParams.get("room"),
            invite = new URLSearchParams(url.hash.slice(1)).get("invite");
          if (!id || !invite) throw new Error("В ссылке нет кода конференции");
          if (url.origin !== location.origin)
            throw new Error(
              "Эта ссылка ведёт на другой сервер. Откройте её в новой вкладке.",
            );
          target = { id, invite };
        }
        result = await conferenceApi(`/${target.id}/join`, undefined, {
          method: "POST",
          body: JSON.stringify({
            invite: target.invite,
            name: person,
            consent,
          }),
        });
        result.invite = target.invite;
      } else {
        result = await conferenceApi("", undefined, {
          method: "POST",
          headers: { "X-Conference-Key": String(data.get("accessKey") || "") },
          body: JSON.stringify({
            title: String(data.get("title") || "").trim(),
            name: person,
            consent,
            scheduled_at: data.get("date")
              ? new Date(String(data.get("date"))).toISOString()
              : null,
          }),
        });
      }
      try {
        localStorage.setItem("protocol-display-name", person);
      } catch {}
      setName(person);
      const session = {
        id: result.room.id,
        token: result.token,
        invite: result.invite,
        title: result.room.title,
      };
      remember(session);
      update(result.room);
      setDialog(null);
      setInvitation(null);
      open(session);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const allTasks = sessions.flatMap((session) =>
    (snapshots[session.id]?.tasks || []).map((task) => ({ task, session })),
  );
  const reminders = allTasks.filter(
    ({ task }) =>
      task.deadline &&
      !["COMPLETED", "CANCELLED"].includes(task.status) &&
      Date.parse(task.deadline) < Date.now() + 3 * 86400000,
  );
  if (!ready)
    return (
      <main className="live-loading">
        <AudioLines size={32} />
        <h1>Протокол</h1>
        <p>Открываем рабочее пространство…</p>
      </main>
    );
  if (current)
    return (
      <ConferenceRoom
        key={current.id}
        session={current}
        onExit={closeRoom}
        onUpdate={update}
      />
    );
  const listed = sessions.filter(
    (s) =>
      view !== "recordings" ||
      snapshots[s.id]?.audio.done ||
      snapshots[s.id]?.audio.pending,
  );
  return (
    <div className="live-app">
      <a className="skip-link" href="#live-main">
        Перейти к содержимому
      </a>
      <header className="conference-header">
        <button className="conference-brand" onClick={() => setView("home")}>
          <span className="brand-icon">
            <AudioLines size={23} />
          </span>
          Протокол
        </button>
        <nav className="conference-nav" aria-label="Основная навигация">
          {[
            ["home", "Главная", Mic],
            ["meetings", "Конференции", Users],
            ["recordings", "Записи", Headphones],
            ["tasks", "Поручения", FileText],
            ["notices", "Напоминания", Bell],
          ].map(([id, label, Icon]) => {
            const Glyph = Icon as typeof Mic;
            return (
              <button
                key={id as string}
                className={"nav-item " + (view === id ? "active" : "")}
                aria-current={view === id ? "page" : undefined}
                onClick={() => setView(id as string)}
              >
                <Glyph size={20} />
                {label as string}
                {id === "notices" && reminders.length > 0 && (
                  <span className="count">{reminders.length}</span>
                )}
              </button>
            );
          })}
        </nav>
        <span className="local-mode">
          <span />
          Локальный ИИ
        </span>
      </header>
      <main id="live-main" className="content live-home">
        <div className="page-heading">
          <div>
            <h1>
              {view === "home"
                ? "Начнём встречу?"
                : view === "tasks"
                  ? "Поручения"
                  : view === "notices"
                    ? "Напоминания"
                    : view === "recordings"
                      ? "Записи встреч"
                      : "Ваши конференции"}
            </h1>
            <p>
              {view === "home"
                ? "Пригласите коллег. Общайтесь. ИИ запишет главное."
                : "Данные хранятся на сервере вашей команды."}
            </p>
          </div>
          {view !== "home" && (
            <button
              className="primary"
              onClick={() => {
                setDialog("start");
                setError("");
              }}
            >
              <Plus size={16} />
              Новая конференция
            </button>
          )}
        </div>
        {error && !dialog && (
          <div className="live-error" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="Закрыть">
              <X size={16} />
            </button>
          </div>
        )}
        {view === "home" && (
          <>
            <section className="live-home-launch">
              <div className="launch-actions">
                <button
                  className="launch-action start-action"
                  onClick={() => {
                    setDialog("start");
                    setError("");
                  }}
                >
                  <span className="launch-icon">
                    <Mic size={34} />
                  </span>
                  <strong>Начать совещание</strong>
                  <small>Создать конференцию</small>
                </button>
                <button
                  className="launch-action"
                  onClick={() => {
                    setInvitation(null);
                    setDialog("join");
                    setError("");
                  }}
                >
                  <span className="launch-icon">
                    <Users size={34} />
                  </span>
                  <strong>Присоединиться</strong>
                  <small>По ссылке от коллеги</small>
                </button>
                <button
                  className="launch-action"
                  onClick={() => {
                    setDialog("schedule");
                    setError("");
                  }}
                >
                  <span className="launch-icon">
                    <CalendarDays size={34} />
                  </span>
                  <strong>Запланировать</strong>
                  <small>Выбрать время встречи</small>
                </button>
                <button
                  className="launch-action"
                  onClick={() => setView("recordings")}
                >
                  <span className="launch-icon">
                    <Headphones size={34} />
                  </span>
                  <strong>Записи и итоги</strong>
                  <small>Вернуться к разговору</small>
                </button>
              </div>
              <aside className="live-home-guide">
                <h2>От разговора — к результату</h2>
                <ol>
                  <li>
                    <strong>Пригласите команду</strong>
                    <span>
                      Скопируйте ссылку и отправьте сотрудникам в вашей сети.
                    </span>
                  </li>
                  <li>
                    <strong>Включите «Запись и ИИ»</strong>
                    <span>
                      Все увидят уведомление. Реплики появятся с именами
                      говорящих.
                    </span>
                  </li>
                  <li>
                    <strong>Проверьте поручения</strong>
                    <span>
                      Ответственные, сроки и итоговый протокол — рядом со
                      звонком.
                    </span>
                  </li>
                </ol>
                <p>Аудио и текст обрабатываются только на ваших серверах.</p>
              </aside>
            </section>
            <div className="section-heading live-section-heading">
              <h2>Последние конференции</h2>
              <button className="text-link" onClick={() => setView("meetings")}>
                Все встречи <ArrowRight size={15} />
              </button>
            </div>
          </>
        )}
        {(view === "home" || view === "meetings" || view === "recordings") && (
          <section className="live-room-list">
            {(view === "home" ? listed.slice(0, 5) : listed).map((s) => {
              const r = snapshots[s.id];
              return (
                <button
                  className="recent-meeting"
                  key={s.id}
                  onClick={() => open(s)}
                >
                  <span className="recent-icon">
                    {r?.ended_at ? <FileText size={21} /> : <Users size={21} />}
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>
                      {r
                        ? new Date(r.date).toLocaleString("ru-RU")
                        : "Открыть сохранённую конференцию"}{" "}
                      ·{" "}
                      {r?.ended_at
                        ? "Завершена"
                        : r?.recording
                          ? "Идёт запись"
                          : "Можно войти"}
                    </small>
                  </span>
                  <ArrowRight size={18} />
                </button>
              );
            })}
            {!listed.length && (
              <div className="live-empty">
                <Users size={30} />
                <h3>
                  {view === "recordings"
                    ? "Записей пока нет"
                    : "Здесь появятся ваши конференции"}
                </h3>
                <p>
                  {view === "recordings"
                    ? "Начните встречу и включите «Запись и ИИ»."
                    : "Создайте встречу или присоединитесь по приглашению."}
                </p>
              </div>
            )}
          </section>
        )}
        {(view === "tasks" || view === "notices") && (
          <>
            <div className="live-dashboard-toolbar">
              <p>
                {view === "notices"
                  ? "Просроченные и со сроком в ближайшие три дня. Уведомления проверяются каждые 30 секунд, пока открыт сайт."
                  : "Поручения из доступных вам конференций. Изменения видны всем участникам."}
              </p>
              {view === "notices" && (
                <button
                  className="secondary"
                  onClick={() => {
                    if (typeof Notification !== "undefined")
                      void Notification.requestPermission().then(() =>
                        refreshAll(),
                      );
                  }}
                >
                  Разрешить уведомления
                </button>
              )}
            </div>
            <div className="live-task-grid">
              {(view === "notices" ? reminders : allTasks).map(
                ({ task, session }) => (
                  <div key={task.id}>
                    <button className="text-link" onClick={() => open(session)}>
                      {session.title}
                    </button>
                    <TaskCard
                      task={task}
                      room={session}
                      participants={snapshots[session.id]?.participants}
                      onChanged={() => void refreshAll()}
                    />
                  </div>
                ),
              )}
            </div>
            {!(view === "notices" ? reminders : allTasks).length && (
              <div className="live-empty">
                <FileText size={30} />
                <h3>
                  {view === "notices"
                    ? "Срочных поручений нет"
                    : "Поручений пока нет"}
                </h3>
                <p>Они появятся после анализа реального разговора.</p>
              </div>
            )}
          </>
        )}
        <footer className="workspace-footer">
          <span>WebRTC · локальная обработка · до 8 участников</span>
        </footer>
      </main>
      <Dialog
        open={!!dialog}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setDialog(null);
            setInvitation(null);
          }
        }}
      >
        <DialogContent className="live-modal" showCloseButton={false}>
          <button
            className="live-modal-close"
            aria-label="Закрыть"
            disabled={busy}
            onClick={() => {
              setDialog(null);
              setInvitation(null);
            }}
          >
            <X size={21} />
          </button>
          <DialogTitle id="room-form-title">
            {dialog === "join"
              ? "Присоединиться к встрече"
              : dialog === "schedule"
                ? "Запланировать конференцию"
                : "Новая конференция"}
          </DialogTitle>
          <DialogDescription>
            Ваше имя увидят коллеги и оно будет указано в расшифровке.
          </DialogDescription>
          <form onSubmit={submit}>
            <label>
              Ваше имя
              <input
                name="name"
                autoFocus
                autoComplete="name"
                defaultValue={name}
                required
                maxLength={100}
                placeholder="Имя и фамилия"
              />
            </label>
            {dialog !== "join" && (
              <label>
                Тема встречи
                <input
                  name="title"
                  required
                  maxLength={300}
                  defaultValue={`Совещание ${new Date().toLocaleDateString("ru-RU")}`}
                />
              </label>
            )}
            {dialog === "schedule" && (
              <label>
                Дата и время
                <input name="date" type="datetime-local" required />
              </label>
            )}
            {dialog === "join" && !invitation && (
              <label>
                Ссылка приглашения
                <input
                  name="link"
                  required
                  type="url"
                  placeholder="https://…/?room=…#invite=…"
                />
              </label>
            )}
            {dialog !== "join" && (
              <details>
                <summary>Ключ доступа, если задан администратором</summary>
                <input
                  name="accessKey"
                  aria-label="Ключ создания конференций"
                  type="password"
                  autoComplete="off"
                />
              </details>
            )}
            <label className="live-consent">
              <input name="consent" type="checkbox" required />
              <span>
                Я согласен на запись и локальную ИИ-расшифровку, когда
                организатор включит запись. Содержание доступно участникам
                встречи.
              </span>
            </label>
            {error && (
              <div className="live-error" role="alert">
                {error}
              </div>
            )}
            <button className="primary" disabled={busy}>
              {busy
                ? "Подключаемся…"
                : dialog === "join"
                  ? "Открыть конференцию"
                  : dialog === "schedule"
                    ? "Создать и получить ссылку"
                    : "Создать конференцию"}
            </button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
