from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectorRunResult:
    source: str
    status: str
    created: int = 0
    updated: int = 0
    skipped: int = 0


def disabled_result(source):
    return CollectorRunResult(source=source, status='SKIPPED', skipped=1)
