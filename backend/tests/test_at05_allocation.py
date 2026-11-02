"""AT-05: compare strategies on identical demand with independent slot pools."""
import random
from dataclasses import dataclass

from app.allocator import allocate_slot, is_eligible
from app.models import SlotType


@dataclass
class SimSlot:
    slot_code: str
    slot_type: SlotType
    floor: int
    exit_rank: int
    ev_only: bool = False
    accessible_only: bool = False
    occupied: bool = False


def fresh_pool() -> list[SimSlot]:
    types = (
        [SlotType.TWO_WHEELER] * 25
        + [SlotType.CAR] * 50
        + [SlotType.LARGE] * 15
        + [SlotType.EV] * 5
        + [SlotType.ACCESSIBLE] * 5
    )
    return [
        SimSlot(
            slot_code=f"S{index:03}",
            slot_type=kind,
            floor=index % 3,
            exit_rank=(index * 7) % 20,
            ev_only=kind == SlotType.EV,
            accessible_only=kind == SlotType.ACCESSIBLE,
        )
        for index, kind in enumerate(types)
    ]


def run_strategy(seed: int, strategy: str, demand: list[str]) -> list[int]:
    pool = fresh_pool()
    rng = random.Random(seed)
    rng.shuffle(pool)
    wasted_ranks: list[int] = []
    weights = {"fit": 1.0, "exit_distance": 0.1, "floor_balance": 0.2}
    for vehicle_type in demand:
        allocation = allocate_slot(pool, vehicle_type, strategy, weights=weights)
        if allocation is None:
            continue
        allocation.slot.occupied = True
        wasted_ranks.append(allocation.wasted_rank)
    return wasted_ranks


def test_at05_same_seeded_demand_separate_pools_and_eligibility():
    strategies = ("first_fit", "best_fit", "scored")
    seeds = (11, 23, 37, 41, 59)
    results: dict[str, list[float]] = {strategy: [] for strategy in strategies}
    sample_sizes: dict[str, list[int]] = {strategy: [] for strategy in strategies}
    for seed in seeds:
        rng = random.Random(seed)
        demand = rng.choices(("two_wheeler", "car", "large", "ev", "accessible"),
            weights=(0.2, 0.5, 0.15, 0.1, 0.05), k=500)
        for strategy in strategies:
            ranks = run_strategy(seed, strategy, demand)
            assert ranks
            results[strategy].append(sum(ranks) / len(ranks))
            sample_sizes[strategy].append(len(ranks))

    for strategy in strategies:
        assert len(results[strategy]) == len(seeds)
        assert all(size > 0 for size in sample_sizes[strategy])
        print(f"AT-05 {strategy}: seeds={list(seeds)}, offered_n={len(demand)}, allocated_n={sample_sizes[strategy]}, "
              f"rejected_n={[len(demand)-size for size in sample_sizes[strategy]]}, "
              f"mean_wasted_rank={results[strategy]}, spread="
              f"{min(results[strategy]):.3f}..{max(results[strategy]):.3f}")

    pool = fresh_pool()
    ev_slot = next(slot for slot in pool if slot.ev_only)
    accessible_slot = next(slot for slot in pool if slot.accessible_only)
    assert not is_eligible("car", ev_slot)
    assert not is_eligible("car", accessible_slot)
    assert is_eligible("ev", ev_slot)
    assert is_eligible("accessible", accessible_slot)
