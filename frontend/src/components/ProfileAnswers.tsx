import { useState } from "react";
import { api } from "../lib/api";
import { Badge, Spinner, useToast } from "./ui";

const SUGGESTIONS = ["Country", "Address Line 1", "City", "State", "Postal Code", "Phone Device Type", "How Did You Hear About Us?", "Earliest start date", "Notice period"];

export function ProfileAnswers({ answers, enabled, onSave }: { answers: Record<string, string>; enabled: boolean; onSave: () => Promise<void> }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  async function save() {
    if (!question.trim() || !answer.trim()) return;
    setBusy(true);
    try {
      await api("/api/profile/answers", { method: "PUT", body: { answers: { [question.trim()]: answer.trim() } } });
      setQuestion(""); setAnswer(""); await onSave();
      toast("Answer saved for matching employer questions. Waiting applications will use it when prepared again.", "success");
    } catch (error) { toast((error as Error).message, "error"); }
    finally { setBusy(false); }
  }
  return <div className="card pad glass-stripe">
    <div className="card-title"><h3>Application answers</h3><Badge>{Object.keys(answers).length}</Badge></div>
    <p className="small muted">Save address details, notice period and exact screening answers before you apply. Copy an employer’s full question for sponsorship, qualifications or declarations so the answer is reused only for that question.</p>
    {enabled && <div className="col" style={{ gap: 10 }}>
      <label className="label" htmlFor="application-question">Employer question</label>
      <input id="application-question" className="input" maxLength={600} list="application-answer-questions" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Select a common field or paste the full question" />
      <datalist id="application-answer-questions">{SUGGESTIONS.map((label) => <option key={label} value={label} />)}</datalist>
      <label className="label" htmlFor="application-answer">Your answer</label>
      <textarea id="application-answer" className="input" maxLength={2000} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Use the employer’s option wording for a dropdown answer" />
      <button className="btn primary" disabled={busy || !question.trim() || !answer.trim()} onClick={save}>{busy && <Spinner />}Save answer</button>
    </div>}
    <div className="col" style={{ marginTop: 16, gap: 10 }}>
      {Object.entries(answers).map(([q, a]) => <div key={q} className="answer" style={{ gridTemplateColumns: "1fr auto" }}>
        <div><div className="k small">{q}</div><div className="v small">{a}</div></div>
        {enabled && <button className="btn ghost sm" onClick={() => { setQuestion(q); setAnswer(a); }}>Edit</button>}
      </div>)}
    </div>
  </div>;
}
