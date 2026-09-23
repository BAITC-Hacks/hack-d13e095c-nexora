"use client";
import { WhatChanged } from "./what-changed";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  conferenceApi,
  downloadRoom,
  invitationLink,
  type LiveTask,
  type RoomSession,
  type RoomSnapshot,
} from "@/lib/conference-api";
import { ConferenceCall, type RemotePeer } from "@/lib/conference-call";
import { AudioUploadQueue, LiveCapture } from "@/lib/live-audio";
import {
  Mic,
  MicOff,
  Video,
  ScreenShare,
  Copy,
  Send,
  Phone,
  Download,
  FileText,
  Users,
  ArrowLeft,
  Square,
  X,
} from "./icons";

const stamp = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const taskLabels: Record<string, string> = {
  NEW: "Новое",
  IN_PROGRESS: "В работе",
  COMPLETED: "Выполнено",
  OVERDUE: "Просрочено",
  CANCELLED: "Отменено",
};
const analysisLabels: Record<string, string> = {
  waiting: "Ожидаем речь",
  analyzing: "ИИ анализирует реплики…",
  ready: "Анализ обновлён",
  error: "ИИ временно недоступен",
};

function MediaTile({
  stream,
  name,
  muted,
  video,
  self,
  state,
}: {
  stream: MediaStream | null;
  name: string;
  muted: boolean;
  video: boolean;
  self?: boolean;
  state?: string;
}) {
  const element = useRef<HTMLVideoElement>(null);
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    const el = element.current;
    if (!el || !stream) return;
    el.srcObject = stream;
    void el
      .play()
      .then(() => setBlocked(false))
      .catch(() => setBlocked(true));
    return () => {
      el.srcObject = null;
    };
  }, [stream]);
  return (
    <div className={"live-tile " + (video ? "has-video" : "")}>
      <video
        ref={element}
        autoPlay
        playsInline
        muted={self}
        aria-label={name}
      />
      {!video && (
        <div className="live-person-avatar">
          {name
            .split(" ")
            .map((n) => n[0])
            .slice(0, 2)
            .join("")
            .toUpperCase()}
        </div>
      )}
      <span className="live-tile-name">
        {muted ? <MicOff size={14} /> : <Mic size={14} />} {name}
        {self ? " (вы)" : ""}
      </span>
      {state && state !== "connected" && (
        <span className="live-peer-state">
          {state === "failed"
            ? "Нет медиасвязи · проверьте LAN/TURN"
            : "Соединение…"}
        </span>
      )}
      {blocked && !self && (
        <button
          className="live-play-audio"
          onClick={() =>
            void element.current?.play().then(() => setBlocked(false))
          }
        >
          Включить звук
        </button>
      )}
    </div>
  );
}

export function TaskCard({
  task,
  room,
  onChanged,
  participants = [],
}: {
  task: LiveTask;
  room: RoomSession;
  onChanged: () => void;
  participants?: { id: string; name: string }[];
}) {
  const [editing, setEditing] = useState(false),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  async function patch(values: unknown) {
    setSaving(true);
    setError("");
    try {
      await conferenceApi(`/${room.id}/tasks/${task.id}`, room.token, {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      setEditing(false);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <article className="live-task">
      <div className="live-task-head">
        <span
          className={
            "live-status " + (task.status === "OVERDUE" ? "danger" : "")
          }
        >
          {taskLabels[task.status]}
        </span>
        <span>
          {task.priority === "urgent"
            ? "Срочно"
            : task.priority === "high"
              ? "Высокий приоритет"
              : ""}
        </span>
      </div>
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            void patch({
              description: data.get("description"),
              ...(participants.length
                ? {
                    responsible_participant_id: data.get("responsible") || null,
                  }
                : {}),
              deadline: data.get("deadline")
                ? new Date(`${data.get("deadline")}T23:59:59`).toISOString()
                : null,
            });
          }}
        >
          <label>
            Поручение
            <textarea
              name="description"
              defaultValue={task.description}
              required
              maxLength={10000}
            />
          </label>
          <label>
            Срок
            <input
              name="deadline"
              type="date"
              defaultValue={task.deadline?.slice(0, 10) || ""}
            />
          </label>
          {participants.length > 0 && (
            <label>
              Ответственный
              <select
                name="responsible"
                defaultValue={task.responsible_participant_id || ""}
              >
                <option value="">Не указан</option>
                {participants.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="live-inline-actions">
            <button className="primary" disabled={saving}>
              Сохранить
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(false)}
            >
              Отмена
            </button>
          </div>
        </form>
      ) : (
        <>
          <h3>{task.description}</h3>
          <p>
            {task.responsible_name || "Ответственный не указан"} ·{" "}
            {task.deadline
              ? new Date(task.deadline).toLocaleDateString("ru-RU")
              : "Срок не указан"}
          </p>
        </>
      )}
      <details>
        <summary>Основание из разговора</summary>
        <blockquote>{task.source_quote}</blockquote>
        <small>
          Уверенность модели: {Math.round(task.confidence * 100)}%. Проверьте
          перед исполнением.
        </small>
      </details>
      <div className="live-inline-actions">
        <label className="live-sr-only" htmlFor={`status-${task.id}`}>
          Статус поручения
        </label>
        <select
          id={`status-${task.id}`}
          value={task.status}
          disabled={saving}
          onChange={(e) => void patch({ status: e.target.value })}
        >
          {Object.entries(taskLabels).map(([key, label]) => (
            <option key={key} value={key} disabled={key === "OVERDUE"}>
              {label}
            </option>
          ))}
        </select>
        <button className="text-link" onClick={() => setEditing(!editing)}>
          Изменить
        </button>
      </div>
      {error && (
        <p role="alert" className="live-error">
          {error}
        </p>
      )}
    </article>
  );
}

export function ConferenceRoom({
  session,
  onExit,
  onUpdate,
}: {
  session: RoomSession;
  onExit: () => void;
  onUpdate: (r: RoomSnapshot) => void;
}) {
  const [room, setRoom] = useState<RoomSnapshot | null>(null),
    [error, setError] = useState(""),
    [status, setStatus] = useState("disconnected"),
    [peers, setPeers] = useState<RemotePeer[]>([]),
    [local, setLocal] = useState<MediaStream | null>(null),
    [muted, setMuted] = useState(false),
    [camera, setCamera] = useState(false),
    [sharing, setSharing] = useState(false),
    [joining, setJoining] = useState(false),
    [panel, setPanel] = useState("transcript"),
    [chat, setChat] = useState(""),
    [uploads, setUploads] = useState(0),
    [uploadError, setUploadError] = useState(""),
    [working, setWorking] = useState(false),
    [diagnostics, setDiagnostics] = useState<{
      speech: boolean;
      ollama: boolean;
      worker: boolean;
    } | null>(null),
    [copied, setCopied] = useState(false);
  const call = useRef<ConferenceCall | null>(null),
    capture = useRef<LiveCapture | null>(null),
    queue = useRef<AudioUploadQueue | null>(null),
    latest = useRef<RoomSnapshot | null>(null),
    onUpdateRef = useRef(onUpdate),
    serverClock = useRef({ server: Date.now(), local: Date.now() });
  onUpdateRef.current = onUpdate;
  const refresh = useCallback(async () => {
    try {
      const next = await conferenceApi<RoomSnapshot>(
        `/${session.id}`,
        session.token,
      );
      latest.current = next;
      serverClock.current = {
        server: Date.parse(next.server_time),
        local: Date.now(),
      };
      setRoom(next);
      onUpdateRef.current(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [session.id, session.token]);
  const checkModels = useCallback(async () => {
    try {
      setDiagnostics(
        await conferenceApi(`/${session.id}/diagnostics`, session.token),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }, [session.id, session.token]);
  useEffect(() => {
    void refresh();
    void checkModels();
    const timer = setInterval(() => void refresh(), 3000);
    const q = new AudioUploadQueue(session, (count, message) => {
      setUploads(count);
      setUploadError(message || "");
    });
    queue.current = q;
    void q
      .restore()
      .catch(() =>
        setUploadError(
          "Не удалось открыть локальную очередь аудио. Разрешите хранение данных в браузере.",
        ),
      );
    return () => {
      clearInterval(timer);
      const c = capture.current,
        connection = call.current;
      void (async () => {
        await c?.stop();
        connection?.leave();
        q.close();
      })();
    };
  }, [refresh, checkModels, session]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (uploads || (room?.recording && status === "connected")) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [uploads, room?.recording, status]);
  useEffect(() => {
    if (
      !room?.recording ||
      room.ended_at ||
      status !== "connected" ||
      !call.current?.audioContext ||
      !queue.current
    )
      return;
    const clock = serverClock.current,
      now = clock.server + (Date.now() - clock.local),
      offset = Math.max(0, (now - Date.parse(room.started_at)) / 1000);
    const instance = new LiveCapture(
      call.current.audioContext,
      call.current.stream,
      offset,
      room.recording_version,
      queue.current,
      setError,
    );
    capture.current = instance;
    void instance
      .begin()
      .catch((e) =>
        setError(`Не удалось включить запись: ${(e as Error).message}`),
      );
    return () => {
      if (capture.current === instance) capture.current = null;
      void instance.stop();
    };
  }, [room?.recording, room?.recording_version, room?.ended_at, status]);
  async function leaveCall() {
    const active = capture.current;
    capture.current = null;
    await active?.stop();
    call.current?.leave();
    call.current = null;
    setStatus("disconnected");
    setLocal(null);
    setPeers([]);
    setSharing(false);
    setCamera(false);
    void refresh();
  }
  async function joinCall() {
    setJoining(true);
    setError("");
    try {
      const config = await conferenceApi<{ iceServers: RTCIceServer[] }>(
        `/${session.id}/rtc`,
        session.token,
      );
      const connection = new ConferenceCall(
        session.id,
        session.token,
        config.iceServers,
        {
          peers: setPeers,
          status: setStatus,
          local: (stream) => {
            setLocal(stream);
            setCamera(!!call.current?.camera);
            setSharing(!!call.current?.sharing);
            setMuted(!!call.current?.muted);
          },
          error: setError,
          changed: () => void refresh(),
          ended: () => {
            void leaveCall();
            void refresh();
          },
        },
      );
      call.current = connection;
      await connection.start(false);
    } catch (e) {
      setError(
        (e as Error).name === "NotAllowedError"
          ? "Разрешите доступ к микрофону в настройках браузера и повторите вход."
          : (e as Error).message,
      );
      call.current?.leave();
      call.current = null;
      setStatus("disconnected");
    } finally {
      setJoining(false);
    }
  }
  async function control(action: string, body?: unknown) {
    setWorking(true);
    setError("");
    try {
      await conferenceApi(`/${session.id}/${action}`, session.token, {
        method: "POST",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function download(path: string, name: string) {
    setWorking(true);
    setError("");
    try {
      await downloadRoom(session, path, name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(invitationLink(session));
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(
        "Не удалось скопировать ссылку. Выделите её в поле приглашения ниже.",
      );
    }
  }
  if (!room)
    return (
      <main className="live-loading">
        <h1>Открываем конференцию…</h1>
        {error && <p role="alert">{error}</p>}
        <button className="secondary" onClick={onExit}>
          На главную
        </button>
      </main>
    );
  const inCall = status !== "disconnected",
    me = room.participants.find((p) => p.id === room.me);
  return (
    <main className="live-room">
      <header className="live-room-header">
        <div>
          <button
            className="text-link"
            onClick={async () => {
              await leaveCall();
              onExit();
            }}
          >
            <ArrowLeft size={15} /> Главная
          </button>
          <h1>{room.title}</h1>
          <p>
            {room.ended_at
              ? "Конференция завершена"
              : `${peers.length + (inCall ? 1 : 0)} в звонке`}{" "}
            · {new Date(room.date).toLocaleString("ru-RU")}
          </p>
        </div>
        <div className="live-inline-actions">
          {session.invite && !room.ended_at && (
            <button className="secondary" onClick={() => void copyInvite()}>
              <Copy size={16} />
              {copied ? "Ссылка скопирована" : "Пригласить"}
            </button>
          )}
          <button className="secondary" onClick={() => void checkModels()}>
            Проверить ИИ
          </button>
        </div>
      </header>
      {error && (
        <div className="live-error" role="alert">
          {error}
          <button aria-label="Закрыть ошибку" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {diagnostics &&
        (!diagnostics.speech || !diagnostics.ollama || !diagnostics.worker) && (
          <div className="live-warning">
            Звонок работает независимо от ИИ.{" "}
            {!diagnostics.worker ? "Worker не запущен. " : ""}
            {!diagnostics.speech ? "Распознавание речи недоступно. " : ""}
            {!diagnostics.ollama ? "Ollama недоступна. " : ""}Проверьте
            настройки серверов; аудио останется в очереди.
          </div>
        )}
      <WhatChanged
        session={session}
        host={room.is_host}
        ended={!!room.ended_at}
        inCall={inCall}
      />
      <div
        className={"live-recording-banner " + (room.recording ? "on" : "")}
        role="status"
      >
        <span className={room.recording ? "live-dot" : "idle-dot"} />
        {room.recording
          ? "Идёт запись и ИИ-расшифровка. Каждый участник записывает свой микрофон."
          : "Запись выключена. Аудио не отправляется на распознавание."}
        {uploads > 0 && <strong>На устройстве: {uploads} фрагм.</strong>}
      </div>
      {uploadError && (
        <div className="live-warning" role="alert">
          {uploadError} Не закрывайте вкладку до отправки.
        </div>
      )}
      <div className="live-room-grid">
        <section className="live-call-stage" aria-label="Конференция">
          {inCall ? (
            <>
              <div
                className={
                  "live-video-grid " + (peers.length === 0 ? "alone" : "")
                }
              >
                <MediaTile
                  stream={local}
                  name={me?.name || "Вы"}
                  muted={muted}
                  video={camera || sharing}
                  self
                />
                {peers.map((peer) => (
                  <MediaTile
                    key={peer.id}
                    stream={peer.stream}
                    name={peer.name}
                    muted={peer.muted}
                    video={peer.camera || peer.sharing}
                    state={peer.state}
                  />
                ))}
              </div>
              {status !== "connected" && (
                <p className="live-connection-state" role="status">
                  {status === "reconnecting"
                    ? "Соединение потеряно. Переподключаемся…"
                    : "Подключаемся к конференции…"}
                </p>
              )}
              <div className="live-call-controls">
                <button
                  aria-pressed={muted}
                  onClick={() => {
                    call.current?.toggleMic();
                    setMuted(!!call.current?.muted);
                  }}
                >
                  {muted ? <MicOff /> : <Mic />}
                  <span>{muted ? "Включить микрофон" : "Микрофон"}</span>
                </button>
                <button
                  aria-pressed={camera}
                  onClick={() =>
                    void call.current
                      ?.toggleCamera()
                      .then(() => setCamera(!!call.current?.camera))
                      .catch((e) => setError((e as Error).message))
                  }
                >
                  <Video />
                  <span>{camera ? "Выключить камеру" : "Камера"}</span>
                </button>
                <button
                  aria-pressed={sharing}
                  onClick={() =>
                    void call.current
                      ?.shareScreen()
                      .then(() => setSharing(!!call.current?.sharing))
                      .catch((e) => {
                        if ((e as Error).name !== "NotAllowedError")
                          setError((e as Error).message);
                      })
                  }
                >
                  <ScreenShare />
                  <span>{sharing ? "Остановить показ" : "Показать экран"}</span>
                </button>
                {room.is_host && (
                  <button
                    className={
                      room.recording ? "live-record active" : "live-record"
                    }
                    disabled={working || status !== "connected"}
                    onClick={() =>
                      void control("recording", { enabled: !room.recording })
                    }
                  >
                    {room.recording ? <Square /> : <Mic />}
                    <span>
                      {room.recording ? "Остановить запись" : "Запись и ИИ"}
                    </span>
                  </button>
                )}
                <button
                  className="live-hangup"
                  onClick={() => void leaveCall()}
                >
                  <Phone />
                  <span>Выйти</span>
                </button>
              </div>
            </>
          ) : (
            <div className="live-prejoin">
              <div className="live-prejoin-icon">
                <Users size={42} />
              </div>
              <h2>
                {room.ended_at ? "Встреча завершена" : "Готовы присоединиться?"}
              </h2>
              <p>
                {room.ended_at
                  ? "Расшифровка, поручения и итоговый протокол сохранены на сервере."
                  : "Вы войдёте с микрофоном. Камеру и показ экрана можно включить во время звонка."}
              </p>
              {!room.ended_at && (
                <button
                  className="primary"
                  disabled={joining}
                  onClick={() => void joinCall()}
                >
                  <Mic size={19} />
                  {joining ? "Доступ к микрофону…" : "Войти в конференцию"}
                </button>
              )}
              {!room.ended_at && (
                <small>
                  Все участники уведомлены о возможности записи и ИИ-анализа.
                </small>
              )}
            </div>
          )}
          {session.invite && !room.ended_at && (
            <div className="live-invite">
              <label htmlFor="invite-link">Ссылка для сотрудников</label>
              <input
                id="invite-link"
                value={invitationLink(session)}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
              />
            </div>
          )}
          <div className="live-analysis-status">
            <span>
              {analysisLabels[room.analysis_status] || room.analysis_status}
            </span>
            <span>Аудио в обработке: {room.audio.pending}</span>
            {room.analysis_error && (
              <span className="live-status danger">{room.analysis_error}</span>
            )}
            {room.audio.failed > 0 && (
              <button
                className="text-link"
                onClick={() => void control("retry")}
              >
                Повторить {room.audio.failed} неудачных фрагм.
              </button>
            )}
          </div>
          <div className="live-meeting-actions">
            <button
              className="secondary"
              disabled={working}
              onClick={() => void download("recording.wav", "conference.wav")}
            >
              <Download size={16} /> Аудиозапись
            </button>
            {room.is_host && (
              <button
                className="secondary"
                disabled={working || room.analysis_status === "analyzing"}
                onClick={() => void control("analyze")}
              >
                <FileText size={16} />
                Обновить итог
              </button>
            )}
            {room.is_host && !room.ended_at && (
              <button
                className="live-end"
                disabled={working}
                onClick={() => {
                  if (
                    window.confirm(
                      "Завершить конференцию для всех участников? Запись остановится, ИИ подготовит итог.",
                    )
                  )
                    void control("end");
                }}
              >
                Завершить для всех
              </button>
            )}
          </div>
        </section>
        <aside className="live-room-sidebar">
          <div
            role="tablist"
            aria-label="Материалы встречи"
            className="live-room-tabs"
          >
            {[
              ["transcript", "Речь"],
              [
                "tasks",
                `Поручения${room.tasks.length ? " " + room.tasks.length : ""}`,
              ],
              ["summary", "Итоги"],
              ["chat", "Чат"],
              ["people", "Люди"],
            ].map(([id, label]) => (
              <button
                key={id}
                role="tab"
                id={`tab-${id}`}
                aria-controls={`panel-${id}`}
                aria-selected={panel === id}
                onClick={() => setPanel(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`panel-${panel}`}
            aria-labelledby={`tab-${panel}`}
            className="live-room-panel"
          >
            {panel === "transcript" && (
              <>
                <div className="live-panel-heading">
                  <h2>Живая расшифровка</h2>
                  <p>Русский · қазақша · смешанная речь</p>
                </div>
                {room.transcript.length ? (
                  room.transcript.map((s) => (
                    <article key={s.id} className="live-transcript">
                      <header>
                        <strong>{s.speaker_name || "Участник"}</strong>
                        <time>{stamp(s.start)}</time>
                      </header>
                      <p>{s.text}</p>
                    </article>
                  ))
                ) : (
                  <div className="live-empty">
                    <Mic size={28} />
                    <h3>Здесь появятся реплики</h3>
                    <p>
                      Организатор включает «Запись и ИИ». Текст поступает
                      фрагментами примерно по 8 секунд плюс время распознавания.
                    </p>
                  </div>
                )}
              </>
            )}
            {panel === "tasks" && (
              <>
                <div className="live-panel-heading">
                  <h2>Поручения из разговора</h2>
                  <p>Проверьте ответственных и сроки перед исполнением.</p>
                </div>
                {room.tasks.length ? (
                  room.tasks.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      room={session}
                      participants={room.participants}
                      onChanged={() => void refresh()}
                    />
                  ))
                ) : (
                  <div className="live-empty">
                    <FileText size={28} />
                    <h3>Поручений пока нет</h3>
                    <p>
                      Озвучьте, что нужно сделать, кто отвечает и к какому
                      сроку. ИИ добавит поручение после анализа.
                    </p>
                  </div>
                )}
              </>
            )}
            {panel === "summary" && (
              <>
                <div className="live-panel-heading">
                  <h2>Итоговый протокол</h2>
                  <p>
                    {room.analysis_stale
                      ? "Есть новые реплики. Итог будет обновлён."
                      : "Проект ИИ — проверьте по расшифровке."}
                  </p>
                </div>
                {room.summary ? (
                  <div className="live-summary">
                    <h3>Краткое содержание</h3>
                    <p>{room.summary}</p>
                    {room.topics.length > 0 && (
                      <>
                        <h3>Темы</h3>
                        <ul>
                          {room.topics.map((t, i) => (
                            <li key={i}>{t}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {room.decisions.length > 0 && (
                      <>
                        <h3>Решения</h3>
                        <ul>
                          {room.decisions.map((t, i) => (
                            <li key={i}>{t}</li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="live-empty">
                    <h3>Итоги ещё не готовы</h3>
                    <p>
                      Они появятся после первых распознанных реплик и ответа
                      локальной модели.
                    </p>
                  </div>
                )}
                <div className="live-inline-actions">
                  <button
                    className="secondary"
                    disabled={
                      working ||
                      room.recording ||
                      room.analysis_stale ||
                      !room.analysis_version
                    }
                    onClick={() => void download("exports/pdf", "protocol.pdf")}
                  >
                    Скачать PDF
                  </button>
                  <button
                    className="secondary"
                    disabled={
                      working ||
                      room.recording ||
                      room.analysis_stale ||
                      !room.analysis_version
                    }
                    onClick={() =>
                      void download("exports/docx", "protocol.docx")
                    }
                  >
                    Скачать DOCX
                  </button>
                </div>
                <p className="live-hint">
                  Для экспорта остановите запись и дождитесь обработки всех
                  фрагментов.
                </p>
              </>
            )}
            {panel === "chat" && (
              <>
                <div className="live-panel-heading">
                  <h2>Чат конференции</h2>
                </div>
                {room.messages.map((m) => (
                  <article className="live-chat-message" key={m.id}>
                    <strong>{m.name}</strong>
                    <small>
                      {new Date(m.at).toLocaleTimeString("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </small>
                    <p>{m.text}</p>
                  </article>
                ))}
                {!room.messages.length && (
                  <p className="live-empty">
                    Сообщений пока нет. Чат доступен участникам звонка.
                  </p>
                )}
                <form
                  className="live-chat-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    try {
                      call.current?.chat(chat.trim());
                      setChat("");
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <input
                    aria-label="Сообщение"
                    placeholder="Написать сообщение…"
                    value={chat}
                    maxLength={2000}
                    onChange={(e) => setChat(e.target.value)}
                  />
                  <button
                    className="primary"
                    aria-label="Отправить сообщение"
                    disabled={status !== "connected" || !chat.trim()}
                  >
                    <Send size={18} />
                  </button>
                </form>
              </>
            )}
            {panel === "people" && (
              <>
                <div className="live-panel-heading">
                  <h2>Участники</h2>
                  <p>
                    Имена привязаны к отдельным микрофонам. Один человек — одно
                    устройство.
                  </p>
                </div>
                {room.participants.map((p) => (
                  <div className="live-person" key={p.id}>
                    <span className="avatar">{p.name.slice(0, 2)}</span>
                    <div>
                      <strong>
                        {p.name}
                        {p.id === room.me ? " (вы)" : ""}
                      </strong>
                      <small>
                        {p.is_host ? "Организатор · " : ""}
                        {p.online ? "В конференции" : "Не в звонке"}
                      </small>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
