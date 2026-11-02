"""PostgreSQL acceptance tests for the location discovery extension."""
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import (
    Area,
    AuditLog,
    City,
    LocationSuggestion,
    Lot,
    Operator,
    Role,
    State,
    TariffVersion,
    User,
    Venue,
)
from app.security import issue_token
from app.seed import seed_locations


async def make_user(role: Role = Role.DRIVER):
    async with SessionLocal() as db:
        operator = Operator(name=f"Location test {uuid4()}", synthetic=True)
        db.add(operator)
        await db.flush()
        user = User(operator_id=operator.id, email=f"{uuid4()}@test.invalid", password_hash="not-used",
                    role=role, synthetic=True)
        db.add(user)
        await db.commit()
        return user.id, operator.id, issue_token(user)


@pytest.mark.asyncio
async def test_at11_location_hierarchy_is_ordered_consistent_and_seed_idempotent():
    async with SessionLocal() as db:
        await seed_locations(db)
        await db.commit()
        before = (
            await db.scalar(select(func.count()).select_from(State).where(State.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(City).where(City.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(Area).where(Area.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(Venue).where(Venue.is_seeded.is_(True))),
        )
        await seed_locations(db)
        await db.commit()
        after = (
            await db.scalar(select(func.count()).select_from(State).where(State.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(City).where(City.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(Area).where(Area.is_seeded.is_(True))),
            await db.scalar(select(func.count()).select_from(Venue).where(Venue.is_seeded.is_(True))),
        )
        assert before == after == (36, 70, 19, 38)
    _, _, token = await make_user()
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        states = (await client.get("/locations/states", headers=headers)).json()
        mp = next(row for row in states if row["code"] == "MP")
        cities = (await client.get(f"/locations/states/{mp['id']}/cities", headers=headers)).json()
        gwalior = next(row for row in cities if row["name"] == "Gwalior")
        areas = (await client.get(f"/locations/cities/{gwalior['id']}/areas", headers=headers)).json()
        assert [row["name"] for row in areas] == sorted((row["name"] for row in areas), key=str.casefold)
        venues = (await client.get(f"/locations/areas/{areas[0]['id']}/venues", headers=headers)).json()
        assert len(venues) == 2
        assert all(row["area_id"] == areas[0]["id"] and row["data_label"] == "SYNTHETIC" for row in venues)


@pytest.mark.asyncio
async def test_at12_location_filters_obey_specificity_empty_results_and_tenant_scope():
    async with SessionLocal() as db:
        await seed_locations(db)
        state = await db.scalar(select(State).where(State.code == "MP"))
        city = await db.scalar(select(City).where(City.state_id == state.id, City.name == "Gwalior"))
        area = await db.scalar(select(Area).where(Area.city_id == city.id, Area.name == "City Centre"))
        venue = await db.scalar(select(Venue).where(Venue.area_id == area.id).order_by(Venue.name))
        empty_venue = await db.scalar(select(Venue).where(Venue.area_id == area.id, Venue.id != venue.id))
        operator = Operator(name=f"AT12 owner {uuid4()}", synthetic=True)
        other_operator = Operator(name=f"AT12 other {uuid4()}", synthetic=True)
        db.add_all([operator, other_operator])
        await db.flush()
        db.add_all([
            Lot(operator_id=operator.id, name="AT12 linked lot", address="demo", area_id=area.id, venue_id=venue.id,
                timezone="UTC", config={}, tariff={}, strategy="first_fit"),
            Lot(operator_id=other_operator.id, name="AT12 other tenant lot", address="demo", area_id=area.id,
                venue_id=venue.id, timezone="UTC", config={}, tariff={}, strategy="first_fit"),
        ])
        user = User(operator_id=operator.id, email=f"{uuid4()}@test.invalid", password_hash="not-used",
                    role=Role.DRIVER, synthetic=True)
        manager = User(operator_id=operator.id, email=f"{uuid4()}@test.invalid", password_hash="not-used",
                       role=Role.MANAGER, synthetic=True)
        db.add_all([user, manager])
        await db.commit()
        token, manager_token = issue_token(user), issue_token(manager)
        venue_id, empty_id, area_id, city_id, state_id = venue.id, empty_venue.id, area.id, city.id, state.id
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        by_venue = await client.get(f"/lots?venue_id={venue_id}&city_id={city_id}", headers=headers)
        by_area = await client.get(f"/lots?area_id={area_id}", headers=headers)
        by_city = await client.get(f"/lots?city_id={city_id}", headers=headers)
        by_state = await client.get(f"/lots?state_id={state_id}", headers=headers)
        no_lots = await client.get(f"/lots?venue_id={empty_id}", headers=headers)
    assert [row["name"] for row in by_venue.json()] == ["AT12 linked lot"]
    assert [row["name"] for row in by_area.json()] == ["AT12 linked lot"]
    assert [row["name"] for row in by_city.json()] == ["AT12 linked lot"]
    assert [row["name"] for row in by_state.json()] == ["AT12 linked lot"]
    assert no_lots.status_code == 200 and no_lots.json() == []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/operator/lots", headers={"Authorization":f"Bearer {manager_token}"}, json={
            "name":"AT12 created at venue","address":"Demo only","area_id":str(area_id),"venue_id":str(venue_id),
            "config":{},"tariff":{},"strategy":"first_fit"})
        assert created.status_code == 201
        updated = await client.put(f"/operator/lots/{created.json()['id']}/configuration",
            headers={"Authorization":f"Bearer {manager_token}"}, json={
                "config":{"grace_minutes":10},"tariff":{"hourly":{"car":10}},"strategy":"best_fit",
                "area_id":str(area_id),"venue_id":str(venue_id)})
        assert updated.status_code == 200 and updated.json()["version"] == 2
    async with SessionLocal() as db:
        created_lot = await db.scalar(select(Lot).where(Lot.id == created.json()["id"]))
        version = await db.scalar(select(TariffVersion).where(TariffVersion.lot_id == created_lot.id))
        assert created_lot.area_id == area_id and created_lot.venue_id == venue_id
        assert version.config["venue_id"] == str(venue_id)


@pytest.mark.asyncio
async def test_at13_suggestions_validate_are_private_rate_limited_and_reviewed_with_audit():
    driver_id, _, driver_token = await make_user()
    other_id, _, other_token = await make_user()
    manager_id, manager_operator, manager_token = await make_user(Role.MANAGER)
    async with SessionLocal() as db:
        state = await db.scalar(select(State).where(State.code == "MP"))
        state_id = state.id
    city_name = f"New Demo {uuid4().hex[:8]}"
    driver_headers = {"Authorization": f"Bearer {driver_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    manager_headers = {"Authorization": f"Bearer {manager_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        suggestion_response = await client.post("/locations/suggestions", headers=driver_headers, json={
            "state_id": str(state_id), "target_level": "city", "city_name": city_name})
        suggestion = suggestion_response.json()
        duplicate = await client.post("/locations/suggestions", headers=driver_headers, json={
            "state_id": str(state_id), "target_level": "city", "city_name": city_name.lower().replace(" ", "   ")})
        invalid = await client.post("/locations/suggestions", headers=driver_headers, json={
            "state_id": str(state_id), "target_level": "city", "city_name": "Bad <City>"})
        owner_list = await client.get("/locations/suggestions", headers=driver_headers)
        other_list = await client.get("/locations/suggestions", headers=other_headers)
        missing_reason = await client.post(f"/locations/suggestions/{suggestion['id']}/review",
            headers=manager_headers, json={"decision":"approve"})
        reviewed = await client.post(f"/locations/suggestions/{suggestion['id']}/review",
            headers=manager_headers, json={"decision":"approve","reason":"Name checked by reviewer"})
        approved_city = await client.get(f"/locations/states/{state_id}/cities", headers=driver_headers)
        no_lots = await client.get(f"/lots?city_id={next(row['id'] for row in approved_city.json() if row['name']==city_name)}", headers=driver_headers)
        reject_response = await client.post("/locations/suggestions", headers=driver_headers, json={
            "state_id": str(state_id), "target_level": "city", "city_name": "Reject This City"})
        manager_queue = await client.get("/locations/suggestions", headers=manager_headers)
        rejected = await client.post(f"/locations/suggestions/{reject_response.json()['id']}/review",
            headers=manager_headers, json={"decision":"reject","reason":"Could not verify this location"})
    assert suggestion_response.status_code == 201
    assert suggestion["status"] == "pending"
    assert suggestion["message"] == "No parking lots are listed here yet. Your suggestion has been sent for review."
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["error"] == "suggestion_duplicate"
    assert invalid.status_code == 422
    assert any(row["id"] == suggestion["id"] for row in owner_list.json())
    assert all(row["id"] != suggestion["id"] for row in other_list.json())
    assert missing_reason.status_code == 422
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "approved"
    assert no_lots.status_code == 200 and no_lots.json() == []
    assert any(row["id"] == reject_response.json()["id"] for row in manager_queue.json())
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    async with SessionLocal() as db:
        approved = await db.scalar(select(City).where(City.state_id == state_id, City.name == city_name))
        audit_rows = (await db.scalars(select(AuditLog).where(AuditLog.operator_id == manager_operator,
            AuditLog.entity_type == "location_suggestion"))).all()
        assert approved is not None and approved.source == "user_submitted" and not approved.is_seeded
        assert {row.action for row in audit_rows} >= {"location_suggestion.approve", "location_suggestion.reject"}
        assert all(row.reason for row in audit_rows)
    limiter_user_id, _, limiter_token = await make_user()
    assert limiter_user_id != driver_id and limiter_user_id != other_id and manager_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for index in range(10):
            response = await client.post("/locations/suggestions", headers={"Authorization": f"Bearer {limiter_token}"},
                json={"state_id":str(state_id),"target_level":"city","city_name":f"Queued {uuid4().hex[:8]} {index:02}"})
            assert response.status_code == 201
        limited = await client.post("/locations/suggestions", headers={"Authorization": f"Bearer {limiter_token}"},
            json={"state_id":str(state_id),"target_level":"city","city_name":f"Queued {uuid4().hex[:8]} 10"})
    assert limited.status_code == 429 and limited.json()["detail"]["error"] == "suggestion_rate_limited"


@pytest.mark.asyncio
async def test_at14_location_suggestion_roles_and_authentication():
    driver_id, _, driver_token = await make_user(Role.DRIVER)
    _, _, attendant_token = await make_user(Role.ATTENDANT)
    _, _, auditor_token = await make_user(Role.AUDITOR)
    _, _, manager_token = await make_user(Role.MANAGER)
    async with SessionLocal() as db:
        state = await db.scalar(select(State).where(State.code == "MP"))
        state_id = state.id
        suggestion = LocationSuggestion(submitted_by_user_id=driver_id, state_id=state_id,
            target_level="city", city_name=f"AT14 {uuid4()}", status="pending")
        db.add(suggestion)
        await db.commit()
        suggestion_id = suggestion.id
    payload = {"decision":"approve","reason":"AT14 role verification"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.post(f"/locations/suggestions/{suggestion_id}/review", json=payload)
        driver = await client.post(f"/locations/suggestions/{suggestion_id}/review",
            headers={"Authorization":f"Bearer {driver_token}"}, json=payload)
        attendant = await client.post(f"/locations/suggestions/{suggestion_id}/review",
            headers={"Authorization":f"Bearer {attendant_token}"}, json=payload)
        auditor = await client.post(f"/locations/suggestions/{suggestion_id}/review",
            headers={"Authorization":f"Bearer {auditor_token}"}, json=payload)
        manager = await client.get("/locations/suggestions", headers={"Authorization":f"Bearer {manager_token}"})
    assert unauthenticated.status_code == 401
    assert driver.status_code == attendant.status_code == auditor.status_code == 403
    assert any(row["id"] == str(suggestion_id) for row in manager.json())
