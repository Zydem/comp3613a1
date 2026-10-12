from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.models.hours import HoursClaim, Milestone, Redemption, Reward, StudentMilestone
from app.models.user import User
from app.repositories.hours import HoursRepository


class HoursClaimService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = HoursRepository(db)

    def submit_claim(
        self,
        user_id: int,
        activity: str,
        claim_date: date,
        hours: float,
        description: str,
        proof: str | None = None,
    ) -> HoursClaim:
        if not activity or not description:
            raise ValueError("Activity and description are required.")
        if hours <= 0:
            raise ValueError("Hours must be greater than zero.")

        claim = HoursClaim(
            userid=user_id,
            activity=activity,
            date=claim_date,
            hours=hours,
            description=description,
            proof=proof.strip() if proof and proof.strip() else None,
            status="pending",
        )
        return self.repo.create_claim(claim)

    def review_claim(
        self,
        claim_id: int,
        reviewer_id: int,
        decision: str,
        reject_reason: str | None = None,
        adjusted_hours: float | None = None,
    ) -> HoursClaim:
        claim = self.repo.get_claim(claim_id)
        if claim is None:
            raise ValueError("Claim not found.")

        decision = decision.lower().strip()
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected.")

        claim.status = decision
        claim.reviewedby = reviewer_id
        claim.rejectreason = reject_reason if decision == "rejected" else None

        if decision == "approved":
            approved_hours = float(adjusted_hours) if adjusted_hours is not None else float(claim.hours)
            if approved_hours <= 0:
                raise ValueError("Approved hours must be greater than zero.")
            claim.hours = approved_hours

            user = self.db.get(User, claim.userid)
            if user is None:
                raise ValueError("User not found for claim.")
            user.lifetimehours = (user.lifetimehours or 0.0) + approved_hours
            user.pointsbalance = (user.pointsbalance or 0) + int(approved_hours * 10)
            self.sync_user_milestones(user)

        return self.repo.save(claim)

    def sync_user_milestones(self, user: User | int) -> list[Milestone]:
        if isinstance(user, int):
            user = self.db.get(User, user)
        if user is None:
            return []

        unlocked: list[Milestone] = []
        for milestone in self.repo.get_milestones():
            if (user.lifetimehours or 0.0) >= milestone.hoursrequired:
                existing = self.repo.get_student_milestone(user.id, milestone.milestoneid)
                if existing is None:
                    self.repo.create_student_milestone(
                        StudentMilestone(
                            userid=user.id,
                            milestoneid=milestone.milestoneid,
                        )
                    )
                unlocked.append(milestone)
        return unlocked

    def has_unlocked_milestone(self, user: User | int, milestone_id: int) -> bool:
        if isinstance(user, int):
            user = self.db.get(User, user)
        if user is None:
            return False

        self.sync_user_milestones(user)
        return self.repo.get_student_milestone(user.id, milestone_id) is not None

    def get_pending_claims(self) -> list[HoursClaim]:
        return self.repo.get_pending_claims()

    def get_claims_by_status(self, status: str) -> list[HoursClaim]:
        return self.repo.get_claims_by_status(status)

    def get_claims_for_user(self, user_id: int) -> list[HoursClaim]:
        return self.repo.get_claims_for_user(user_id)

    def ensure_default_milestones(self) -> list[Milestone]:
        defaults = [
            ("Bronze", 10),
            ("Silver", 25),
            ("Gold", 50),
        ]

        milestones: list[Milestone] = []
        for name, total_hours in defaults:
            milestone = self.repo.get_milestone_by_name(name)
            if milestone is None:
                milestone = self.repo.create_milestone(Milestone(name=name, hoursrequired=total_hours))
            milestones.append(milestone)

        return list(self.repo.get_milestones())

    def get_all_milestones(self) -> list[Milestone]:
        return list(self.repo.get_milestones())

    def get_leaderboard(self) -> list[dict]:
        users = self.db.exec(
            select(User)
            .where(User.role != "admin")
            .order_by(User.lifetimehours.desc(), User.username.asc())
        ).all()

        leaderboard = []
        for index, user in enumerate(users, start=1):
            milestone = self.get_current_milestone_for_hours(float(user.lifetimehours or 0.0))
            leaderboard.append({
                "rank": index,
                "user": user,
                "milestone": milestone,
            })
        return leaderboard

    def get_current_milestone_for_hours(self, hours: float) -> Milestone | None:
        current: Milestone | None = None
        for milestone in self.get_all_milestones():
            if hours >= milestone.hoursrequired:
                current = milestone
            else:
                break
        return current

    def get_next_milestone_for_hours(self, hours: float) -> Milestone | None:
        for milestone in self.get_all_milestones():
            if hours < milestone.hoursrequired:
                return milestone
        return None

    def ensure_default_rewards(self) -> list[Reward]:
        gold_milestone = self.repo.get_milestone_by_name("Gold")
        defaults = [
            ("Coffee Voucher", "Warm-up treat for volunteer hours.", 40, 6, None),
            ("Lunch Pass", "One meal voucher for campus dining.", 90, 4, None),
            ("Campus Hoodie", "A branded hoodie for our top contributors.", 120, 3, None),
            ("Gold Access Pass", "VIP admission to the leadership summit.", 260, 1, gold_milestone.milestoneid if gold_milestone else None),
            ("Conference Ticket", "Priority entry to the community conference.", 220, 2, None),
            ("Out of Stock Tee", "This merchandise is currently unavailable.", 60, 0, None),
        ]

        existing_rewards = list(self.repo.get_rewards())
        for name, description, point_cost, stock, required_milestone_id in defaults:
            existing = next((item for item in existing_rewards if item.name == name), None)
            if existing is None:
                existing = self.repo.create_reward(
                    Reward(
                        name=name,
                        description=description,
                        pointscost=point_cost,
                        stock=stock,
                        requiredmilestoneid=required_milestone_id,
                    )
                )
            else:
                existing.description = description
                existing.pointscost = point_cost
                existing.requiredmilestoneid = required_milestone_id
                self.db.add(existing)
                self.db.commit()
                self.db.refresh(existing)
            existing_rewards = list(self.repo.get_rewards())

        return list(self.repo.get_rewards())

    def get_reward_catalog(self, user: User) -> list[dict]:
        self.ensure_default_rewards()
        self.sync_user_milestones(user)
        entries: list[dict] = []
        for reward in self.repo.get_rewards():
            reasons: list[str] = []
            if reward.stock <= 0:
                reasons.append("Out of stock")
            if reward.pointscost > (user.pointsbalance or 0):
                reasons.append("Not enough points")
            if reward.requiredmilestoneid is not None:
                required = self.db.get(Milestone, reward.requiredmilestoneid)
                milestone_owned = self.has_unlocked_milestone(user, reward.requiredmilestoneid)
                if not milestone_owned:
                    reasons.append(f"Requires {required.name if required else 'milestone'}")

            entries.append({
                "reward": reward,
                "eligible": not reasons,
                "reasons": reasons,
            })
        return entries

    def redeem_reward(self, user_id: int, reward_id: int, staff_note: str | None = None) -> Redemption:
        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found.")

        reward = self.repo.get_reward_by_id(reward_id)
        if reward is None:
            raise ValueError("Reward not found.")

        self.sync_user_milestones(user)

        reasons: list[str] = []
        if reward.stock <= 0:
            reasons.append("out of stock")
        if user.pointsbalance < reward.pointscost:
            reasons.append("not enough points")
        if reward.requiredmilestoneid is not None:
            required = self.db.get(Milestone, reward.requiredmilestoneid)
            owned = self.has_unlocked_milestone(user, reward.requiredmilestoneid)
            if not owned:
                reasons.append(f"requires {required.name if required else 'the required milestone'}")

        if reasons:
            raise ValueError("Reward is locked: " + "; ".join(reasons))

        note = (staff_note or "").strip() or None
        user.pointsbalance -= reward.pointscost
        reward.stock -= 1
        redemption = Redemption(
            userid=user_id,
            rewardid=reward_id,
            pointsspent=reward.pointscost,
            status="requested",
            staffnote=note,
        )
        self.db.add(user)
        self.db.add(reward)
        self.repo.create_redemption(redemption)
        return redemption

    def process_redemption(self, redemption_id: int, staff_id: int, action: str) -> Redemption:
        redemption = self.repo.get_redemption(redemption_id)
        if redemption is None:
            raise ValueError("Redemption not found.")

        action = action.lower().strip()
        if action not in {"fulfill", "cancel"}:
            raise ValueError("Action must be fulfill or cancel.")

        reward = self.repo.get_reward_by_id(redemption.rewardid)
        user = self.db.get(User, redemption.userid)

        if action == "fulfill":
            if redemption.status == "fulfilled":
                return redemption
            redemption.status = "fulfilled"
            redemption.processedby = staff_id
        elif action == "cancel":
            if redemption.status == "cancelled":
                return redemption
            redemption.status = "cancelled"
            redemption.processedby = staff_id
            if user is not None:
                user.pointsbalance += redemption.pointsspent
            if reward is not None:
                reward.stock += 1
            self.db.add(user) if user is not None else None
            self.db.add(reward) if reward is not None else None

        self.db.add(redemption)
        self.db.commit()
        self.db.refresh(redemption)
        return redemption

    def get_redemptions_for_user(self, user_id: int) -> list[Redemption]:
        return list(self.repo.get_redemptions_for_user(user_id))

    def get_all_redemptions(self) -> list[Redemption]:
        return list(self.repo.get_all_redemptions())
