from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import app.database as database
from app.main import app
from app.models.hours import HoursClaim, Milestone, Reward
from app.models.user import User
from app.services.hours_service import HoursClaimService
from app.utilities.security import encrypt_password


@pytest.fixture
def seeded_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api_test.db'}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=5.0, pointsbalance=50),
            User(username="bob", email="bob@example.com", password=encrypt_password("bobpass"), role="student", lifetimehours=12.0, pointsbalance=120),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()
    client = TestClient(app)
    return client


def login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_it01_login_claim_submission_progress_and_rewards(seeded_client):
    client = seeded_client
    token = login(client, "alice", "pw")
    headers = {"Authorization": f"Bearer {token}"}

    claim_resp = client.post(
        "/api/claims",
        json={"activity": "Park cleanup", "date": "2026-10-11", "hours": 3.5, "description": "Helped at the park clean-up drive", "proof": "receipt-1"},
        headers=headers,
    )
    assert claim_resp.status_code == 201, claim_resp.text

    my_claims = client.get("/api/claims/me", headers=headers)
    assert my_claims.status_code == 200, my_claims.text
    assert my_claims.json()[0]["activity"] == "Park cleanup"

    progress = client.get("/api/me/progress", headers=headers)
    assert progress.status_code == 200, progress.text
    assert progress.json()["lifetime_hours"] == 5.0

    leaderboard = client.get("/api/leaderboard", headers=headers)
    assert leaderboard.status_code == 200, leaderboard.text
    assert isinstance(leaderboard.json(), list)

    rewards = client.get("/api/rewards", headers=headers)
    assert rewards.status_code == 200, rewards.text
    assert isinstance(rewards.json(), list)


def test_it02_missing_token_invalid_hours_and_role_forbidden(seeded_client):
    client = seeded_client

    unauth = client.post("/api/claims", json={"activity": "X", "date": "2026-10-11", "hours": 5, "description": "bad"})
    assert unauth.status_code == 401

    token = login(client, "alice", "pw")
    headers = {"Authorization": f"Bearer {token}"}

    invalid_hours = client.post(
        "/api/claims",
        json={"activity": "X", "date": "2026-10-11", "hours": 25, "description": "bad"},
        headers=headers,
    )
    assert invalid_hours.status_code == 400
    assert "greater than zero and no more than 24" in invalid_hours.json()["detail"]

    staff_list = client.get("/api/claims", headers=headers)
    assert staff_list.status_code == 403

    reject = client.patch("/api/claims/999", json={"action": "reject", "reason": "Bad"}, headers=headers)
    assert reject.status_code == 403


def test_it03_admin_claim_review_and_approval_flow(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'claims_review.db'}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="student", email="student@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.add(HoursClaim(userid=1, activity="Park cleanup", date=date(2026, 10, 11), hours=3.5, description="Helped with park cleanup", status="pending"))
        session.commit()

    client = TestClient(app)
    admin_token = login(client, "admin", "adminpass")
    headers = {"Authorization": f"Bearer {admin_token}"}

    queue = client.get("/api/claims", headers=headers)
    assert queue.status_code == 200
    payload = queue.json()
    assert payload[0]["activity"] == "Park cleanup"

    patch = client.patch("/api/claims/1", json={"action": "approve", "hours": 4.0}, headers=headers)
    assert patch.status_code == 200, patch.text
    assert patch.json()["claim"]["status"] == "approved"

    student_token = login(client, "student", "pw")
    progress = client.get("/api/me/progress", headers={"Authorization": f"Bearer {student_token}"})
    assert progress.status_code == 200
    assert progress.json()["lifetime_hours"] == 4.0


def test_it04_leaderboard_and_rewards_catalog_are_returned(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'leaderboard_api.db'}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=25.0, pointsbalance=250),
            User(username="bob", email="bob@example.com", password=encrypt_password("pw"), role="student", lifetimehours=53.0, pointsbalance=530),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.add(Milestone(name="Bronze", hoursrequired=10))
        session.add(Milestone(name="Silver", hoursrequired=25))
        session.add(Milestone(name="Gold", hoursrequired=50))
        session.commit()

    client = TestClient(app)
    token = login(client, "alice", "pw")
    headers = {"Authorization": f"Bearer {token}"}

    leaderboard = client.get("/api/leaderboard", headers=headers)
    assert leaderboard.status_code == 200, leaderboard.text
    names = [entry["username"] for entry in leaderboard.json()]
    assert "bob" in names and "alice" in names

    rewards = client.get("/api/rewards", headers=headers)
    assert rewards.status_code == 200
    payload = rewards.json()
    assert any(item["name"] == "Coffee Voucher" for item in payload)


def test_it05_redemption_request_and_staff_processing_flow(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'redemption_api.db'}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="student", email="student@example.com", password=encrypt_password("pw"), role="student", lifetimehours=40.0, pointsbalance=200),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

    client = TestClient(app)
    student_token = login(client, "student", "pw")
    reward_list = client.get("/api/rewards", headers={"Authorization": f"Bearer {student_token}"})
    reward_id = next(item["reward_id"] for item in reward_list.json() if item["name"] == "Coffee Voucher")

    redemption = client.post("/api/redemptions", json={"reward_id": reward_id}, headers={"Authorization": f"Bearer {student_token}"})
    assert redemption.status_code == 201, redemption.text
    redemption_id = redemption.json()["redemption"]["redemptionid"]

    my_redemptions = client.get("/api/redemptions/me", headers={"Authorization": f"Bearer {student_token}"})
    assert my_redemptions.status_code == 200
    assert any(item["reward_id"] == reward_id for item in my_redemptions.json())

    admin_token = login(client, "admin", "adminpass")
    staff_queue = client.get("/api/redemptions", headers={"Authorization": f"Bearer {admin_token}"})
    assert staff_queue.status_code == 200
    assert any(item["id"] == redemption_id for item in staff_queue.json())

    fulfill = client.patch(f"/api/redemptions/{redemption_id}", json={"action": "fulfill"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert fulfill.status_code == 200, fulfill.text
    assert fulfill.json()["redemption"]["status"] == "fulfilled"


def test_it06_protected_routes_reject_unapproved_access(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'protected_routes.db'}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="student", email="student@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

    client = TestClient(app)

    user_token = login(client, "student", "pw")
    admin_token = login(client, "admin", "adminpass")

    client.cookies.clear()
    no_token = client.get("/api/users")
    assert no_token.status_code == 401

    wrong_role = client.get("/api/users", headers={"Authorization": f"Bearer {user_token}"})
    assert wrong_role.status_code == 403

    admin_ok = client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_ok.status_code == 200
