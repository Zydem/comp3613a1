from __future__ import annotations

from typing import Sequence

from sqlmodel import Session, select

from app.models.hours import HoursClaim, Milestone, Redemption, Reward, StudentMilestone


class HoursRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_claim(self, claim: HoursClaim) -> HoursClaim:
        self.db.add(claim)
        self.db.commit()
        self.db.refresh(claim)
        return claim

    def get_claims_for_user(self, user_id: int) -> list[HoursClaim]:
        return self.db.exec(select(HoursClaim).where(HoursClaim.userid == user_id)).all()

    def get_pending_claims(self) -> list[HoursClaim]:
        return self.db.exec(
            select(HoursClaim)
            .where(HoursClaim.status == "pending")
            .order_by(HoursClaim.date.desc(), HoursClaim.claimid.desc())
        ).all()

    def get_claims_by_status(self, status: str) -> list[HoursClaim]:
        return self.db.exec(
            select(HoursClaim)
            .where(HoursClaim.status == status)
            .order_by(HoursClaim.date.desc(), HoursClaim.claimid.desc())
        ).all()

    def get_claim(self, claim_id: int) -> HoursClaim | None:
        return self.db.get(HoursClaim, claim_id)

    def save(self, claim: HoursClaim) -> HoursClaim:
        self.db.add(claim)
        self.db.commit()
        self.db.refresh(claim)
        return claim

    def get_milestones(self) -> Sequence[Milestone]:
        return self.db.exec(select(Milestone).order_by(Milestone.hoursrequired)).all()

    def get_milestone_by_name(self, name: str) -> Milestone | None:
        return self.db.exec(select(Milestone).where(Milestone.name == name)).one_or_none()

    def create_milestone(self, milestone: Milestone) -> Milestone:
        self.db.add(milestone)
        self.db.commit()
        self.db.refresh(milestone)
        return milestone

    def get_student_milestone(self, user_id: int, milestone_id: int) -> StudentMilestone | None:
        return self.db.exec(
            select(StudentMilestone).where(
                StudentMilestone.userid == user_id,
                StudentMilestone.milestoneid == milestone_id,
            )
        ).one_or_none()

    def create_student_milestone(self, milestone: StudentMilestone) -> StudentMilestone:
        self.db.add(milestone)
        self.db.commit()
        self.db.refresh(milestone)
        return milestone

    def get_rewards(self) -> Sequence[Reward]:
        return self.db.exec(select(Reward).order_by(Reward.pointscost)).all()

    def get_reward_by_id(self, reward_id: int) -> Reward | None:
        return self.db.get(Reward, reward_id)

    def create_reward(self, reward: Reward) -> Reward:
        self.db.add(reward)
        self.db.commit()
        self.db.refresh(reward)
        return reward

    def get_all_redemptions(self) -> Sequence[Redemption]:
        return self.db.exec(select(Redemption).order_by(Redemption.createdat.desc())).all()

    def get_redemptions_for_user(self, user_id: int) -> Sequence[Redemption]:
        return self.db.exec(
            select(Redemption).where(Redemption.userid == user_id).order_by(Redemption.createdat.desc())
        ).all()

    def get_redemption(self, redemption_id: int) -> Redemption | None:
        return self.db.get(Redemption, redemption_id)

    def create_redemption(self, redemption: Redemption) -> Redemption:
        self.db.add(redemption)
        self.db.commit()
        self.db.refresh(redemption)
        return redemption

    def save_redemption(self, redemption: Redemption) -> Redemption:
        self.db.add(redemption)
        self.db.commit()
        self.db.refresh(redemption)
        return redemption
