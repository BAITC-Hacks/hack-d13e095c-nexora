"use client";
import { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Plus,
  Trash2,
  Sparkles,
  Printer,
  Check,
  FileText,
  ArrowLeft,
  Users,
  CalendarDays,
} from "./icons";
import { toast } from "sonner";
import { Recorder } from "./recorder";
import { Badge, Choice, Empty, initials, countLabel } from "./widgets";
import { recognizeDemo } from "@/lib/demo-recognition";
import { newAssignment, protocolErrors } from "@/lib/domain";
import type { Meeting, Protocol } from "@/lib/types";
export function MeetingDetail({
  meeting,
  onChange,
  onBack,
  onApprove,
  onBusy,
  busy,
}: {
  meeting: Meeting;
  onChange: (m: Meeting) => void;
  onBack: () => void;
  onApprove: () => void;
  onBusy: (v: boolean) => void;
  busy: boolean;
}) {
  const [tab, setTab] = useState(meeting.protocol ? "protocol" : "overview"),
    [processing, setProcessing] = useState(false),
    [errors, setErrors] = useState<string[]>([]);
  const approved = !!meeting.protocol?.approvedAt;
  const [recordOpen, setRecordOpen] = useState(!meeting.protocol);
  function updateProtocol(p: Protocol) {
    setErrors([]);
    onChange({ ...meeting, protocol: p });
  }
  async function generate() {
    if (meeting.protocol) return;
    setProcessing(true);
    onBusy(true);
    try {
      const result = await recognizeDemo(meeting);
      onChange({ ...meeting, ...result });
      setTab("protocol");
      toast.success("Демонстрационный проект протокола готов");
    } catch {
      toast.error("Не удалось сформировать проект. Повторите попытку.");
    } finally {
      setProcessing(false);
      onBusy(false);
    }
  }
  return (
    <>
      <button className="text-link back-link no-print" onClick={onBack}>
        <ArrowLeft size={15} />К совещаниям
      </button>
      <div className="detail-title">
        <div>
          <div className="eyebrow">СОВЕЩАНИЕ</div>
          <h1>{meeting.title}</h1>
          <div className="detail-meta">
            <span>
              <CalendarDays size={15} />
              {new Date(meeting.date).toLocaleString("ru-RU", {
                day: "numeric",
                month: "long",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <span>
              <Users size={15} />
              {countLabel(meeting.participants.length, [
                "участник",
                "участника",
                "участников",
              ])}
            </span>
            <Badge
              status={
                approved ? "approved" : meeting.protocol ? "review" : "planned"
              }
            />
          </div>
        </div>
        {approved && (
          <button
            className="secondary no-print"
            onClick={() => {
              setTab("protocol");
              setTimeout(() => window.print(), 150);
            }}
          >
            <Printer size={16} />
            Печать
          </button>
        )}
      </div>
      <div className="no-print">
        <button
          className="record-disclosure"
          aria-expanded={recordOpen || busy}
          aria-controls="meeting-recording"
          disabled={busy}
          onClick={() => setRecordOpen(!recordOpen)}
        >
          <span>
            Аудиозапись{" "}
            <small>
              {meeting.audio ? "Запись сохранена" : "Можно записать встречу"}
            </small>
          </span>
          <span>{recordOpen || busy ? "Свернуть" : "Открыть"}</span>
        </button>
        <div id="meeting-recording" hidden={!recordOpen && !busy}>
          <Recorder
            externalBusy={processing}
            meeting={meeting}
            onSave={(audio, audioSeconds) =>
              onChange({ ...meeting, audio, audioSeconds })
            }
            onBusy={onBusy}
          />
        </div>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="detail-tabs">
        <TabsList variant="line" className="no-print">
          <TabsTrigger value="overview">Повестка и участники</TabsTrigger>
          <TabsTrigger value="transcript">Расшифровка</TabsTrigger>
          <TabsTrigger value="protocol">
            Протокол {meeting.protocol && <span className="tab-dot" />}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <section className="panel overview-grid">
            <div>
              <h2>Повестка совещания</h2>
              {meeting.agenda.map((a, i) => (
                <div className="agenda-item" key={i}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <p>{a}</p>
                </div>
              ))}
            </div>
            <div>
              <h2>Участники</h2>
              {meeting.participants.map((p) => (
                <div className="participant" key={p.id}>
                  <span className="avatar">{initials(p.name)}</span>
                  <div>
                    {p.name}
                    <small>{p.department}</small>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </TabsContent>
        <TabsContent value="transcript">
          <section className="panel">
            <div className="section-heading">
              <h2>Расшифровка совещания</h2>
              <span className="badge">Демоданные</span>
            </div>
            <div className="demo-disclaimer">
              Демонстрационный текст. Аудиозапись не отправляется на
              распознавание.
            </div>
            {meeting.transcript.length ? (
              meeting.transcript.map((t) => (
                <article className="transcript-line" key={t.id}>
                  <span className="avatar">{initials(t.speaker)}</span>
                  <div>
                    <h3>
                      {t.speaker}
                      <time>{t.time}</time>
                    </h3>
                    <p>{t.text}</p>
                  </div>
                </article>
              ))
            ) : (
              <Empty
                title="Расшифровка ещё не создана"
                description="Запустите демонстрационное распознавание ниже."
              />
            )}
          </section>
        </TabsContent>
        <TabsContent value="protocol">
          {meeting.protocol ? (
            <section className="panel protocol-panel">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">
                    {approved ? "УТВЕРЖДЁННЫЙ ДОКУМЕНТ" : "ПРОЕКТ ДОКУМЕНТА"}
                  </div>
                  <h2>Протокол совещания</h2>
                </div>
                <span className="badge">Демоданные</span>
              </div>
              <div className="protocol-body">
                <p className="protocol-participants">
                  <strong>Участники: </strong>
                  {meeting.participants
                    .map((p) => `${p.name} (${p.department})`)
                    .join("; ")}
                </p>
                <p className="demo-disclaimer">
                  {approved
                    ? `Утверждён ${new Date(meeting.protocol.approvedAt!).toLocaleString("ru-RU")}. Поручения доступны в разделе контроля.`
                    : "Проверьте решения, ответственных и сроки. Демонстрационный ИИ использует повестку, а не содержание аудио."}
                </p>
                <div className="protocol-fields">
                  {approved ? (
                    <>
                      <h3>Основные вопросы</h3>
                      <p className="preserve-lines">
                        {meeting.protocol.themes}
                      </p>
                      <h3>Принятые решения</h3>
                      <p className="preserve-lines">
                        {meeting.protocol.decisions}
                      </p>
                    </>
                  ) : (
                    <>
                      <label>
                        Основные вопросы
                        <textarea
                          rows={3}
                          value={meeting.protocol.themes}
                          onChange={(e) =>
                            updateProtocol({
                              ...meeting.protocol!,
                              themes: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        Принятые решения
                        <textarea
                          rows={4}
                          value={meeting.protocol.decisions}
                          onChange={(e) =>
                            updateProtocol({
                              ...meeting.protocol!,
                              decisions: e.target.value,
                            })
                          }
                        />
                      </label>
                    </>
                  )}
                </div>
                <div className="section-heading assignments-heading">
                  <h2>
                    Поручения{" "}
                    <span className="number-count">
                      {meeting.protocol.assignments.length}
                    </span>
                  </h2>
                  {!approved && (
                    <button
                      className="text-link"
                      onClick={() =>
                        updateProtocol({
                          ...meeting.protocol!,
                          assignments: [
                            ...meeting.protocol!.assignments,
                            newAssignment(meeting),
                          ],
                        })
                      }
                    >
                      <Plus size={16} />
                      Добавить поручение
                    </button>
                  )}
                </div>
                {meeting.protocol.assignments.map((a, i) => (
                  <article className="assignment-editor" key={a.id}>
                    <div className="assignment-editor-heading">
                      <span>ПОРУЧЕНИЕ {String(i + 1).padStart(2, "0")}</span>
                      {!approved && (
                        <button
                          className="icon-button"
                          aria-label={`Удалить поручение ${i + 1}`}
                          onClick={() =>
                            updateProtocol({
                              ...meeting.protocol!,
                              assignments: meeting.protocol!.assignments.filter(
                                (x) => x.id !== a.id,
                              ),
                            })
                          }
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                    {approved ? (
                      <>
                        <h3>{a.text}</h3>
                        <dl className="approved-fields">
                          <div>
                            <dt>Ответственный</dt>
                            <dd>{a.assignee}</dd>
                          </div>
                          <div>
                            <dt>Срок исполнения</dt>
                            <dd>
                              {new Date(
                                a.deadline + "T12:00:00",
                              ).toLocaleDateString("ru-RU")}
                            </dd>
                          </div>
                          <div>
                            <dt>Подразделение</dt>
                            <dd>{a.department}</dd>
                          </div>
                          <div>
                            <dt>Инициатор</dt>
                            <dd>{a.initiator}</dd>
                          </div>
                          <div>
                            <dt>Вопрос повестки</dt>
                            <dd>{a.agenda}</dd>
                          </div>
                        </dl>
                      </>
                    ) : (
                      <>
                        <label>
                          Содержание поручения
                          <textarea
                            rows={2}
                            value={a.text}
                            onChange={(e) =>
                              updateProtocol({
                                ...meeting.protocol!,
                                assignments: meeting.protocol!.assignments.map(
                                  (x) =>
                                    x.id === a.id
                                      ? { ...x, text: e.target.value }
                                      : x,
                                ),
                              })
                            }
                          />
                        </label>
                        <div className="editor-grid">
                          {(
                            [
                              ["assignee", "Ответственный"],
                              ["deadline", "Срок исполнения"],
                              ["department", "Подразделение"],
                              ["initiator", "Инициатор"],
                              ["agenda", "Вопрос повестки"],
                            ] as const
                          ).map(([key, label]) => (
                            <label key={key}>
                              {label}
                              {key === "assignee" ? (
                                <Choice
                                  label={`Ответственный за поручение ${i + 1}`}
                                  value={a.assignee || "__empty"}
                                  items={[
                                    ["__empty", "Выберите ответственного"],
                                    ...meeting.participants.map(
                                      (p) =>
                                        [p.name, p.name] as [string, string],
                                    ),
                                  ]}
                                  onChange={(value) => {
                                    const p = meeting.participants.find(
                                      (p) => p.name === value,
                                    );
                                    updateProtocol({
                                      ...meeting.protocol!,
                                      assignments:
                                        meeting.protocol!.assignments.map(
                                          (x) =>
                                            x.id === a.id
                                              ? {
                                                  ...x,
                                                  assignee: p?.name || "",
                                                  department:
                                                    p?.department || "",
                                                }
                                              : x,
                                        ),
                                    });
                                  }}
                                />
                              ) : (
                                <input
                                  type={key === "deadline" ? "date" : "text"}
                                  value={a[key]}
                                  onChange={(e) =>
                                    updateProtocol({
                                      ...meeting.protocol!,
                                      assignments:
                                        meeting.protocol!.assignments.map(
                                          (x) =>
                                            x.id === a.id
                                              ? { ...x, [key]: e.target.value }
                                              : x,
                                        ),
                                    })
                                  }
                                />
                              )}
                            </label>
                          ))}
                        </div>
                      </>
                    )}
                  </article>
                ))}
                {!meeting.protocol.assignments.length && (
                  <p className="muted-note">
                    Поручения не добавлены. Можно утвердить протокол только с
                    решениями.
                  </p>
                )}
                {errors.length > 0 && (
                  <div role="alert" className="error-note">
                    {errors.map((e) => (
                      <p key={e}>{e}</p>
                    ))}
                  </div>
                )}
                {!approved && (
                  <div className="approve-bar no-print">
                    <span>
                      <Check size={15} />
                      Изменения сохраняются автоматически
                    </span>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => {
                        const found = protocolErrors(meeting);
                        setErrors(found);
                        if (!found.length) onApprove();
                      }}
                    >
                      <Check size={16} />
                      Утвердить протокол
                    </button>
                  </div>
                )}
              </div>
            </section>
          ) : (
            <section className="panel">
              <Empty
                title="Протокол ещё не сформирован"
                description="Запустите демораспознавание, чтобы получить редактируемый проект."
              />
            </section>
          )}
        </TabsContent>
      </Tabs>
      {!meeting.protocol && (
        <section className="recognition-bar no-print">
          <div>
            <Sparkles size={22} />
            <div>
              <h3>Попробуйте автоматическое протоколирование</h3>
              <p>Демонстрация на основе повестки. Аудио не анализируется.</p>
            </div>
          </div>
          <button
            className="primary"
            disabled={busy || processing}
            onClick={generate}
          >
            <Sparkles size={16} />
            {processing ? "Формируем проект…" : "Создать демопротокол"}
          </button>
        </section>
      )}
      {approved && tab !== "protocol" && (
        <p className="muted-note no-print">
          Для печати откройте вкладку «Протокол».
        </p>
      )}
    </>
  );
}
