from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.hours import HoursClaim, Milestone, Reward
from app.models.user import User
from app.services.hours_service import HoursClaimService


@pytest.fixture
def mem_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_ut01_approve_claim_updates_user_hours_and_unlocks_milestone(mem_session):
    user = User(username="stud1", email="stud1@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    milestone = Milestone(name="Bronze", hoursrequired=5)
    mem_session.add(milestone)
    mem_session.commit()
    mem_session.refresh(milestone)

    claim = HoursClaim(userid=user.id, activity="Volunteer", date=date.today(), hours=5.0, description="Community work", status="pending")
    mem_session.add(claim)
    mem_session.commit()
    mem_session.refresh(claim)

    service = HoursClaimService(mem_session)
    approved = service.review_claim(claim.claimid, user.id, "approved", None, adjusted_hours=5.0)

    assert approved.status == "approved"
    assert mem_session.get(User, user.id).lifetimehours == 5.0
    assert mem_session.get(User, user.id).pointsbalance == 50
    assert mem_session.query(type(approved)).count() == 1

    unlocked = mem_session.query(__import__("app.models.hours", fromlist=["StudentMilestone"]).StudentMilestone).filter_by(userid=user.id, milestoneid=milestone.milestoneid).first()
    assert unlocked is not None


def test_ut02_seeded_students_points_match_hours_and_approved_claims_add_points(mem_session):
    seeded = [("bob", 53.0), ("milo", 48.0), ("nina", 30.0), ("omar", 19.0), ("priya", 8.0)]
    for username, hours in seeded:
        mem_session.add(User(username=username, email=f"{username}@example.com", password="pw", role="student", lifetimehours=hours, pointsbalance=int(hours * 10)))
    mem_session.commit()

    for username, hours in seeded:
        user = mem_session.query(User).filter_by(username=username).one()
        assert user.pointsbalance == int(hours * 10)

    priya = mem_session.query(User).filter_by(username="priya").one()
    claim = HoursClaim(userid=priya.id, activity="Reading club support", date=date.today(), hours=3.0, description="Helped run the reading club", status="pending")
    mem_session.add(claim)
    mem_session.commit()
    mem_session.refresh(claim)

    service = HoursClaimService(mem_session)
    service.review_claim(claim.claimid, priya.id, "approved", adjusted_hours=3.0)

    priya_after = mem_session.get(User, priya.id)
    assert priya_after.lifetimehours == 11.0
    assert priya_after.pointsbalance == 110


def test_ut03_reject_claim_keeps_hours_unmet_and_sets_reason(mem_session):
    user = User(username="stud2", email="stud2@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    claim = HoursClaim(userid=user.id, activity="Seminar", date=date.today(), hours=3.0, description="Event help", status="pending")
    mem_session.add(claim)
    mem_session.commit()
    mem_session.refresh(claim)

    service = HoursClaimService(mem_session)
    rejected = service.review_claim(claim.claimid, user.id, "rejected", "Missing proof")

    assert rejected.status == "rejected"
    assert rejected.rejectreason == "Missing proof"
    assert mem_session.get(User, user.id).lifetimehours == 0
    assert mem_session.get(User, user.id).pointsbalance == 0


def test_ut04_seeded_milestones_include_bronze_silver_gold(mem_session):
    service = HoursClaimService(mem_session)
    milestones = service.ensure_default_milestones()
    names = {milestone.name.lower() for milestone in milestones}

    assert {"bronze", "silver", "gold"}.issubset(names)
    bronze = next(item for item in milestones if item.name.lower() == "bronze")
    silver = next(item for item in milestones if item.name.lower() == "silver")
    gold = next(item for item in milestones if item.name.lower() == "gold")
    assert bronze.hoursrequired >= 10
    assert silver.hoursrequired > bronze.hoursrequired
    assert gold.hoursrequired > silver.hoursrequired


def test_ut05_reward_redemption_reduces_points_and_stock(mem_session):
    user = User(username="spender", email="spender@example.com", password="pw", role="student", lifetimehours=40.0, pointsbalance=200)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    service = HoursClaimService(mem_session)
    service.ensure_default_milestones()
    rewards = service.ensure_default_rewards()
    reward = next(item for item in rewards if item.name == "Coffee Voucher")
    initial_stock = reward.stock

    redemption = service.redeem_reward(user.id, reward.rewardid)

    assert redemption.status == "requested"
    assert mem_session.get(User, user.id).pointsbalance == 160
    assert mem_session.get(type(reward), reward.rewardid).stock == initial_stock - 1


def test_ut06_zero_stock_blocks_redeem(mem_session):
    user = User(username="stockwatch", email="stockwatch@example.com", password="pw", role="student", lifetimehours=50.0, pointsbalance=200)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    service = HoursClaimService(mem_session)
    service.ensure_default_milestones()
    rewards = service.ensure_default_rewards()
    reward = next(item for item in rewards if item.name == "Coffee Voucher")
    reward.stock = 0
    mem_session.add(reward)
    mem_session.commit()

    with pytest.raises(ValueError, match="out of stock"):
        service.redeem_reward(user.id, reward.rewardid)


def test_ut07_cancelled_redemption_restores_points_and_stock(mem_session):
    student = User(username="stockuser", email="stock@example.com", password="pw", role="student", lifetimehours=40.0, pointsbalance=200)
    admin = User(username="adminstock", email="adminstock@example.com", password="pw", role="admin", lifetimehours=0, pointsbalance=0)
    mem_session.add_all([student, admin])
    mem_session.commit()
    mem_session.refresh(student)
    mem_session.refresh(admin)

    service = HoursClaimService(mem_session)
    service.ensure_default_milestones()
    rewards = service.ensure_default_rewards()
    reward = next(item for item in rewards if item.name == "Coffee Voucher")
    initial_stock = reward.stock

    redemption = service.redeem_reward(student.id, reward.rewardid)
    service.process_redemption(redemption.redemptionid, admin.id, "cancel")

    assert mem_session.get(User, student.id).pointsbalance == 200
    assert mem_session.get(type(reward), reward.rewardid).stock == initial_stock


def test_ut08_hours_of_zero_or_over_24_are_rejected_no_claim_saved(mem_session):
    user = User(username="badhours", email="badhours@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    service = HoursClaimService(mem_session)
    with pytest.raises(ValueError, match="greater than zero and no more than 24"):
        service.submit_claim(user.id, "Beach clean-up", date.today(), 0, "Cleaned the beach")
    with pytest.raises(ValueError, match="greater than zero and no more than 24"):
        service.submit_claim(user.id, "Beach clean-up", date.today(), 30, "Cleaned the beach")

    assert mem_session.query(HoursClaim).count() == 0


def test_ut09_reject_without_reason_fails_claim_stays_pending(mem_session):
    user = User(username="noreason", email="noreason@example.com", password="pw", role="student", lifetimehours=0, pointsbalance=0)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    claim = HoursClaim(userid=user.id, activity="Seminar", date=date.today(), hours=3.0, description="Event help", status="pending")
    mem_session.add(claim)
    mem_session.commit()
    mem_session.refresh(claim)

    service = HoursClaimService(mem_session)
    with pytest.raises(ValueError, match="A rejection reason is required"):
        service.review_claim(claim.claimid, user.id, "rejected", reject_reason="   ")

    latest = mem_session.get(HoursClaim, claim.claimid)
    assert latest.status == "pending"
    assert latest.rejectreason is None


def test_ut10_gold_reward_is_not_eligible_for_non_gold_student(mem_session):
    user = User(username="non_gold", email="non_gold@example.com", password="pw", role="student", lifetimehours=40.0, pointsbalance=500)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    service = HoursClaimService(mem_session)
    service.ensure_default_milestones()
    rewards = service.ensure_default_rewards()
    gold_reward = next(item for item in rewards if item.name == "Gold Access Pass")

    catalog = service.get_reward_catalog(user)
    gold_entry = next(item for item in catalog if item["reward"].name == "Gold Access Pass")
    assert gold_entry["eligible"] is False
    assert any("Gold" in reason for reason in gold_entry["reasons"])

    with pytest.raises(ValueError, match="Reward is locked"):
        service.redeem_reward(user.id, gold_reward.rewardid)


def test_ut11_approving_already_processed_claim_fails_totals_not_doubled(mem_session):
    user = User(username="double", email="double@example.com", password="pw", role="student", lifetimehours=5.0, pointsbalance=50)
    mem_session.add(user)
    mem_session.commit()
    mem_session.refresh(user)

    claim = HoursClaim(userid=user.id, activity="Already approved", date=date.today(), hours=3.0, description="Done", status="approved", reviewedby=user.id)
    mem_session.add(claim)
    mem_session.commit()
    mem_session.refresh(claim)

    service = HoursClaimService(mem_session)
    with pytest.raises(ValueError, match="already been processed"):
        service.review_claim(claim.claimid, user.id, "approved", adjusted_hours=10.0)

    refreshed = mem_session.get(User, user.id)
    assert refreshed.lifetimehours == 5.0
    assert refreshed.pointsbalance == 50


def test_ut12_fulfilling_redemption_keeps_points_and_stock_unchanged(mem_session):
    student = User(username="fulfill", email="fulfill@example.com", password="pw", role="student", lifetimehours=40.0, pointsbalance=200)
    admin = User(username="adminfulfill", email="adminfulfill@example.com", password="pw", role="admin", lifetimehours=0, pointsbalance=0)
    mem_session.add_all([student, admin])
    mem_session.commit()
    mem_session.refresh(student)
    mem_session.refresh(admin)

    service = HoursClaimService(mem_session)
    service.ensure_default_milestones()
    rewards = service.ensure_default_rewards()
    reward = next(item for item in rewards if item.name == "Coffee Voucher")
    expected_stock = reward.stock

    redemption = service.redeem_reward(student.id, reward.rewardid)
    service.process_redemption(redemption.redemptionid, admin.id, "fulfill")

    assert mem_session.get(User, student.id).pointsbalance == 160
    assert mem_session.get(type(reward), reward.rewardid).stock == expected_stock - 1
