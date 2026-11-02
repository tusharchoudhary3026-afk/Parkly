"""Transparent weekday/hour occupancy baseline and time-ordered evaluation."""
from datetime import datetime

import pandas as pd


def forecast_mean(snapshots: list[dict], target: datetime) -> tuple[float | None, int]:
    if not snapshots:
        return None, 0
    frame=pd.DataFrame(snapshots)
    frame["captured_at"]=pd.to_datetime(frame["captured_at"],utc=True)
    frame["weekday"]=frame["captured_at"].dt.weekday
    frame["hour"]=frame["captured_at"].dt.hour
    frame["occupancy_rate"]=frame["occupied_count"]/frame["capacity"].clip(lower=1)
    target_utc=pd.Timestamp(target).tz_convert("UTC") if pd.Timestamp(target).tzinfo else pd.Timestamp(target,tz="UTC")
    matching=frame[(frame["weekday"]==target_utc.weekday())&(frame["hour"]==target_utc.hour)]
    if matching.empty:
        return float(frame["occupancy_rate"].mean()),len(frame)
    return float(matching["occupancy_rate"].mean()),len(matching)


def frozen_last_week_mae(records: list[dict]) -> tuple[float, int]:
    frame=pd.DataFrame(records)
    if frame.empty:
        raise ValueError("forecast evaluation requires snapshots")
    frame["captured_at"]=pd.to_datetime(frame["captured_at"],utc=True)
    cutoff=frame["captured_at"].max()-pd.Timedelta(7, unit="D")
    train=frame[frame["captured_at"]<cutoff].copy()
    # Strictly after the boundary gives exactly 168 hourly observations per series.
    test=frame[frame["captured_at"]>cutoff].copy()
    if train.empty or test.empty:
        raise ValueError("time split requires training history and a frozen final week")
    for part in (train,test):
        part["weekday"]=part["captured_at"].dt.weekday
        part["hour"]=part["captured_at"].dt.hour
        part["occupancy_rate"]=part["occupied_count"]/part["capacity"].clip(lower=1)
    averages=train.groupby(["lot_id","weekday","hour"])["occupancy_rate"].mean().rename("prediction")
    scored=test.join(averages,on=["lot_id","weekday","hour"])
    scored["prediction"]=scored["prediction"].fillna(train["occupancy_rate"].mean())
    mae=float((scored["occupancy_rate"]-scored["prediction"]).abs().mean())
    return mae,len(scored)
