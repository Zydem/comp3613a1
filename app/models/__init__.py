"""Database table models.

Import every table model here so ``SQLModel.metadata.create_all`` sees them.
"""

from app.models.user import User
from app.models.hours import HoursClaim, Milestone, StudentMilestone

__all__ = ["User", "HoursClaim", "Milestone", "StudentMilestone"]
