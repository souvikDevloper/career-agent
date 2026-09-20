"""Regression tests for separating autonomous Astra work from interactive work."""

import json

from career_agent.handlers import worker


class FakeSQS:
    def __init__(self):
        self.sent = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "migrated"}


def test_legacy_watch_message_is_forwarded_out_of_work_queue(monkeypatch):
    fake = FakeSQS()
    monkeypatch.setenv("WATCH_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/astra-watch")
    monkeypatch.setattr(worker, "_sqs", fake)

    record = {
        "messageId": "old-1",
        "eventSourceARN": "arn:aws:sqs:us-east-1:123:career-agent-work",
    }
    msg = {"kind": "check_watch", "user_id": "u1", "watch_id": "w_1"}

    assert worker._forward_legacy_watch(record, msg)
    assert fake.sent == [{
        "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/astra-watch",
        "MessageBody": json.dumps(msg),
    }]


def test_watch_queue_delivery_is_not_forwarded_again(monkeypatch):
    fake = FakeSQS()
    monkeypatch.setenv("WATCH_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/astra-watch")
    monkeypatch.setattr(worker, "_sqs", fake)

    record = {
        "messageId": "watch-1",
        "eventSourceARN": "arn:aws:sqs:us-east-1:123:astra-watch",
    }
    msg = {"kind": "match_new_job", "user_id": "u1", "job_key": "j1"}

    assert not worker._forward_legacy_watch(record, msg)
    assert fake.sent == []
