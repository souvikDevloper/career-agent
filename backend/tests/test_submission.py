import helpers  # noqa: F401

from career_agent.submission import submission_plan


def test_amazon_uses_authenticated_local_browser():
    job = {"connector": "amazon-jobs", "external_id": "123",
           "url": "https://www.amazon.jobs/en/jobs/123/sde",
           "apply": {"kind": "external", "url": "https://www.amazon.jobs/en/jobs/123/sde"}}
    plan = submission_plan(job)
    assert plan["mode"] == "local_browser"
    assert plan["can_fill"] is True
    assert plan["can_submit"] is True
    assert plan["requires_user_presence"] is True
    assert plan["requires_login"] is True
    assert plan["url"] == "https://account.amazon.jobs/en-US/applicant/jobs/123/apply"


def test_workday_uses_authenticated_local_browser():
    job = {"connector": "workday-public",
           "apply": {"kind": "external", "url": "https://paypal.wd1.myworkdayjobs.com/en-US/jobs/job/x"}}
    assert submission_plan(job)["mode"] == "local_browser"


def test_greenhouse_hosted_form_stays_cloud_automatable():
    job = {"connector": "greenhouse-public",
           "apply": {"kind": "hosted_form", "url": "https://job-boards.greenhouse.io/twilio/jobs/8177722"}}
    plan = submission_plan(job)
    assert plan["mode"] == "cloud_browser"
    assert plan["requires_user_presence"] is False


def test_greenhouse_embedded_external_form_moves_to_local_browser():
    job = {"connector": "greenhouse-public",
           "apply": {"kind": "external", "url": "https://stripe.com/jobs/search?gh_jid=8172487"}}
    plan = submission_plan(job)
    assert plan["mode"] == "local_browser"
    assert plan["requires_user_presence"] is True


def test_unknown_connector_is_manual_not_falsely_automated():
    plan = submission_plan({"connector": "new-ats", "url": "https://jobs.example.test/1"})
    assert plan["mode"] == "manual"
    assert plan["can_submit"] is False
