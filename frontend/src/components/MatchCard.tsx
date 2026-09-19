import type { MatchCard as M } from "../lib/api";
import { timeAgo } from "../lib/format";
import { IArrow, IBuilding, IClock, IPin } from "./Icons";
import { Badge, Bar, EnvBadge, ScoreRing } from "./ui";
import SpotlightCard from "./motion/SpotlightCard";
import { SpeakButton } from "./SpeakButton";
import KineticScoreGauge from "./motion/KineticScoreGauge";

function evidenceLabel(extractor?: string): string {
  if (!extractor || extractor.startsWith("heuristic")) return "Provisional keyword estimate";
  const [provider, ...modelParts] = extractor.split(":");
  const model = modelParts.join(":").toLowerCase();
  if (provider === "bedrock") return model.includes("nova") ? "Evidence by Amazon Nova" : "Evidence by Amazon Bedrock";
  if (provider === "anthropic") return model.includes("claude") ? "Evidence by Claude" : "Evidence by Anthropic";
  if (provider === "openai") return "Evidence by configured AI model";
  return "Model evidence";
}

export function MatchRow({ m, onOpen }: { m: M; onOpen: () => void }) {
  const req = (m.skills || []).filter((s) => s.required);
  const hit = req.filter((s) => s.evidence).length;
  const glowClass = m.score >= 85 ? "glow-high" : m.score >= 65 ? "glow-mid" : "glow-low";
  return (
    <SpotlightCard className={`card hover match fade-in cursor-pointer ${glowClass}`} onClick={onOpen} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen()}>
      <div className="row" style={{ width: "100%", gap: 16, alignItems: "center" }}>
        <ScoreRing score={m.score} />
        <div style={{ minWidth: 0, flex: 1 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <h4>{m.job.title}</h4>
          <EnvBadge env={m.job.environment} />
          {m.blocked && <Badge tone="rose">Not eligible</Badge>}
          {!m.blocked && m.unknowns?.length > 0 && <Badge tone="amber">Needs info</Badge>}
          {m.extractor?.startsWith("heuristic") && <Badge tone="amber">Provisional score</Badge>}
        </div>
        <div className="co row wrap" style={{ gap: 14 }}>
          <span className="row" style={{ gap: 5 }}><IBuilding size={14} /> {m.job.company}</span>
          {m.job.location && <span className="row" style={{ gap: 5 }}><IPin size={14} /> {m.job.location}</span>}
          {/* When the employer posted it is what decides whether it is worth
              applying to; when we first saw it is our bookkeeping. Show theirs
              when the board gives us one, and fall back to ours when it does not. */}
          <span className="row" style={{ gap: 5 }}>
            <IClock size={14} />
            {m.job.published_at ? `posted ${timeAgo(m.job.published_at)}` : `seen ${timeAgo(m.job.first_seen_at || m.created_at)}`}
          </span>
        </div>
        {m.explanation && <p className="small ink2" style={{ marginTop: 8, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{m.explanation}</p>}
      </div>
        <div className="col" style={{ alignItems: "flex-end", gap: 8 }}>
          <span className="small muted">{req.length ? `${hit}/${req.length} must-haves evidenced` : "—"}</span>
          <span className="btn sm">Explain <IArrow size={14} /></span>
          {/* The card itself opens the match, so the speak control has to stop the
              click here or listening would navigate away from what you asked to hear. */}
          <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
            <SpeakButton
              label="Listen"
              text={`${m.job.title} at ${m.job.company}${m.job.location ? `, ${m.job.location}` : ""}. Fit ${m.score} out of 100. ${m.explanation || ""}`}
            />
          </span>
        </div>
      </div>
    </SpotlightCard>
  );
}

const COMPONENT_LABEL: Record<string, [string, number]> = {
  required_skills: ["Required skills", 40],
  experience: ["Project / experience evidence", 30],
  responsibilities: ["Role responsibilities", 20],
  preferences: ["Your preferences", 10],
};

export function MatchExplain({ m }: { m: M }) {
  return (
    <div className="stack">
      <div className="row" style={{ gap: 18, alignItems: "center" }}>
        <KineticScoreGauge score={m.score} size="lg" />
        <div>
          <div className="eyebrow">Explained fit · {m.rubric_version}</div>
          <h2 style={{ fontSize: 24, marginTop: 4 }}>{m.job.title}</h2>
          <div className="ink2">{m.job.company} · {m.job.location}</div>
          <div className="row wrap" style={{ marginTop: 8 }}>
            <EnvBadge env={m.job.environment} />
            <Badge tone={m.auto_eligible ? "mint" : "amber"}>{m.auto_eligible ? "Eligible for automation" : "Review required"}</Badge>
            <span title={m.extractor || "Evidence source unavailable"}><Badge>{evidenceLabel(m.extractor)}</Badge></span>
          </div>
        </div>
      </div>
      {m.explanation && (
        <div className="card pad glass-stripe" style={{ background: "var(--grad-soft)" }}>
          <p className="ink2">{m.explanation}</p>
          {/* The full reasoning is the longest thing on this screen and the part
              worth hearing while looking at the posting in another tab. */}
          <div className="row" style={{ marginTop: 10 }}>
            <SpeakButton
              label="Read this explanation"
              text={`${m.job.title} at ${m.job.company}. Fit ${m.score} out of 100. ${m.explanation}`}
            />
          </div>
        </div>
      )}

      <div>
        <div className="eyebrow" style={{ marginBottom: 10 }}>How the score adds up</div>
        <div className="col" style={{ gap: 10 }}>
          {Object.entries(COMPONENT_LABEL).map(([k, [label, max]]) => (
            <Bar key={k} label={label} value={Math.round(m.components?.[k] ?? 0)} max={max} />
          ))}
        </div>
        <p className="tiny muted" style={{ marginTop: 8 }}>Our own rubric — not an employer ATS score or a probability of an interview. Missing evidence lowers fit.</p>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Eligibility checks</div>
        {(m.filters || []).length === 0 && <p className="muted small">No hard constraints set.</p>}
        {(m.filters || []).map((f) => (
          <div key={f.check} className="check-row">
            <span className={`status-ic ${f.status}`}>{f.status === "pass" ? "✓" : f.status === "fail" ? "✕" : "?"}</span>
            <div>
              <div style={{ fontWeight: 600, textTransform: "capitalize" }}>{f.check.replace(/_/g, " ")} {!f.mandatory && <span className="muted tiny">(preference)</span>}</div>
              <div className="muted small">{f.detail}</div>
            </div>
          </div>
        ))}
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Requirement evidence from your resume</div>
        {(m.skills || []).map((s) => (
          <div key={s.skill + String(s.required)} className="check-row">
            <span className={`status-ic ${s.evidence ? "pass" : s.required ? "fail" : "unknown"}`}>{s.evidence ? "✓" : s.required ? "✕" : "–"}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{s.skill} <span className="muted tiny">{s.required ? "must-have" : "nice-to-have"}</span></div>
              {s.evidence ? <div className="evidence" style={{ marginTop: 6 }}>“{s.evidence}”</div> : <div className="muted small">No supporting passage found.</div>}
            </div>
          </div>
        ))}
        {(m.experience_evidence || []).length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Relevant experience</div>
            <div className="col">{m.experience_evidence!.map((q) => <div key={q} className="evidence">“{q}”</div>)}</div>
          </div>
        )}
      </div>

      {m.unknowns?.length > 0 && (
        <div className="banner"><span>We won't guess: {m.unknowns.join("; ")}</span></div>
      )}
      {m.job.description && (
        <details>
          <summary className="small" style={{ cursor: "pointer", color: "var(--ink-2)" }}>Job description</summary>
          <p className="small ink2" style={{ whiteSpace: "pre-wrap", marginTop: 10 }}>{m.job.description}</p>
        </details>
      )}
    </div>
  );
}
