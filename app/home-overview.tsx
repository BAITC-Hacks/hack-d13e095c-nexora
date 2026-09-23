import type { ReactNode } from "react";
import type { Assignment, Meeting } from "@/lib/types";
import { statusOf } from "@/lib/domain";
import { ArrowRight, CheckCircle2, FileText, Clock3 } from "./icons";
import { countLabel, dateText, Empty } from "./widgets";

export function HomeOverview({
  meetings,
  notices,
  onMeetings,
  onReview,
  onTasks,
  onTask,
  renderMeeting,
}: {
  meetings: Meeting[];
  notices: Assignment[];
  onMeetings: () => void;
  onReview: () => void;
  onTasks: () => void;
  onTask: (task: Assignment) => void;
  renderMeeting: (meeting: Meeting) => ReactNode;
}) {
  const drafts = meetings.filter((m) => m.protocol && !m.protocol.approvedAt);
  const overdue = notices.filter((a) => statusOf(a) === "overdue").length;
  return (
    <div className="simple-home">
      <section className="attention-strip" aria-label="Что требует внимания">
        <div className="attention-intro">
          <CheckCircle2 size={22} />
          <div>
            <h2>
              {drafts.length || notices.length
                ? "С чего начать"
                : "Всё в порядке"}
            </h2>
            <p>
              {drafts.length || notices.length
                ? "Выберите задачу — мы откроем нужный раздел."
                : "Протоколы проверены. Срочных поручений нет."}
            </p>
          </div>
        </div>
        {drafts.length > 0 && (
          <button className="attention-action" onClick={onReview}>
            <FileText size={19} />
            <span>
              <strong>Проверить протоколы</strong>
              <small>
                {countLabel(drafts.length, [
                  "документ готов",
                  "документа готовы",
                  "документов готовы",
                ])}
              </small>
            </span>
            <ArrowRight size={17} />
          </button>
        )}
        {notices.length > 0 && (
          <button className="attention-action" onClick={onTasks}>
            <Clock3 size={19} />
            <span>
              <strong>
                {overdue ? "Проверить сроки" : "Посмотреть задачи"}
              </strong>
              <small>
                {overdue
                  ? `${countLabel(overdue, ["поручение просрочено", "поручения просрочены", "поручений просрочено"])}`
                  : `${countLabel(notices.length, ["близкий срок", "близких срока", "близких сроков"])}`}
              </small>
            </span>
            <ArrowRight size={17} />
          </button>
        )}
      </section>
      <div className="home-columns">
        <section className="panel home-meetings">
          <div className="section-heading">
            <div>
              <h2>Ваши совещания</h2>
              <p className="section-description">
                Откройте встречу, чтобы продолжить работу.
              </p>
            </div>
            <button className="text-link" onClick={onMeetings}>
              Все встречи <ArrowRight size={15} />
            </button>
          </div>
          {meetings.length ? (
            [...meetings]
              .sort((a, b) => b.date.localeCompare(a.date))
              .slice(0, 5)
              .map(renderMeeting)
          ) : (
            <Empty
              title="Здесь будут ваши встречи"
              description="Нажмите «Новое совещание», добавьте тему и участников."
            />
          )}
        </section>
        <aside className="home-focus">
          <div className="section-heading">
            <div>
              <h2>Ближайшие задачи</h2>
              <p className="section-description">
                Просроченные и на ближайшие 3 дня
              </p>
            </div>
          </div>
          {notices.length ? (
            notices.slice(0, 4).map((a) => (
              <button
                className="focus-task"
                key={a.id}
                onClick={() => onTask(a)}
              >
                <span className="focus-task-date">
                  <span className={statusOf(a) === "overdue" ? "overdue" : ""}>
                    {dateText(a.deadline)}
                    {statusOf(a) === "overdue" ? " · Срок прошёл" : ""}
                  </span>
                  <ArrowRight size={15} />
                </span>
                <h3>{a.text}</h3>
                <p>{a.assignee}</p>
              </button>
            ))
          ) : (
            <Empty
              title="Можно выдохнуть"
              description="На ближайшие дни срочных задач нет."
            />
          )}
          {notices.length > 0 && (
            <button className="text-link focus-all" onClick={onTasks}>
              Открыть поручения <ArrowRight size={15} />
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}
