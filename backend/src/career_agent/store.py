"""Persistence abstraction over a single DynamoDB table.

The domain layer only talks to :class:`Store`. ``DynamoStore`` is used in AWS;
``MemoryStore`` implements identical conditional semantics for fast unit tests.
Conditions are a tiny declarative DSL so both implementations agree exactly.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable


class ConditionFailed(Exception):
    """A conditional write or transaction precondition did not hold."""


# ---------------------------------------------------------------------------
# Condition DSL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class C:
    """Single clause: ``C("state", "eq", "Queued")`` or ``C("pk", "not_exists")``."""

    attr: str
    op: str
    value: Any = None

    def evaluate(self, item: dict | None) -> bool:
        present = item is not None and self.attr in item
        if self.op == "not_exists":
            return not present
        if self.op == "exists":
            return present
        if not present:
            return False
        current = item[self.attr]  # type: ignore[index]
        if self.op == "eq":
            return current == self.value
        if self.op == "ne":
            return current != self.value
        if self.op == "lt":
            return current < self.value
        if self.op == "le":
            return current <= self.value
        if self.op == "gt":
            return current > self.value
        if self.op == "ge":
            return current >= self.value
        raise ValueError(f"unsupported op {self.op}")


@dataclass(frozen=True)
class Or:
    clauses: tuple

    def __init__(self, *clauses: Any) -> None:
        object.__setattr__(self, "clauses", tuple(clauses))

    def evaluate(self, item: dict | None) -> bool:
        return any(c.evaluate(item) for c in self.clauses)


@dataclass(frozen=True)
class And:
    clauses: tuple

    def __init__(self, *clauses: Any) -> None:
        object.__setattr__(self, "clauses", tuple(clauses))

    def evaluate(self, item: dict | None) -> bool:
        return all(c.evaluate(item) for c in self.clauses)


Condition = C | Or | And


# ---------------------------------------------------------------------------
# Transaction operations
# ---------------------------------------------------------------------------


@dataclass
class Put:
    item: dict
    condition: Condition | None = None


@dataclass
class Update:
    pk: str
    sk: str
    set: dict = field(default_factory=dict)
    add: dict = field(default_factory=dict)
    remove: list = field(default_factory=list)
    condition: Condition | None = None


@dataclass
class Check:
    pk: str
    sk: str
    condition: Condition


@dataclass
class Delete:
    pk: str
    sk: str
    condition: Condition | None = None


Op = Put | Update | Check | Delete


class Store:
    """Interface. Items always contain string ``pk`` and ``sk``."""

    def get(self, pk: str, sk: str, consistent: bool = True) -> dict | None:  # pragma: no cover
        raise NotImplementedError

    def put(self, item: dict, condition: Condition | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def update(self, op: Update) -> dict:  # pragma: no cover
        raise NotImplementedError

    def delete(self, pk: str, sk: str, condition: Condition | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def query(
        self,
        pk: str,
        sk_prefix: str = "",
        *,
        index: str | None = None,
        limit: int = 100,
        newest_first: bool = False,
        sk_lte: str | None = None,
    ) -> list[dict]:  # pragma: no cover
        raise NotImplementedError

    def transact(self, ops: Iterable[Op]) -> None:  # pragma: no cover
        raise NotImplementedError


# Index definitions shared by both stores: name -> (partition attr, sort attr)
INDEXES = {
    "gsi1": ("gsi1pk", "gsi1sk"),
}


class MemoryStore(Store):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()
        self.stream: list[dict] = []  # emulates DynamoDB Streams NEW_IMAGE

    def get(self, pk: str, sk: str, consistent: bool = True) -> dict | None:
        item = self._items.get((pk, sk))
        return copy.deepcopy(item) if item else None

    def _check(self, key: tuple[str, str], condition: Condition | None) -> None:
        if condition is not None and not condition.evaluate(self._items.get(key)):
            raise ConditionFailed(str(condition))

    def put(self, item: dict, condition: Condition | None = None) -> None:
        with self._lock:
            key = (item["pk"], item["sk"])
            self._check(key, condition)
            self._items[key] = copy.deepcopy(item)
            self.stream.append(copy.deepcopy(item))

    def _apply_update(self, op: Update) -> dict:
        key = (op.pk, op.sk)
        current = copy.deepcopy(self._items.get(key) or {"pk": op.pk, "sk": op.sk})
        current.update(copy.deepcopy(op.set))
        for k, v in op.add.items():
            current[k] = current.get(k, 0) + v
        for k in op.remove:
            current.pop(k, None)
        return current

    def update(self, op: Update) -> dict:
        with self._lock:
            key = (op.pk, op.sk)
            self._check(key, op.condition)
            new = self._apply_update(op)
            self._items[key] = new
            self.stream.append(copy.deepcopy(new))
            return copy.deepcopy(new)

    def delete(self, pk: str, sk: str, condition: Condition | None = None) -> None:
        with self._lock:
            self._check((pk, sk), condition)
            self._items.pop((pk, sk), None)

    def query(self, pk, sk_prefix="", *, index=None, limit=100, newest_first=False, sk_lte=None):
        pk_attr, sk_attr = INDEXES[index] if index else ("pk", "sk")
        rows = [
            i
            for i in self._items.values()
            if i.get(pk_attr) == pk
            and str(i.get(sk_attr, "")).startswith(sk_prefix)
            and (sk_lte is None or str(i.get(sk_attr, "")) <= sk_lte)
        ]
        rows.sort(key=lambda i: str(i.get(sk_attr, "")), reverse=newest_first)
        return copy.deepcopy(rows[:limit])

    def transact(self, ops: Iterable[Op]) -> None:
        ops = list(ops)
        keys = [(o.item["pk"], o.item["sk"]) if isinstance(o, Put) else (o.pk, o.sk) for o in ops]
        if len(keys) != len(set(keys)):
            raise ValueError("DynamoDB transactions cannot touch the same item twice")
        if len(ops) > 100:
            raise ValueError("too many transaction items")
        with self._lock:
            for op in ops:
                if isinstance(op, Put):
                    self._check((op.item["pk"], op.item["sk"]), op.condition)
                elif isinstance(op, (Update, Check, Delete)):
                    self._check((op.pk, op.sk), op.condition)
            for op in ops:
                if isinstance(op, Put):
                    self._items[(op.item["pk"], op.item["sk"])] = copy.deepcopy(op.item)
                    self.stream.append(copy.deepcopy(op.item))
                elif isinstance(op, Update):
                    new = self._apply_update(op)
                    self._items[(op.pk, op.sk)] = new
                    self.stream.append(copy.deepcopy(new))
                elif isinstance(op, Delete):
                    self._items.pop((op.pk, op.sk), None)


# ---------------------------------------------------------------------------
# DynamoDB implementation
# ---------------------------------------------------------------------------


def to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


class _ExprBuilder:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.values: dict[str, Any] = {}

    def name(self, attr: str) -> str:
        token = f"#n{len(self.names)}"
        self.names[token] = attr
        return token

    def value(self, v: Any) -> str:
        token = f":v{len(self.values)}"
        self.values[token] = to_dynamo(v)
        return token

    def cond(self, c: Condition) -> str:
        if isinstance(c, Or):
            return "(" + " OR ".join(self.cond(x) for x in c.clauses) + ")"
        if isinstance(c, And):
            return "(" + " AND ".join(self.cond(x) for x in c.clauses) + ")"
        n = self.name(c.attr)
        if c.op == "not_exists":
            return f"attribute_not_exists({n})"
        if c.op == "exists":
            return f"attribute_exists({n})"
        sym = {"eq": "=", "ne": "<>", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}[c.op]
        return f"{n} {sym} {self.value(c.value)}"

    def apply(self, params: dict) -> dict:
        if self.names:
            params["ExpressionAttributeNames"] = self.names
        if self.values:
            params["ExpressionAttributeValues"] = self.values
        return params


def _update_params(op: Update) -> dict:
    b = _ExprBuilder()
    parts = []
    if op.set:
        parts.append("SET " + ", ".join(f"{b.name(k)} = {b.value(v)}" for k, v in op.set.items()))
    if op.add:
        parts.append("ADD " + ", ".join(f"{b.name(k)} {b.value(v)}" for k, v in op.add.items()))
    if op.remove:
        parts.append("REMOVE " + ", ".join(b.name(k) for k in op.remove))
    params: dict[str, Any] = {"Key": {"pk": op.pk, "sk": op.sk}, "UpdateExpression": " ".join(parts)}
    if op.condition is not None:
        params["ConditionExpression"] = b.cond(op.condition)
    return b.apply(params)


class DynamoStore(Store):
    def __init__(self, table_name: str, resource: Any = None) -> None:
        import boto3  # local import keeps unit tests dependency-free

        self._resource = resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)
        self._client = self._table.meta.client
        self._name = table_name

    def get(self, pk, sk, consistent=True):
        res = self._table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=consistent)
        item = res.get("Item")
        return from_dynamo(item) if item else None

    def _wrap(self, fn, **params):
        try:
            return fn(**params)
        except self._client.exceptions.ConditionalCheckFailedException as exc:
            raise ConditionFailed(str(exc)) from exc
        except self._client.exceptions.TransactionCanceledException as exc:
            reasons = [r.get("Code") for r in exc.response.get("CancellationReasons", [])]
            if "ConditionalCheckFailed" in reasons:
                raise ConditionFailed(str(reasons)) from exc
            raise

    def put(self, item, condition=None):
        params: dict[str, Any] = {"Item": to_dynamo(item)}
        if condition is not None:
            b = _ExprBuilder()
            params["ConditionExpression"] = b.cond(condition)
            b.apply(params)
        self._wrap(self._table.put_item, **params)

    def update(self, op):
        params = _update_params(op)
        params["ReturnValues"] = "ALL_NEW"
        res = self._wrap(self._table.update_item, **params)
        return from_dynamo(res.get("Attributes", {}))

    def delete(self, pk, sk, condition=None):
        params: dict[str, Any] = {"Key": {"pk": pk, "sk": sk}}
        if condition is not None:
            b = _ExprBuilder()
            params["ConditionExpression"] = b.cond(condition)
            b.apply(params)
        self._wrap(self._table.delete_item, **params)

    def query(self, pk, sk_prefix="", *, index=None, limit=100, newest_first=False, sk_lte=None):
        from boto3.dynamodb.conditions import Key

        pk_attr, sk_attr = INDEXES[index] if index else ("pk", "sk")
        expr = Key(pk_attr).eq(pk)
        if sk_prefix and sk_lte:
            expr = expr & Key(sk_attr).between(sk_prefix, sk_lte)
        elif sk_prefix:
            expr = expr & Key(sk_attr).begins_with(sk_prefix)
        elif sk_lte:
            expr = expr & Key(sk_attr).lte(sk_lte)
        params: dict[str, Any] = {
            "KeyConditionExpression": expr,
            "Limit": limit,
            "ScanIndexForward": not newest_first,
        }
        if index:
            params["IndexName"] = index
        items: list[dict] = []
        while True:
            res = self._table.query(**params)
            items.extend(res.get("Items", []))
            if len(items) >= limit or "LastEvaluatedKey" not in res:
                break
            params["ExclusiveStartKey"] = res["LastEvaluatedKey"]
        return [from_dynamo(i) for i in items[:limit]]

    def transact(self, ops):
        from boto3.dynamodb.types import TypeSerializer

        ser = TypeSerializer()

        def s(d: dict) -> dict:
            return {k: ser.serialize(v) for k, v in to_dynamo(d).items()}

        items = []
        for op in ops:
            if isinstance(op, Put):
                p: dict[str, Any] = {"TableName": self._name, "Item": s(op.item)}
                if op.condition is not None:
                    b = _ExprBuilder()
                    p["ConditionExpression"] = b.cond(op.condition)
                    b.apply(p)
                    if "ExpressionAttributeValues" in p:
                        p["ExpressionAttributeValues"] = s(p["ExpressionAttributeValues"])
                items.append({"Put": p})
            elif isinstance(op, Update):
                p = _update_params(op)
                p["TableName"] = self._name
                p["Key"] = s(p["Key"])
                if "ExpressionAttributeValues" in p:
                    p["ExpressionAttributeValues"] = s(p["ExpressionAttributeValues"])
                items.append({"Update": p})
            elif isinstance(op, Check):
                b = _ExprBuilder()
                p = {"TableName": self._name, "Key": s({"pk": op.pk, "sk": op.sk}), "ConditionExpression": b.cond(op.condition)}
                b.apply(p)
                if "ExpressionAttributeValues" in p:
                    p["ExpressionAttributeValues"] = s(p["ExpressionAttributeValues"])
                items.append({"ConditionCheck": p})
            elif isinstance(op, Delete):
                p = {"TableName": self._name, "Key": s({"pk": op.pk, "sk": op.sk})}
                if op.condition is not None:
                    b = _ExprBuilder()
                    p["ConditionExpression"] = b.cond(op.condition)
                    b.apply(p)
                    if "ExpressionAttributeValues" in p:
                        p["ExpressionAttributeValues"] = s(p["ExpressionAttributeValues"])
                items.append({"Delete": p})
        if items:
            self._wrap(self._client.transact_write_items, TransactItems=items)
