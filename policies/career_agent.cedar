// Career Agent authorization policies (policy version: authz/1.0)
//
// Cedar decides *who may do what* and *under which recorded conditions*.
// Transactional facts (remaining daily capacity, cooldown, packet hash) are
// computed by backend code from DynamoDB immediately before the external write
// and passed as context. The language model never produces this context.

// ---- Ownership -----------------------------------------------------------

@id("owner-read-prepare-approve")
permit (
  principal,
  action in [Action::"view_application", Action::"prepare_application", Action::"approve_application", Action::"cancel_application"],
  resource is Application
)
when { resource.owner == principal };

@id("deny-cross-user")
forbid (principal, action, resource is Application)
unless { resource.owner == principal };

// ---- Submission modes ----------------------------------------------------

@id("submit-with-current-explicit-approval")
permit (principal, action == Action::"submit_application", resource is Application)
when { resource.owner == principal && context.approved_packet_hash_matches };

@id("submit-auto-strictly-above-80")
permit (principal, action == Action::"submit_application", resource is Application)
when {
  resource.owner == principal &&
  context.mode == "auto_above_80" &&
  context.mandate_active &&
  context.auto_eligible &&
  context.score > 80
};

@id("submit-auto-eligible-mandate")
permit (principal, action == Action::"submit_application", resource is Application)
when {
  resource.owner == principal &&
  context.mode == "auto_eligible" &&
  context.mandate_active &&
  context.auto_eligible
};

// ---- Guardrails that override every permit -------------------------------

@id("forbid-missing-required-answers")
forbid (principal, action == Action::"submit_application", resource)
unless { context.required_answers_complete };

@id("forbid-daily-cap-exhausted")
forbid (principal, action == Action::"submit_application", resource)
when { context.daily_remaining <= 0 };

@id("forbid-during-cooldown")
forbid (principal, action == Action::"submit_application", resource)
unless { context.cooldown_ok };

@id("forbid-connector-without-submit-capability")
forbid (principal, action == Action::"submit_application", resource)
unless { context.connector_can_submit };

@id("forbid-paused-or-cancelled")
forbid (principal, action == Action::"submit_application", resource)
when { context.paused };

@id("forbid-current-preferences")
forbid (principal, action == Action::"submit_application", resource)
unless { context.preferences_allow_submission };

@id("judge-sessions-test-employers-only")
forbid (principal, action == Action::"submit_application", resource is Application)
when { principal.is_judge && resource.target_environment != "test" };

// ---- Outreach and profile publication need their own explicit approval ----

@id("referral-needs-explicit-approval")
permit (principal, action == Action::"send_referral", resource is Application)
when { resource.owner == principal && context.approved_content_hash_matches && !principal.is_judge };

@id("profile-publish-needs-explicit-approval")
permit (principal, action == Action::"publish_profile", resource is Application)
when { resource.owner == principal && context.approved_content_hash_matches && !principal.is_judge };
