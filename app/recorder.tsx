"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square, Download, Headphones } from "./icons";
import { toast } from "sonner";
import type { Meeting } from "@/lib/types";
const duration = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
export function Recorder({
  meeting,
  onSave,
  onBusy,
  externalBusy = false,
}: {
  externalBusy?: boolean;
  meeting: Meeting;
  onSave: (blob: Blob, seconds: number) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [recording, setRecording] = useState(false),
    [pending, setPending] = useState(false),
    [seconds, setSeconds] = useState(0),
    [url, setUrl] = useState(""),
    [error, setError] = useState("");
  const latestSave = useRef(onSave);
  latestSave.current = onSave;
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    alive = useRef(true),
    started = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (recorder.current?.state === "recording") recorder.current.stop();
      stream.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);
  useEffect(() => {
    if (!meeting.audio) {
      setUrl("");
      return;
    }
    const u = URL.createObjectURL(meeting.audio);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [meeting.audio]);
  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - started.current) / 1000)),
      250,
    );
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => {
      clearInterval(timer);
      window.removeEventListener("beforeunload", guard);
    };
  }, [recording]);
  async function start() {
    setError("");
    setPending(true);
    onBusy(true);
    try {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined"
      )
        throw new Error(
          "Запись недоступна. Откройте сайт в современном браузере по HTTPS или localhost.",
        );
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = s;
      const r = new MediaRecorder(s);
      recorder.current = r;
      const chunks: BlobPart[] = [];
      r.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      r.onerror = () => {
        setError("Запись прервана. Проверьте микрофон и попробуйте снова.");
        s.getTracks().forEach((t) => t.stop());
        setRecording(false);
        onBusy(false);
      };
      r.onstop = () => {
        s.getTracks().forEach((t) => t.stop());
        if (!alive.current) return;
        const blob = new Blob(chunks, { type: r.mimeType || "audio/webm" });
        setRecording(false);
        onBusy(false);
        if (blob.size) {
          latestSave.current(
            blob,
            Math.max(1, Math.round((Date.now() - started.current) / 1000)),
          );
          toast.success("Аудиозапись готова");
        } else setError("Пустая запись. Проверьте микрофон и повторите.");
      };
      started.current = Date.now();
      setSeconds(0);
      r.start(250);
      setRecording(true);
    } catch (e) {
      const err = e as Error;
      setError(
        err.name === "NotAllowedError"
          ? "Нет доступа к микрофону. Разрешите доступ в настройках браузера и повторите."
          : err.name === "NotFoundError"
            ? "Микрофон не найден. Подключите его и повторите."
            : err.message || "Не удалось начать запись.",
      );
      onBusy(false);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="record-panel">
      <div className="record-heading">
        <span className={`record-icon ${recording ? "recording" : ""}`}>
          <Headphones size={23} />
        </span>
        <div>
          <h3>
            {recording ? "Идёт запись совещания" : "Аудиозапись совещания"}
          </h3>
          <p>
            {recording
              ? "Остановите запись перед переходом в другой раздел."
              : "Запись сохраняется только в этом браузере."}
          </p>
        </div>
        <span className="record-time">
          {duration(recording ? seconds : meeting.audioSeconds || 0)}
        </span>
        {recording ? (
          <button
            className="stop-button"
            onClick={() => recorder.current?.stop()}
          >
            <Square size={14} fill="currentColor" />
            Остановить
          </button>
        ) : (
          <button
            className="primary"
            disabled={pending || externalBusy || !!meeting.protocol?.approvedAt}
            onClick={start}
          >
            <Mic size={16} />
            {pending
              ? "Доступ к микрофону…"
              : meeting.audio
                ? "Перезаписать"
                : "Начать запись"}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="error-note">
          {error}
        </p>
      )}
      {url && (
        <div className="audio-player">
          <audio controls src={url} aria-label="Запись совещания" />
          <a
            href={url}
            download={`soveshchanie-${meeting.id}.${meeting.audio?.type.includes("mp4") ? "m4a" : "webm"}`}
            className="text-link"
          >
            <Download size={16} />
            Скачать
          </a>
        </div>
      )}
    </section>
  );
}
