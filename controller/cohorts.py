"""One shared cohort definition, used by detection, experiments and the supervisor view.

A cohort is a named group of leads defined by feature conditions. Its id is derived from
its definition, so the same group always has the same id everywhere. Cohorts that already
exist in a workflow's config (for example ones a supervisor created) keep the id they have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FEATURES = ("lang", "city_tier", "age_band", "value_band")
MAX_COHORTS = 20          # simulator limit
DEFAULT = "default"       # leads that match no cohort


def _slug(text: str) -> str:
    text = text.replace("+", "plus")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@dataclass(frozen=True)
class Cohort:
    id: str
    where: tuple          # canonical: ((feature, (value, ...)), ...), sorted

    @staticmethod
    def make(where: dict) -> "Cohort":
        """Build a cohort from {feature: [values]} with a deterministic id."""
        if not where:
            raise ValueError("a cohort needs at least one feature condition")
        for f, vals in where.items():
            if f not in FEATURES:
                raise ValueError(f"unknown feature {f!r}")
            if not vals:
                raise ValueError(f"feature {f!r} has no values")
        canon = tuple((f, tuple(sorted(str(v) for v in where[f]))) for f in sorted(where))
        cid = "__".join(f"{f}_" + "_".join(_slug(v) for v in vals) for f, vals in canon)
        return Cohort(cid, canon)

    def matches(self, features: dict) -> bool:
        """AND across features, OR within a feature's values (same rule as the simulator)."""
        return all(str(features.get(f)) in vals for f, vals in self.where)

    def to_config(self) -> dict:
        return {"id": self.id, "where": {f: list(vals) for f, vals in self.where}}

    @staticmethod
    def from_config(d: dict) -> "Cohort":
        """Read a cohort out of a workflow config, keeping the id the config already uses."""
        return Cohort(d["id"], Cohort.make(d["where"]).where)


class CohortSet:
    """Ordered cohorts. A lead belongs to the FIRST cohort it matches, otherwise to 'default'."""

    def __init__(self, cohorts):
        self.cohorts = list(cohorts)
        if len(self.cohorts) > MAX_COHORTS:
            raise ValueError(f"at most {MAX_COHORTS} cohorts")
        ids = [c.id for c in self.cohorts]
        if len(set(ids)) != len(ids) or DEFAULT in ids:
            raise ValueError("cohort ids must be unique and not 'default'")

    def assign(self, features: dict) -> str:
        for c in self.cohorts:
            if c.matches(features):
                return c.id
        return DEFAULT

    def ids(self) -> list[str]:
        return [c.id for c in self.cohorts] + [DEFAULT]

    def to_config(self) -> list[dict]:
        return [c.to_config() for c in self.cohorts]

    @staticmethod
    def from_config(items) -> "CohortSet":
        return CohortSet(Cohort.from_config(d) for d in (items or []))