from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class HoursClaim(SQLModel, table=True):
    claimid: Optional[int] = Field(default=None, primary_key=True)
    userid: int = Field(foreign_key="user.id", index=True)
    activity: str
    date: date
    hours: float = 0.0
    description: str
    proof: Optional[str] = None
    status: str = "pending"
    reviewedby: Optional[int] = Field(default=None, foreign_key="user.id")
    rejectreason: Optional[str] = None


class Milestone(SQLModel, table=True):
    milestoneid: Optional[int] = Field(default=None, primary_key=True)
    name: str
    hoursrequired: int


class StudentMilestone(SQLModel, table=True):
    userid: int = Field(foreign_key="user.id", primary_key=True)
    milestoneid: int = Field(foreign_key="milestone.milestoneid", primary_key=True)
    unlockedat: datetime = Field(default_factory=datetime.utcnow)


class Reward(SQLModel, table=True):
    rewardid: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str
    pointscost: int = 0
    stock: int = 0
    requiredmilestoneid: Optional[int] = Field(default=None, foreign_key="milestone.milestoneid")


class Redemption(SQLModel, table=True):
    redemptionid: Optional[int] = Field(default=None, primary_key=True)
    userid: int = Field(foreign_key="user.id", index=True)
    rewardid: int = Field(foreign_key="reward.rewardid", index=True)
    pointsspent: int = 0
    status: str = "requested"
    staffnote: Optional[str] = None
    processedby: Optional[int] = Field(default=None, foreign_key="user.id")
    createdat: datetime = Field(default_factory=datetime.utcnow)
