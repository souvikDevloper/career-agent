import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { Link } from "../lib/router";
import { dateTime, timeAgo } from "../lib/format";
import { Shell } from "../components/Shell";
import { Badge, Empty } from "../components/ui";
import { ICheck, IClock, IList } from "../components/Icons";

type Task = { task_id: string; app_id: string; title: string; due?: string; kind: string; status: string; note?: string; created_at: string; source_message?: string };

export function TasksPage() {
  const { data, reload } = useApi<{ tasks: Task[] }>("/api/tasks", [], 6000);
  const tasks = data?.tasks || [];
  const open = tasks.filter((t) => t.status === "open").sort((a, b) => (a.due || "9") < (b.due || "9") ? -1 : 1);
  const done = tasks.filter((t) => t.status !== "open");
  const update = async (t: Task, status: string) => { await api(`/api/tasks/${t.task_id}`, { method: "PATCH", body: { status } }); reload(); };

  return (
    <Shell title="Tasks">
      <div className="page-head">
        <div><h1>Assessments, interviews & reminders</h1><p>Created from employer messages with the deadline quoted from the message. Reminders are cancelled when you complete a task.</p></div>
      </div>
      <div className="grid g2">
        <div className="card pad">
          <div className="card-title"><h3><IClock size={16} /> Open</h3><Badge tone="amber">{open.length}</Badge></div>
          {open.length === 0 ? <Empty icon={<IList />} title="All clear">Tasks appear when an employer invites you to an assessment or interview.</Empty> : (
            <div className="col">
              {open.map((t) => {
                const overdue = t.due && new Date(t.due).getTime() < Date.now();
                return (
                  <div key={t.task_id} className="app-card" style={{ cursor: "default" }}>
                    <div className="row between"><h5>{t.title}</h5><Badge tone={t.kind === "assessment_invite" ? "amber" : t.kind === "interview_invite" ? "violet" : "cyan"}>{t.kind.replace(/_/g, " ")}</Badge></div>
                    {t.note && <p className="small muted" style={{ marginTop: 4 }}>{t.note}</p>}
                    <div className="row between" style={{ marginTop: 10 }}>
                      <span className="small" style={{ color: overdue ? "var(--rose)" : "var(--amber)" }}>{t.due ? `Due ${dateTime(t.due)}` : "No deadline"}</span>
                      <div className="row">
                        <Link to={`/app/applications/${t.app_id}`} className="btn ghost sm">Open</Link>
                        <button className="btn sm success" onClick={() => update(t, "done")}><ICheck size={14} /> Done</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="card pad">
          <div className="card-title"><h3><ICheck size={16} /> Completed</h3><Badge tone="mint">{done.length}</Badge></div>
          {done.length === 0 ? <p className="muted small">Nothing completed yet.</p> : done.map((t) => (
            <div key={t.task_id} className="row between small" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
              <span style={{ textDecoration: "line-through", color: "var(--muted)" }}>{t.title}</span>
              <button className="btn ghost sm" onClick={() => update(t, "open")}>Reopen · {timeAgo(t.created_at)}</button>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}
