"use client";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Plus, Trash2, ArrowLeft, ArrowRight } from "./icons";
import { localDay } from "@/lib/domain";
import type { Meeting } from "@/lib/types";

export function CreateMeeting({
  open,
  onOpenChange,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreate: (m: Meeting) => void;
}) {
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(localDay() + "T10:00");
  const [agenda, setAgenda] = useState("");
  const [people, setPeople] = useState([{ name: "", department: "" }]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="meeting-dialog">
        <DialogHeader>
          <div className="form-step-label">Шаг {step} из 2</div>
          <DialogTitle>
            {step === 1
              ? "О чём будет встреча?"
              : "Кто участвует и что обсудим?"}
          </DialogTitle>
          <DialogDescription>
            {step === 1
              ? "Начните с темы и времени. Участников добавим на следующем шаге."
              : "Добавьте хотя бы одного участника и один вопрос повестки."}
          </DialogDescription>
        </DialogHeader>
        <div className="form-step-track" aria-hidden="true">
          <i />
          <i className={step === 2 ? "filled" : ""} />
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (step === 1) {
              setStep(2);
              return;
            }
            const questions = agenda
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean);
            if (!questions.length) {
              const field = e.currentTarget.elements.namedItem(
                "agenda",
              ) as HTMLTextAreaElement;
              field.setCustomValidity("Напишите хотя бы один вопрос.");
              field.reportValidity();
              return;
            }
            onCreate({
              id: crypto.randomUUID(),
              title: title.trim(),
              date,
              agenda: questions,
              participants: people.map((p) => ({
                ...p,
                name: p.name.trim(),
                department: p.department.trim(),
                id: crypto.randomUUID(),
              })),
              transcript: [],
            });
          }}
        >
          {step === 1 ? (
            <>
              <label>
                Тема встречи
                <input
                  key="title"
                  autoFocus
                  name="title"
                  required
                  pattern={".*\\S.*"}
                  maxLength={180}
                  placeholder="Например, планы команды на октябрь"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                Когда встречаемся?
                <input
                  type="datetime-local"
                  required
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
              <div className="form-footer">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onOpenChange(false)}
                >
                  Отмена
                </button>
                <button type="submit" className="primary">
                  Далее <ArrowRight size={16} />
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="meeting-summary">
                <strong>{title}</strong>
                <span>
                  {new Date(date).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "long",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div className="form-subhead">Участники</div>
              {people.map((p, i) => (
                <div className="participant-inputs" key={i}>
                  <label>
                    Имя и фамилия
                    <input
                      autoFocus={i === 0}
                      aria-label={`Имя участника ${i + 1}`}
                      required
                      pattern={".*\\S.*"}
                      placeholder="Например, Анна Смирнова"
                      value={p.name}
                      onChange={(e) =>
                        setPeople(
                          people.map((x, n) =>
                            n === i ? { ...x, name: e.target.value } : x,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    Подразделение
                    <input
                      aria-label={`Подразделение участника ${i + 1}`}
                      required
                      pattern={".*\\S.*"}
                      placeholder="Например, отдел развития"
                      value={p.department}
                      onChange={(e) =>
                        setPeople(
                          people.map((x, n) =>
                            n === i ? { ...x, department: e.target.value } : x,
                          ),
                        )
                      }
                    />
                  </label>
                  {people.length > 1 && (
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Удалить участника ${i + 1}`}
                      onClick={() =>
                        setPeople(people.filter((_, n) => n !== i))
                      }
                    >
                      <Trash2 size={17} />
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                className="text-link add-person"
                onClick={() =>
                  setPeople([...people, { name: "", department: "" }])
                }
              >
                <Plus size={16} />
                Ещё участник
              </button>
              <label>
                Что обсудим?
                <textarea
                  name="agenda"
                  required
                  rows={3}
                  value={agenda}
                  placeholder="Итоги недели\nПланы на следующий месяц"
                  onChange={(e) => {
                    e.currentTarget.setCustomValidity("");
                    setAgenda(e.target.value);
                  }}
                />
                <span className="form-hint">
                  Каждый вопрос — с новой строки.
                </span>
              </label>
              <div className="form-footer">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setStep(1)}
                >
                  <ArrowLeft size={16} />
                  Назад
                </button>
                <button type="submit" className="primary">
                  Создать совещание
                </button>
              </div>
            </>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
