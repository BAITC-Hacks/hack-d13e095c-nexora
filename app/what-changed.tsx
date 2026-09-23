"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  conferenceApi,
  savedRooms,
  type RoomSession,
  type RoomSnapshot,
} from "@/lib/conference-api";

type Item = {
  category: "risk" | "deadline" | "decision" | "question";
  text: string;
  responsible?: string | null;
  deadline?: string;
  previous?: { deadline: string | null; status: string };
  evidence: {
    label: string;
    quote: string;
    start?: number | null;
    task_id?: string;
  }[];
};
type Briefing = {
  configured: boolean;
  status?: "pending" | "generating" | "ready" | "error";
  stale?: boolean;
  updates?: string | null;
  generated_at?: string | null;
  error?: string | null;
  result?: {
    items: Item[];
    remaining: number;
    warnings: string[];
    previous_title: string;
    since: string;
  } | null;
};
const categories = {
  risk: "Новый риск",
  deadline: "Срок сорван",
  decision: "Решение изменилось",
  question: "Открытый вопрос",
};

export function WhatChanged({
  session,
  host,
  ended,
  inCall,
}: {
  session: RoomSession;
  host: boolean;
  ended: boolean;
  inCall: boolean;
}) {
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [options, setOptions] = useState<RoomSession[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const alive = useRef(true),
    refreshed = useRef(false);
  const refresh = useCallback(async () => {
    try {
      const next = await conferenceApi<Briefing>(
        `/${session.id}/briefing`,
        session.token,
      );
      if (alive.current) {
        setBrief(next);
        setError("");
      }
      return next;
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    }
  }, [session.id, session.token]);
  useEffect(() => {
    alive.current = true;
    refreshed.current = false;
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [refresh]);
  // A scheduled meeting may be opened days later: refresh stale successful output once on entry.
  useEffect(() => {
    if (
      host &&
      !ended &&
      !refreshed.current &&
      brief?.status === "ready" &&
      brief.stale
    ) {
      refreshed.current = true;
      void save(brief.updates || "");
    }
  }, [brief, host, ended]);
  async function save(updates: string) {
    setSaving(true);
    setError("");
    try {
      await conferenceApi(`/${session.id}/briefing`, session.token, {
        method: "PATCH",
        body: JSON.stringify({ updates }),
      });
      setEditing(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function choose() {
    setChoosing(true);
    setLoadingOptions(true);
    setError("");
    const candidates = savedRooms().filter((s) => s.id !== session.id);
    const results = await Promise.allSettled(
      candidates.map(async (s) => {
        const r = await conferenceApi<RoomSnapshot>(`/${s.id}`, s.token);
        return r.is_host && r.ended_at ? s : null;
      }),
    );
    setOptions(
      results.flatMap((r) =>
        r.status === "fulfilled" && r.value ? [r.value] : [],
      ),
    );
    setLoadingOptions(false);
  }
  async function configure(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget),
      previous = options.find((o) => o.id === data.get("previous"));
    if (!previous) return;
    setSaving(true);
    setError("");
    try {
      await conferenceApi(`/${session.id}/briefing`, session.token, {
        method: "PUT",
        body: JSON.stringify({
          previous_id: previous.id,
          previous_token: previous.token,
          updates: String(data.get("updates") || ""),
          share_with_participants: data.get("share") === "on",
        }),
      });
      setChoosing(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const busy =
    saving || brief?.status === "pending" || brief?.status === "generating";
  return (
    <section className="what-changed" aria-labelledby="what-changed-title">
      <header>
        <div>
          <h2 id="what-changed-title">Что изменилось?</h2>
          <p>What Changed? · Главное за 30 секунд чтения</p>
        </div>
        {brief?.configured && host && !ended && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void save(brief.updates || "")}
          >
            {busy ? "Готовим сводку…" : "Обновить"}
          </button>
        )}
      </header>
      {error && (
        <p className="live-error" role="alert">
          {error}{" "}
          <button className="text-link" onClick={() => void refresh()}>
            Повторить
          </button>
        </p>
      )}
      {!brief && !error && (
        <p role="status">Проверяем данные прошлого созвона…</p>
      )}
      {brief && !brief.configured && (
        <>
          <p>
            Прошлая встреча не выбрана. Для первой встречи сравнение не
            требуется.
          </p>
          {host && !ended && !choosing && (
            <button className="text-link" onClick={() => void choose()}>
              Выбрать прошлый созвон
            </button>
          )}
          {choosing && (
            <form className="briefing-form" onSubmit={configure}>
              {loadingOptions ? (
                <p role="status">Загружаем встречи…</p>
              ) : !options.length ? (
                <p>Нет завершённых встреч, где вы организатор.</p>
              ) : (
                <>
                  <label>
                    Предыдущая встреча
                    <select name="previous" required>
                      <option value="">Выберите встречу</option>
                      {options.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Что произошло после созвона?
                    <textarea name="updates" maxLength={2000} rows={3} />
                  </label>
                  <label className="live-consent">
                    <input type="checkbox" name="share" required />
                    <span>
                      Показать участникам сводку и цитаты прошлого созвона.
                    </span>
                  </label>
                  <button className="primary" disabled={saving}>
                    Подготовить сводку
                  </button>
                </>
              )}
              <button
                type="button"
                className="text-link"
                onClick={() => setChoosing(false)}
              >
                Отмена
              </button>
            </form>
          )}
        </>
      )}
      {brief?.configured && (
        <>
          {brief.result && (
            <p className="briefing-since">
              После «{brief.result.previous_title}» ·{" "}
              {new Date(brief.result.since).toLocaleDateString("ru-RU")}
            </p>
          )}
          {busy && (
            <p role="status">
              ИИ сравнивает факты. Можно{" "}
              {inCall ? "продолжать разговор" : "войти в звонок"}, не дожидаясь
              результата.
            </p>
          )}
          {brief.status === "error" && (
            <p className="live-warning" role="alert">
              {brief.error === "PREVIOUS_UNAVAILABLE"
                ? "Предыдущая встреча недоступна."
                : "ИИ-сравнение не выполнено. Проверьте Ollama и повторите. Доступные сроки рассчитаны по поручениям."}
            </p>
          )}
          {brief.stale && !busy && brief.status !== "error" && (
            <p className="live-warning">
              Данные изменились после подготовки сводки.{" "}
              {host && !ended
                ? "Нажмите «Обновить»."
                : "Попросите организатора обновить сводку."}
            </p>
          )}
          {!!brief.result?.items.length && (
            <ul className="briefing-items">
              {brief.result.items.map((item, index) => (
                <li key={`${item.category}:${index}`}>
                  <span className={`briefing-category ${item.category}`}>
                    {categories[item.category]}
                  </span>
                  <p>{item.text}</p>
                  {item.deadline && (
                    <p className="briefing-hint">
                      {item.responsible || "Ответственный не указан"} · срок{" "}
                      {new Date(item.deadline).toLocaleDateString("ru-RU")}
                    </p>
                  )}
                  <details>
                    <summary>На основании чего</summary>
                    {item.previous && (
                      <p className="briefing-hint">
                        На прошлом созвоне срок ещё не был сорван
                        {item.previous.deadline
                          ? `: ${new Date(item.previous.deadline).toLocaleDateString("ru-RU")}`
                          : ": срок не был указан"}
                        .
                      </p>
                    )}
                    {item.evidence.map((e, i) => (
                      <blockquote key={i}>
                        <span>
                          {e.label}
                          {typeof e.start === "number"
                            ? ` · ${Math.floor(e.start / 60)}:${String(Math.floor(e.start % 60)).padStart(2, "0")}`
                            : ""}
                        </span>
                        <p>{e.quote}</p>
                      </blockquote>
                    ))}
                  </details>
                </li>
              ))}
            </ul>
          )}
          {brief.status === "ready" &&
            !brief.stale &&
            !brief.result?.items.length && (
              <p className="briefing-empty">
                В доступных данных подтверждённых изменений и открытых вопросов
                не найдено.
              </p>
            )}
          {!!brief.result?.remaining && (
            <p className="briefing-hint">
              Ещё {brief.result.remaining} пунктов не вошли в короткую сводку.
              Проверьте поручения прошлого созвона.
            </p>
          )}
          {!!brief.result?.warnings.length && (
            <details className="briefing-coverage">
              <summary>Что учтено и чего не хватает</summary>
              <ul>
                {brief.result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          {brief.generated_at && !brief.stale && (
            <p className="briefing-hint">
              Обновлено {new Date(brief.generated_at).toLocaleString("ru-RU")}
            </p>
          )}
          {host && !ended && (
            <>
              {!editing ? (
                <button
                  className="text-link"
                  onClick={() => {
                    setNotes(brief.updates || "");
                    setEditing(true);
                  }}
                >
                  Добавить события после созвона
                </button>
              ) : (
                <form
                  className="briefing-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void save(notes);
                  }}
                >
                  <label>
                    Что произошло после созвона?
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      maxLength={2000}
                      rows={3}
                    />
                  </label>
                  <p className="briefing-hint">
                    Укажите реальные факты: новые препятствия, изменённые
                    решения, ответы на открытые вопросы. Эти заметки
                    используются как источник для участников встречи.
                  </p>
                  <div className="live-inline-actions">
                    <button className="primary" disabled={busy}>
                      Сохранить и обновить
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
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
