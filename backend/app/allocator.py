"""Deterministic, explainable slot allocation primitives."""
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import Slot

SIZE_RANK = {"two_wheeler": 1, "car": 2, "ev": 2, "accessible": 2, "large": 3}


@dataclass(frozen=True)
class Allocation:
    slot: Slot
    wasted_rank: int
    explanation: str
    components: dict[str, float]


def is_eligible(vehicle_type: str, slot: Slot) -> bool:
    if slot.ev_only and vehicle_type != "ev":
        return False
    if slot.accessible_only and vehicle_type != "accessible":
        return False
    return SIZE_RANK.get(slot.slot_type.value, 0) >= SIZE_RANK.get(vehicle_type, 99)


def allocate_slot(
    slots: Iterable[Slot],
    vehicle_type: str,
    strategy: str,
    weights: dict[str, float] | None = None,
    floor_load: dict[int, int] | None = None,
) -> Allocation | None:
    eligible = [slot for slot in slots if not slot.occupied and is_eligible(vehicle_type, slot)]
    if not eligible:
        return None
    eligible.sort(key=lambda slot: slot.slot_code)
    if strategy == "first_fit":
        selected = eligible[0]
    elif strategy == "best_fit":
        selected = min(eligible, key=lambda slot: (SIZE_RANK[slot.slot_type.value], slot.slot_code))
    elif strategy == "scored":
        configured = weights or {"fit": 1.0, "exit_distance": 0.1, "floor_balance": 0.2}
        loads = floor_load or {}
        def components(slot: Slot) -> dict[str, float]:
            return {
                "fit": float(SIZE_RANK[slot.slot_type.value] - SIZE_RANK[vehicle_type]),
                "exit_distance": float(slot.exit_rank),
                "floor_balance": float(loads.get(slot.floor, 0)),
            }
        selected = min(
            eligible,
            key=lambda slot: (
                sum(configured.get(key, 0.0) * value for key, value in components(slot).items()),
                slot.slot_code,
            ),
        )
        parts = components(selected)
        reason = (
            f"scored fit {parts['fit']:g}, exit distance {parts['exit_distance']:g}, "
            f"floor load {parts['floor_balance']:g}"
        )
        return Allocation(selected, SIZE_RANK[selected.slot_type.value] - SIZE_RANK[vehicle_type], reason, parts)
    else:
        raise ValueError(f"Unknown allocation strategy: {strategy}")
    wasted = SIZE_RANK[selected.slot_type.value] - SIZE_RANK[vehicle_type]
    return Allocation(selected, wasted, f"smallest eligible free slot; wasted rank {wasted}", {"fit": float(wasted)})
