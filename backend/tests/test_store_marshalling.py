"""Marshalling of transaction requests.

Both DynamoDB bugs this project shipped lived here and neither was reachable by a
test: MemoryStore marshals nothing, and the only other path was a live call, so
the failures only appeared in production logs.

  * Values were serialized by hand and then sent through the boto3 *resource's*
    client, which marshals again - "Type mismatch for key pk expected: S actual: M".
  * Expression values were passed through a helper that drops None, so the
    expression still named :vN while the values map no longer contained it -
    "an expression attribute value used in expression is not defined".

These assert on the request that would be sent, which is the layer that was blind.
"""

from __future__ import annotations

import re
from decimal import Decimal

from career_agent.store import Check, Delete, Put, Update, build_transact_items, C

TABLE = "career-agent-test"


def _values_are_defined(entry: dict) -> None:
    """Every :vN named by an expression must exist in ExpressionAttributeValues."""
    params = next(iter(entry.values()))
    named = set()
    for key in ("UpdateExpression", "ConditionExpression"):
        if key in params:
            named |= set(re.findall(r":v\d+", params[key]))
    defined = set(params.get("ExpressionAttributeValues", {}))
    assert named <= defined, f"expression names {sorted(named - defined)} but they are not defined"


def test_keys_serialize_as_strings_not_maps():
    """The double-serialization bug: pk must be {'S': ...}, never a map."""
    items = build_transact_items([Put({"pk": "USER#1", "sk": "PROFILE#V#000001", "version": 1})], TABLE)
    item = items[0]["Put"]["Item"]
    assert item["pk"] == {"S": "USER#1"}
    assert item["sk"] == {"S": "PROFILE#V#000001"}
    assert item["version"] == {"N": "1"}


def test_none_expression_value_survives_as_null():
    """The dropped-value bug: setting an attribute to None must not remove :vN."""
    items = build_transact_items([Update("USER#1", "APP#1", set={"receipt": None, "state": "Submitted"})], TABLE)
    params = items[0]["Update"]
    _values_are_defined(items[0])
    assert {"NULL": True} in params["ExpressionAttributeValues"].values()


def test_every_op_defines_the_values_its_expression_names():
    """The general invariant. Any future regression of this class fails here."""
    ops = [
        Put({"pk": "USER#1", "sk": "A"}, C("pk", "not_exists")),
        Put({"pk": "USER#1", "sk": "B", "note": None}, C("pk", "not_exists")),
        Update("USER#1", "APP#1", set={"state": "Queued"}, condition=C("version", "eq", 3)),
        Update("USER#1", "LEDGER#2026-09-18", add={"count": 1}, set={"ttl": None}),
        Update("USER#1", "APP#2", set={"a": None}, remove=["b"], condition=C("fencing", "eq", 7)),
        Check("USER#1", "SETTINGS", C("mode", "eq", "review")),
        Delete("USER#1", "APP#3", C("state", "ne", "Submitted")),
    ]
    entries = build_transact_items(ops, TABLE)
    assert len(entries) == len(ops)
    for entry in entries:
        _values_are_defined(entry)


def test_floats_become_decimal():
    """DynamoDB rejects floats; they have to be converted before serializing."""
    items = build_transact_items([Put({"pk": "USER#1", "sk": "M", "score": 86.5})], TABLE)
    assert items[0]["Put"]["Item"]["score"] == {"N": str(Decimal("86.5"))}


def test_condition_without_values_sends_no_empty_map():
    """attribute_not_exists takes no value, and an empty map is itself invalid."""
    items = build_transact_items([Put({"pk": "USER#1", "sk": "A"}, C("pk", "not_exists"))], TABLE)
    params = items[0]["Put"]
    assert "attribute_not_exists" in params["ConditionExpression"]
    # Absent is correct and is what the builder does; an empty map would be rejected.
    assert params.get("ExpressionAttributeValues", None) != {}


def test_nested_none_is_still_dropped_from_item_attributes():
    """Inside an item a None is noise and is dropped - only expression values must keep it."""
    items = build_transact_items([Put({"pk": "USER#1", "sk": "P", "facts": {"name": "Aarav", "summary": None}})], TABLE)
    facts = items[0]["Put"]["Item"]["facts"]["M"]
    assert "name" in facts and "summary" not in facts


def test_table_name_is_set_on_every_entry():
    ops = [Put({"pk": "U", "sk": "A"}), Update("U", "B", set={"x": 1}), Delete("U", "C")]
    for entry in build_transact_items(ops, TABLE):
        assert next(iter(entry.values()))["TableName"] == TABLE
