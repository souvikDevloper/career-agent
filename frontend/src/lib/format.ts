export function timeAgo(iso?: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function dateTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function scoreTone(score: number): string {
  // Deep enough to read as a ring stroke and as a numeral on a white card;
  // the previous values were tuned for a dark surface and washed out on light.
  if (score > 80) return "#4ade80";
  if (score >= 65) return "#4cc9f0";
  if (score >= 50) return "#fbbf24";
  return "#f472b6";
}

export const STATE_META: Record<string, { label: string; tone: string; lane: "action" | "progress" | "done" | "closed" }> = {
  Discovered: { label: "Discovered", tone: "violet", lane: "progress" },
  Ineligible: { label: "Not eligible", tone: "rose", lane: "closed" },
  Preparing: { label: "Preparing", tone: "cyan", lane: "progress" },
  NeedsInformation: { label: "Needs your answer", tone: "amber", lane: "action" },
  NeedsApproval: { label: "Awaiting approval", tone: "amber", lane: "action" },
  NeedsUserPresence: { label: "Browser ready", tone: "cyan", lane: "action" },
  ManualHandoff: { label: "Apply on site", tone: "amber", lane: "action" },
  Authorized: { label: "Authorized", tone: "cyan", lane: "progress" },
  Queued: { label: "Queued", tone: "cyan", lane: "progress" },
  Paused: { label: "Paused", tone: "amber", lane: "action" },
  Submitting: { label: "Submitting", tone: "violet", lane: "progress" },
  Submitted: { label: "Submitted", tone: "mint", lane: "done" },
  KnownFailure: { label: "Failed", tone: "rose", lane: "action" },
  OutcomeUnknown: { label: "Confirming", tone: "amber", lane: "progress" },
  NeedsReview: { label: "Check needed", tone: "rose", lane: "action" },
  Withdrawn: { label: "Withdrawn", tone: "", lane: "closed" },
};

export const STAGE_LABEL: Record<string, string> = {
  applied: "Applied",
  reply_received: "Reply received",
  assessment_invited: "Assessment invited",
  interview_scheduled: "Interview scheduled",
  offer: "Offer",
  rejected: "Not selected",
  withdrawn: "Withdrawn",
};

export const EVENT_LABEL: Record<string, string> = {
  "application.discovered": "Opening discovered",
  "application.preparation_requested": "Preparation requested",
  "packet.prepared": "Application packet prepared",
  "application.approved": "Approved",
  "application.queued": "Queued for submission",
  "application.paused": "Paused",
  "application.resumed": "Resumed",
  "application.withdrawn": "Withdrawn",
  "submission.started": "Browser worker started (policy checked)",
  "submission.local_started": "Signed-in browser started (policy checked)",
  "submission.local_dispatched": "Signed-in browser clicked submit",
  "submission.user_presence_needed": "Browser needs your attention",
  "submission.denied": "Submission blocked by policy",
  "submission.succeeded": "Submitted with receipt",
  "submission.failed": "Submission failed",
  "submission.outcome_unknown": "Outcome unknown — reconciling",
  "submission.reconciled": "Confirmed by reconciliation",
  "submission.unresolved": "Could not confirm submission",
  "submission.form_changed": "Employer form changed — re-preparing",
  "submission.requeued": "Requeued after worker restart",
  "submission.user_reported": "You marked it as applied",
  "stage.reply_received": "Employer replied",
  "stage.assessment_invited": "Assessment invitation received",
  "stage.interview_scheduled": "Interview invitation received",
  "stage.rejected": "Employer declined",
  "stage.offer": "Offer received",
  "task.created": "Task created",
  "notification.delivered": "Notification delivered",
  "watch.new_match": "New match from your watch",
  "watch.created": "Watch created",
  "monitor.checked": "Sources checked",
  "demo.job_published": "Test employer published a job",
  "mandate.granted": "Automatic mode authorized",
  "mandate.revoked": "Automatic mode revoked",
  "settings.updated": "Settings updated",
  "profile.version_saved": "Profile version saved",
  "workspace.example_started": "Example workspace started",
  "connector.telegram_linked": "Telegram linked",
  "message.unmatched": "Message needs matching",
};
