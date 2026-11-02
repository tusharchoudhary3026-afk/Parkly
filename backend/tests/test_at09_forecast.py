"""AT-09: evaluate the baseline on a frozen final week using an earlier time split."""
import random
from datetime import UTC, datetime, timedelta

from app.forecast import frozen_last_week_mae


def test_at09_baseline_mae_on_frozen_last_seven_days():
    rng=random.Random(20261101)
    now=datetime.now(UTC).replace(minute=0,second=0,microsecond=0)
    records=[]
    for day in range(30):
        captured_day=now-timedelta(days=day+1)
        for lot_id,capacity in (("lot-a",67),("lot-b",67),("lot-c",67)):
            for hour in range(24):
                peak=0.28 if hour in range(8,11) or hour in range(16,20) else 0.0
                weekend=-0.08 if captured_day.weekday()>=5 else 0.0
                rate=min(0.95,max(0.05,0.32+peak+weekend+rng.uniform(-0.05,0.05)))
                records.append({"lot_id":lot_id,"captured_at":captured_day.replace(hour=hour),
                    "occupied_count":round(capacity*rate),"capacity":capacity,"synthetic":True})
    mae,sample_size=frozen_last_week_mae(records)
    assert sample_size==7*24*3
    assert 0<=mae<=1
    print(f"AT-09 baseline MAE={mae:.4f}, n={sample_size}, split=first 23 days / frozen last 7 days")
