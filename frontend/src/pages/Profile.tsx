import { useRef, useState, type ReactNode } from "react";
import { api, requestId, waitForOperation } from "../lib/api";
import { useMe } from "../lib/me";
import { timeAgo } from "../lib/format";
import { Shell } from "../components/Shell";
import { ProfileAnswers } from "../components/ProfileAnswers";
import { Badge, Empty, Spinner, useToast } from "../components/ui";
import { IBrain, ICheck, IFile, IShield, IUpload } from "../components/Icons";

export function ProfilePage() {
  const { me, reload } = useMe();
  const toast = useToast();
  const [over, setOver] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [improve, setImprove] = useState<any>(null);
  const [improving, setImproving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const profile = me?.profile;
  const f = profile?.facts || {};

  async function upload(file: File) {
    if (!/\.(pdf|docx)$/i.test(file.name)) return toast("Please upload a PDF or DOCX.", "error");
    if (file.size > 5 * 1024 * 1024) return toast("Resume must be under 5 MB.", "error");
    try {
      setStatus("Getting a secure upload link…");
      const { resume_id, upload: post } = await api("/api/resume/upload-url", { body: { filename: file.name, size: file.size } });
      const form = new FormData();
      Object.entries(post.fields as Record<string, string>).forEach(([k, v]) => form.append(k, v));
      form.append("file", file);
      setStatus("Uploading to private storage…");
      const up = await fetch(post.url, { method: "POST", body: form });
      if (!up.ok) throw new Error("Upload failed");
      const { operation } = await api(`/api/resume/${resume_id}/process`, { body: { client_request_id: requestId("resume") } });
      const done = await waitForOperation(operation.op_id, (op) => setStatus(op.progress?.[op.progress.length - 1]?.message || "Processing…"));
      if (done.status === "failed") throw new Error(done.final?.error || "Could not read the resume");
      toast("Profile ready — please review the uncertain fields.", "success");
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setStatus(null);
    }
  }

  async function save() {
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(draft)) patch[k] = v;
    try {
      await api("/api/profile", { method: "PATCH", body: patch });
      toast("Saved as a new profile version. Earlier applications keep their original version.", "success");
      setEditing(false);
      setDraft({});
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  async function runImprove() {
    setImproving(true);
    try {
      const { operation } = await api("/api/resume/improve", { body: { client_request_id: requestId("improve") } });
      const done = await waitForOperation(operation.op_id, () => {});
      if (done.status === "failed") throw new Error(done.final?.error);
      setImprove(done.final);
    } catch (e) {
      toast((e as Error).message || "Could not generate suggestions", "error");
    } finally {
      setImproving(false);
    }
  }

  function downloadRevision() {
    const blob = new Blob([improve?.revised_resume_markdown || ""], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "resume-revision.md";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const fields: [string, string][] = [["name", "Name"], ["email", "Email"], ["phone", "Phone"], ["location", "Location"], ["headline", "Headline"]];

  return (
    <Shell title="Profile">
      <div className="page-head">
        <div><h1>Your verified profile</h1><p>Facts come from your resume with evidence. Corrections create a new version; nothing is invented.</p></div>
        {profile && <Badge tone="violet">Version {profile.version} · {timeAgo(profile.created_at)}</Badge>}
      </div>

      <div className="split profile">
        <div className="stack">
          {me?.example_workspace ? (
            <div className="banner info"><IShield size={18} /> Example workspace: Aarav Mehta is a fictional applicant. Uploading your own resume requires your own account.</div>
          ) : (
            <div
              className={`dropzone glass-stripe ${over ? "over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); const file = e.dataTransfer.files[0]; if (file) upload(file); }}
              onClick={() => fileRef.current?.click()}
              role="button"
              tabIndex={0}
            >
              <input ref={fileRef} type="file" accept=".pdf,.docx" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
              <div className="empty" style={{ padding: 0 }}>
                <div className="art">{status ? <Spinner /> : <IUpload />}</div>
                <div style={{ color: "var(--ink)", fontWeight: 700 }}>{status || (profile ? "Upload a newer resume" : "Drop your resume here")}</div>
                <div className="small">PDF or DOCX · up to 5 MB · stored privately, encrypted</div>
              </div>
            </div>
          )}

          {!profile ? (
            <div className="card glass-stripe"><Empty icon={<IFile />} title="No profile yet">Upload a resume to extract facts with evidence.</Empty></div>
          ) : (
            <div className="card pad glass-stripe">
              <div className="card-title">
                <h3>Basics</h3>
                {!me?.example_workspace && (editing ? <div className="row"><button className="btn ghost sm" onClick={() => { setEditing(false); setDraft({}); }}>Cancel</button><button className="btn primary sm" onClick={save}>Save version</button></div>
                  : <button className="btn sm" onClick={() => setEditing(true)}>Correct facts</button>)}
              </div>
              <div className="grid g2">
                {fields.map(([k, label]) => (
                  <div key={k}>
                    <div className="label">{label} {(f.uncertain || []).includes(k) && <Badge tone="amber">check</Badge>}</div>
                    {editing ? <input className="input input-glow" defaultValue={f[k] || ""} onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} /> : <div>{f[k] || <span className="muted">—</span>}</div>}
                  </div>
                ))}
                <div>
                  <div className="label">Work authorization <Badge tone={f.work_authorization?.verified ? "mint" : "amber"}>{f.work_authorization?.verified ? "confirmed by you" : "never inferred"}</Badge></div>
                  {editing ? <input className="input input-glow" placeholder="e.g. Yes, authorized to work in India" onChange={(e) => setDraft((d) => ({ ...d, work_authorization: e.target.value }))} /> : <div>{f.work_authorization?.value || <span className="muted">Ask me when an employer requires it</span>}</div>}
                </div>
              </div>
              <div className="divider" />
              <Section title="Education" items={f.education} render={(e: any) => <><b>{e.school}</b> · {e.degree} {e.field} {e.graduation_year && <Badge>{e.graduation_year}</Badge>}</>} />
              <Section title="Experience" items={f.experience} render={(e: any) => <><b>{e.title}</b> · {e.company} <span className="muted small">{e.start}–{e.end || "present"}</span></>} />
              <Section title="Projects" items={f.projects} render={(e: any) => <><b>{e.name}</b> <span className="muted small">{e.description}</span></>} />
              <div className="eyebrow" style={{ margin: "14px 0 8px" }}>Skills</div>
              <div className="row wrap" style={{ gap: 6 }}>{(f.skills || []).map((s: any) => <Badge key={s.name} tone={s.verified ? "mint" : "amber"} title={s.evidence}>{s.verified && <ICheck size={12} />}{s.name}</Badge>)}</div>
            </div>
          )}
        </div>

        <div className="stack">
          <div className="card pad glass-stripe">
            <div className="card-title"><h3><IBrain size={16} /> Resume improvement</h3><button className="btn sm primary" onClick={runImprove} disabled={improving || !profile}>{improving && <Spinner />} Suggest edits</button></div>
            <p className="small muted">Readability and evidence gaps. Suggestions never add qualifications — missing details become questions for you.</p>
            {(f.suggestions || []).slice(0, 3).map((s: any, i: number) => (
              <div key={i} className="evidence" style={{ marginTop: 10 }}><b>{s.section}:</b> {s.issue}. {s.suggestion}</div>
            ))}
            {improve && (
              <div className="fade-in" style={{ marginTop: 14 }}>
                {(improve.edits || []).map((e: any, i: number) => (
                  <div key={i} className="card pad glass-stripe" style={{ marginTop: 10, padding: 14 }}>
                    <div className="eyebrow">{e.section}</div>
                    <div className="small" style={{ color: "#fecdd3", textDecoration: "line-through", marginTop: 6 }}>{e.before}</div>
                    <div className="small" style={{ color: "#a7f3d0", marginTop: 6 }}>{e.after}</div>
                    <div className="tiny muted" style={{ marginTop: 6 }}>{e.reason}</div>
                  </div>
                ))}
                {(improve.questions_for_user || []).length > 0 && (
                  <div className="banner" style={{ marginTop: 12, display: "block" }}><b>Questions for you:</b><ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{improve.questions_for_user.map((q: string) => <li key={q}>{q}</li>)}</ul></div>
                )}
                {improve.revised_resume_markdown && <button className="btn" style={{ marginTop: 12 }} onClick={downloadRevision}><IFile size={16} /> Download revision</button>}
              </div>
            )}
          </div>
          <ProfileAnswers answers={profile?.saved_answers || {}} enabled={!!profile && !me?.example_workspace} onSave={reload} />
        </div>
      </div>
    </Shell>
  );
}

function Section({ title, items, render }: { title: string; items?: any[]; render: (x: any) => ReactNode }) {
  if (!items?.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      <div className="col" style={{ gap: 8 }}>
        {items.map((it, i) => (
          <div key={i} className="small">
            <div className="row wrap" style={{ gap: 6 }}>{render(it)} <Badge tone={it.verified ? "mint" : "amber"}>{it.verified ? "evidenced" : "unverified"}</Badge></div>
            {it.evidence && <div className="tiny muted" style={{ marginTop: 3 }}>“{it.evidence}”</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
