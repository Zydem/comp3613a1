from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import app.database as database
from app.main import app
from app.models.user import User
from app.models.hours import HoursClaim, Milestone, Redemption, StudentMilestone
from app.services.hours_service import HoursClaimService
from app.utilities.security import encrypt_password


class DummyDB:
    def __init__(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)


def test_approve_claim_updates_user_hours_and_unlocks_milestone():
    db = DummyDB()
    user = User(username="stud1", email="stud1@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)

    milestone = Milestone(name="Bronze", hoursrequired=5)
    db.session.add(milestone)
    db.session.commit()
    db.session.refresh(milestone)

    claim = HoursClaim(userid=user.id, activity="Volunteer", date=date.today(), hours=5.0, description="Community work", status="pending")
    db.session.add(claim)
    db.session.commit()
    db.session.refresh(claim)

    service = HoursClaimService(db.session)
    approved = service.review_claim(claim.claimid, user.id, "approved", None)

    assert approved.status == "approved"
    user_after = db.session.get(User, user.id)
    assert user_after.lifetimehours == 5.0
    assert user_after.pointsbalance == 50
    unlocked = db.session.query(StudentMilestone).filter_by(userid=user.id, milestoneid=milestone.milestoneid).first()
    assert unlocked is not None


def test_seeded_students_have_points_matching_hours_and_approved_claims_add_points():
    db = DummyDB()
    seeded = [
        ("bob", 53.0),
        ("milo", 48.0),
        ("nina", 30.0),
        ("omar", 19.0),
        ("priya", 8.0),
    ]
    for username, hours in seeded:
        user = User(
            username=username,
            email=f"{username}@example.com",
            password="pw",
            role="regular_user",
            lifetimehours=hours,
            pointsbalance=int(hours * 10),
        )
        db.session.add(user)
    db.session.commit()

    for username, hours in seeded:
        user = db.session.query(User).filter_by(username=username).one()
        assert user.pointsbalance == int(hours * 10)

    priya = db.session.query(User).filter_by(username="priya").one()
    claim = HoursClaim(
        userid=priya.id,
        activity="Reading club support",
        date=date.today(),
        hours=3.0,
        description="Helped run the reading club", 
        status="pending",
    )
    db.session.add(claim)
    db.session.commit()
    db.session.refresh(claim)

    service = HoursClaimService(db.session)
    service.review_claim(claim.claimid, priya.id, "approved")

    priya_after = db.session.get(User, priya.id)
    assert priya_after.lifetimehours == 11.0
    assert priya_after.pointsbalance == 110


def test_reject_claim_keeps_hours_unmet_and_sets_reason():
    db = DummyDB()
    user = User(username="stud2", email="stud2@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)

    claim = HoursClaim(userid=user.id, activity="Seminar", date=date.today(), hours=3.0, description="Event help", status="pending")
    db.session.add(claim)
    db.session.commit()
    db.session.refresh(claim)

    service = HoursClaimService(db.session)
    rejected = service.review_claim(claim.claimid, user.id, "rejected", "Missing proof")

    assert rejected.status == "rejected"
    assert rejected.rejectreason == "Missing proof"
    user_after = db.session.get(User, user.id)
    assert user_after.lifetimehours == 0


def test_submit_claim_route_creates_pending_claim_and_admin_queue_shows_it(monkeypatch, tmp_path):
    db_path = tmp_path / "hours_route_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="bob", email="bob@example.com", password=encrypt_password("bobpass"), role="student", lifetimehours=0, pointsbalance=0),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

    client = TestClient(app)

    bob_login = client.post("/login", data={"username": "bob", "password": "bobpass"}, follow_redirects=True)
    assert bob_login.status_code == 200
    assert "Volunteer claim submitted successfully" not in bob_login.text

    submit_response = client.post(
        "/hours/submit",
        data={
            "activity": "Community cleanup",
            "claim_date": "2026-10-11",
            "hours": 3.5,
            "description": "Helped at the park clean-up drive",
        },
        follow_redirects=True,
    )

    assert submit_response.status_code == 200
    assert "Volunteer claim submitted successfully" in submit_response.text
    assert "Lifetime hours" in submit_response.text
    assert "Community cleanup" not in submit_response.text

    admin_login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert admin_login.status_code == 200

    admin_page = client.get("/admin", follow_redirects=True)
    assert admin_page.status_code == 200
    assert "Community cleanup" in admin_page.text
    assert "No volunteer claims are awaiting review." not in admin_page.text


def test_admin_review_page_sorts_and_sections_pending_approved_rejected_claims(monkeypatch, tmp_path):
    db_path = tmp_path / "admin_review_sections.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

        pending_older = HoursClaim(
            userid=2,
            activity="Baking club",
            date=date(2026, 10, 1),
            hours=2.0,
            description="Served at the bake sale",
            status="pending",
        )
        pending_newer = HoursClaim(
            userid=2,
            activity="Park cleanup",
            date=date(2026, 10, 3),
            hours=3.0,
            description="Picked up litter",
            status="pending",
        )
        approved = HoursClaim(
            userid=2,
            activity="Library help",
            date=date(2026, 10, 5),
            hours=4.0,
            description="Sorted books",
            status="approved",
            reviewedby=1,
        )
        rejected = HoursClaim(
            userid=2,
            activity="Food drive",
            date=date(2026, 10, 6),
            hours=2.0,
            description="Packed food items",
            status="rejected",
            reviewedby=1,
            rejectreason="Missing proof",
        )
        session.add_all([pending_older, pending_newer, approved, rejected])
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert login.status_code == 200

    page = client.get("/admin", follow_redirects=True)
    assert page.status_code == 200
    assert "Pending review" in page.text
    assert "Approved" in page.text
    assert "Rejected" in page.text
    assert "Park cleanup" in page.text
    assert "Library help" in page.text
    assert "Food drive" in page.text

    assert page.text.index("Park cleanup") < page.text.index("Baking club")
    assert page.text.index("Library help") < page.text.index("Food drive")


def test_admin_review_tabs_show_counts_and_status_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "admin_review_tabs.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

        session.add_all([
            HoursClaim(userid=2, activity="Park cleanup", date=date(2026, 10, 3), hours=3.0, description="Picked up litter", status="pending"),
            HoursClaim(userid=2, activity="Library help", date=date(2026, 10, 5), hours=4.0, description="Sorted books", status="approved", reviewedby=1),
            HoursClaim(userid=2, activity="Food drive", date=date(2026, 10, 6), hours=2.0, description="Packed food items", status="rejected", reviewedby=1, rejectreason="Missing proof"),
        ])
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert login.status_code == 200

    page = client.get("/admin", follow_redirects=True)
    assert page.status_code == 200
    assert "Pending (1)" in page.text
    assert "Approved (1)" in page.text
    assert "Rejected (1)" in page.text
    assert "Approved hours" in page.text
    assert "Reason" in page.text
    assert "Review" in page.text


def test_student_dashboard_has_milestones_and_recent_activity(monkeypatch, tmp_path):
    db_path = tmp_path / "student_dashboard.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=25.0, pointsbalance=0),
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

        bronze = Milestone(name="Bronze", hoursrequired=10)
        silver = Milestone(name="Silver", hoursrequired=25)
        gold = Milestone(name="Gold", hoursrequired=50)
        session.add_all([bronze, silver, gold])
        session.commit()

        session.add(StudentMilestone(userid=1, milestoneid=bronze.milestoneid, unlockedat=date(2026, 10, 8)))
        session.add(StudentMilestone(userid=1, milestoneid=silver.milestoneid, unlockedat=date(2026, 10, 10)))
        session.add(HoursClaim(userid=1, activity="Park cleanup", date=date(2026, 10, 4), hours=4.0, description="Garden work", status="approved", reviewedby=2))
        session.add(HoursClaim(userid=1, activity="Food drive", date=date(2026, 10, 7), hours=2.0, description="Packed food", status="rejected", reviewedby=2, rejectreason="Missing proof"))
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "alice", "password": "pw"}, follow_redirects=True)
    assert login.status_code == 200

    page = client.get("/app", follow_redirects=True)
    assert page.status_code == 200
    assert "Milestones" in page.text
    assert "Unlocked" in page.text
    assert "Locked" in page.text
    assert "Recent activity" in page.text


def test_claim_proof_and_detail_review_flow(monkeypatch, tmp_path):
    db_path = tmp_path / "claim_proof_flow.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

        claim = HoursClaim(
            userid=2,
            activity="Beach cleanup",
            date=date(2026, 10, 10),
            hours=5.0,
            description="Organised a local clean-up.",
            proof="Supervisor: Sam Lee / sam@example.com",
            status="pending",
        )
        session.add(claim)
        session.commit()
        session.refresh(claim)

    client = TestClient(app)
    login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert login.status_code == 200

    admin_page = client.get("/admin", follow_redirects=True)
    assert admin_page.status_code == 200
    assert "Beach cleanup" in admin_page.text
    assert "Yes" in admin_page.text
    assert "Review" in admin_page.text

    detail = client.get(f"/admin/claims/{claim.claimid}", follow_redirects=True)
    assert detail.status_code == 200
    assert "Beach cleanup" in detail.text
    assert "Supervisor: Sam Lee / sam@example.com" in detail.text
    assert "Approve" in detail.text
    assert "Reject" in detail.text


def test_claim_proof_can_be_an_uploaded_image(monkeypatch, tmp_path):
    db_path = tmp_path / "claim_image_proof.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="admin", email="admin@example.com", password=encrypt_password("adminpass"), role="admin", lifetimehours=0, pointsbalance=0),
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="student", lifetimehours=0, pointsbalance=0),
        ])
        session.commit()

    client = TestClient(app)
    admin_login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert admin_login.status_code == 200

    response = client.post(
        "/hours/submit",
        data={
            "activity": "Beach cleanup",
            "claim_date": "2026-10-10",
            "hours": "5.0",
            "description": "Uploaded a photo of the volunteer work.",
        },
        files={"proof_image": ("proof.png", b"fake-image-bytes", "image/png")},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with Session(engine) as session:
        claim = session.exec(select(HoursClaim)).first()
        assert claim is not None
        assert claim.proof is not None
        assert "/static/uploads/" in claim.proof

    admin_page = client.get("/admin", follow_redirects=True)
    assert admin_page.status_code == 200
    assert "Beach cleanup" in admin_page.text
    assert "/static/uploads/" in admin_page.text or "Yes" in admin_page.text


def test_seeded_milestones_include_bronze_silver_gold():
    db = DummyDB()
    service = HoursClaimService(db.session)

    milestones = service.ensure_default_milestones()
    names = {milestone.name.lower() for milestone in milestones}

    assert {"bronze", "silver", "gold"}.issubset(names)
    bronze = next(item for item in milestones if item.name.lower() == "bronze")
    silver = next(item for item in milestones if item.name.lower() == "silver")
    gold = next(item for item in milestones if item.name.lower() == "gold")
    assert bronze.hoursrequired >= 10
    assert silver.hoursrequired > bronze.hoursrequired
    assert gold.hoursrequired > silver.hoursrequired


def test_student_leaderboard_ranks_users_by_lifetime_hours(monkeypatch, tmp_path):
    db_path = tmp_path / "leaderboard_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([
            User(username="alice", email="alice@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=10.0, pointsbalance=0),
            User(username="bob", email="bob@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=53.0, pointsbalance=0),
            User(username="charlie", email="charlie@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=18.0, pointsbalance=0),
            User(username="dana", email="dana@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=48.0, pointsbalance=0),
            User(username="erin", email="erin@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=30.0, pointsbalance=0),
            User(username="frank", email="frank@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=19.0, pointsbalance=0),
            User(username="gina", email="gina@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=8.0, pointsbalance=0),
            User(username="hugo", email="hugo@example.com", password=encrypt_password("pw"), role="regular_user", lifetimehours=62.0, pointsbalance=0),
            User(username="admin", email="admin@example.com", password=encrypt_password("pw"), role="admin", lifetimehours=90.0, pointsbalance=0),
        ])
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "bob", "password": "pw"}, follow_redirects=True)
    assert login.status_code == 200

    leaderboard_page = client.get("/app/leaderboard", follow_redirects=True)
    assert leaderboard_page.status_code == 200
    assert "Leaderboard" in leaderboard_page.text
    assert "bob" in leaderboard_page.text
    assert "alice" in leaderboard_page.text
    assert "charlie" in leaderboard_page.text
    assert "admin" not in leaderboard_page.text
    assert "(You)" in leaderboard_page.text

    service = HoursClaimService(Session(engine))
    leaderboard = service.get_leaderboard()
    ordered_hours = [entry["user"].lifetimehours for entry in leaderboard]
    assert ordered_hours == [62.0, 53.0, 48.0, 30.0, 19.0, 18.0, 10.0, 8.0]

    current_user_row = next(entry for entry in leaderboard if entry["user"].username == "bob")
    assert current_user_row["rank"] == 2


def test_gold_student_can_redeem_gold_reward(monkeypatch, tmp_path):
    db_path = tmp_path / "gold_reward_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            username="bob",
            email="bob@example.com",
            password=encrypt_password("bobpass"),
            role="regular_user",
            lifetimehours=53.0,
            pointsbalance=260,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        service = HoursClaimService(session)
        service.ensure_default_milestones()
        rewards = service.ensure_default_rewards()
        gold_reward = next(item for item in rewards if item.name == "Gold Access Pass")

        assert gold_reward.requiredmilestoneid is not None
        assert session.query(StudentMilestone).filter_by(userid=user.id, milestoneid=gold_reward.requiredmilestoneid).count() == 0

    client = TestClient(app)
    login = client.post("/login", data={"username": "bob", "password": "bobpass"}, follow_redirects=True)
    assert login.status_code == 200

    confirm_page = client.get(f"/app/rewards/confirm/{gold_reward.rewardid}", follow_redirects=True)
    assert confirm_page.status_code == 200
    assert "Confirm Redeem" in confirm_page.text
    assert "Lifetime hours and rank won't change" in confirm_page.text

    redeem_response = client.post(
        f"/app/rewards/confirm/{gold_reward.rewardid}",
        data={"staff_note": "Medium", "confirm_redeem": "1"},
        follow_redirects=True,
    )
    assert redeem_response.status_code == 200
    assert "Reward requested successfully" in redeem_response.text

    with Session(engine) as session:
        redemption = session.exec(select(Redemption)).first()
        assert redemption is not None
        assert redemption.staffnote == "Medium"


def test_redeem_and_cancel_update_stock_without_changing_stock_on_fulfill(monkeypatch, tmp_path):
    db_path = tmp_path / "reward_stock_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        student = User(
            username="stockuser",
            email="stock@example.com",
            password=encrypt_password("pw"),
            role="regular_user",
            lifetimehours=40.0,
            pointsbalance=200,
        )
        admin = User(
            username="adminstock",
            email="adminstock@example.com",
            password=encrypt_password("pw"),
            role="admin",
            lifetimehours=0,
            pointsbalance=0,
        )
        session.add_all([student, admin])
        session.commit()
        session.refresh(student)
        session.refresh(admin)

        service = HoursClaimService(session)
        service.ensure_default_milestones()
        rewards = service.ensure_default_rewards()
        reward = next(item for item in rewards if item.name == "Coffee Voucher")
        initial_stock = reward.stock
        assert initial_stock > 0

        redemption = service.redeem_reward(student.id, reward.rewardid)
        assert reward.stock == initial_stock - 1
        assert redemption.status == "requested"
        assert student.pointsbalance == 160
        assert session.get(type(reward), reward.rewardid).stock == initial_stock - 1

        service.process_redemption(redemption.redemptionid, admin.id, "fulfill")
        assert session.get(type(reward), reward.rewardid).stock == initial_stock - 1

        service.process_redemption(redemption.redemptionid, admin.id, "cancel")
        assert session.get(type(reward), reward.rewardid).stock == initial_stock
        student_after_cancel = session.get(User, student.id)
        assert student_after_cancel.pointsbalance == 200


def test_reward_stock_persists_in_db_and_zero_stock_blocks_redeem(monkeypatch, tmp_path):
    db_path = tmp_path / "reward_stock_persistence.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        student = User(
            username="stockwatch",
            email="stockwatch@example.com",
            password=encrypt_password("pw"),
            role="regular_user",
            lifetimehours=50.0,
            pointsbalance=200,
        )
        session.add(student)
        session.commit()
        session.refresh(student)

        service = HoursClaimService(session)
        service.ensure_default_milestones()
        rewards = service.ensure_default_rewards()
        reward = next(item for item in rewards if item.name == "Coffee Voucher")

        redemption = service.redeem_reward(student.id, reward.rewardid)
        assert session.get(type(reward), reward.rewardid).stock == reward.stock
        assert reward.stock == 5
        catalog = service.get_reward_catalog(student)
        coffee = next(item for item in catalog if item["reward"].name == "Coffee Voucher")
        assert coffee["reward"].stock == 5
        assert coffee["eligible"] is True

        reward_zero = next(item for item in service.repo.get_rewards() if item.name == "Out of Stock Tee")
        reward_zero.stock = 0
        session.add(reward_zero)
        session.commit()

        catalog_zero = service.get_reward_catalog(student)
        out_of_stock_entry = next(item for item in catalog_zero if item["reward"].name == "Out of Stock Tee")
        assert out_of_stock_entry["eligible"] is False
        assert "Out of stock" in out_of_stock_entry["reasons"]

        with pytest.raises(ValueError, match="out of stock"):
            service.redeem_reward(student.id, reward_zero.rewardid)


def test_student_views_are_split_by_wireframe(monkeypatch, tmp_path):
    db_path = tmp_path / "student_views_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(
                username="bob",
                email="bob@example.com",
                password=encrypt_password("bobpass"),
                role="student",
                lifetimehours=12.5,
                pointsbalance=150,
            )
        )
        session.commit()

        user = session.query(User).filter_by(username="bob").first()
        session.add(
            HoursClaim(
                userid=user.id,
                activity="Park cleanup",
                date=date(2026, 10, 5),
                hours=5.0,
                description="Helped clear litter at the community park",
                status="approved",
                rejectreason=None,
            )
        )
        session.add(
            HoursClaim(
                userid=user.id,
                activity="Food drive",
                date=date(2026, 10, 8),
                hours=3.0,
                description="Sorted donations for the food bank",
                status="rejected",
                rejectreason="Missing proof",
            )
        )
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "bob", "password": "bobpass"}, follow_redirects=True)
    assert login.status_code == 200

    dashboard = client.get("/app", follow_redirects=True)
    assert dashboard.status_code == 200
    assert "Lifetime hours" in dashboard.text
    assert "12.5" in dashboard.text
    assert "Log volunteer hours" in dashboard.text
    assert "Submit claim" not in dashboard.text

    hours_page = client.get("/hours", follow_redirects=True)
    assert hours_page.status_code == 200
    assert "Log volunteer hours" in hours_page.text
    assert "Submit claim" in hours_page.text
    assert "My claims" not in hours_page.text

    claims_page = client.get("/app/claims", follow_redirects=True)
    assert claims_page.status_code == 200
    assert "Park cleanup" in claims_page.text
    assert "Food drive" in claims_page.text
    assert "Approved hours" in claims_page.text
    assert "Reject reason" in claims_page.text
    assert "Missing proof" in claims_page.text


def test_reward_catalog_redemption_and_staff_processing(monkeypatch, tmp_path):
    db_path = tmp_path / "rewards_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        bob = User(
            username="bob",
            email="bob@example.com",
            password=encrypt_password("bobpass"),
            role="regular_user",
            lifetimehours=53.0,
            pointsbalance=550,
        )
        admin = User(
            username="admin",
            email="admin@example.com",
            password=encrypt_password("adminpass"),
            role="admin",
            lifetimehours=0,
            pointsbalance=0,
        )
        session.add_all([bob, admin])
        session.commit()
        session.refresh(bob)
        session.refresh(admin)

        service = HoursClaimService(session)
        service.ensure_default_milestones()
        rewards = service.ensure_default_rewards()
        gold = next(item for item in rewards if item.name == "Gold Access Pass")
        gold_reward_id = gold.rewardid
        session.add(
            StudentMilestone(
                userid=bob.id,
                milestoneid=gold.requiredmilestoneid,
            )
        )
        session.commit()

    client = TestClient(app)
    login = client.post("/login", data={"username": "bob", "password": "bobpass"}, follow_redirects=True)
    assert login.status_code == 200

    catalog = client.get("/app/rewards", follow_redirects=True)
    assert catalog.status_code == 200
    assert "Reward catalog" in catalog.text
    assert "Gold Access Pass" in catalog.text
    assert "Eligible" in catalog.text

    redeem_response = client.post(f"/app/rewards/redeem/{gold_reward_id}", follow_redirects=True)
    assert redeem_response.status_code == 200
    assert "Reward requested successfully" in redeem_response.text

    my_redemptions = client.get("/app/redemptions", follow_redirects=True)
    assert my_redemptions.status_code == 200
    assert "Requested" in my_redemptions.text
    assert "Gold Access Pass" in my_redemptions.text

    logout = client.get("/logout", follow_redirects=True)
    assert logout.status_code == 200

    admin_login = client.post("/login", data={"username": "admin", "password": "adminpass"}, follow_redirects=True)
    assert admin_login.status_code == 200

    staff_queue = client.get("/admin/redemptions", follow_redirects=True)
    assert staff_queue.status_code == 200
    assert "Requested" in staff_queue.text
    assert "Gold Access Pass" in staff_queue.text

    fulfill = client.post("/admin/redemptions/1/fulfill", follow_redirects=True)
    assert fulfill.status_code == 200
    assert "Fulfilled" in fulfill.text

    cancel = client.post("/admin/redemptions/1/cancel", follow_redirects=True)
    assert cancel.status_code == 200
    assert "Cancelled" in cancel.text
