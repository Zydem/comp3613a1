from datetime import date

from fastapi import Body, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.dependencies import SessionDep
from app.dependencies.auth import ApiAdminDep, ApiAuthDep
from app.repositories.user import UserRepository
from app.services.auth_service import AuthService
from app.services.hours_service import HoursClaimService
from app.services.user_service import UserService
from app.utilities.security import access_token_cookie_kwargs
from app.schemas import UserResponse
from . import api_router


def _role_allowed(user, allowed: set[str]) -> bool:
    if user.role in allowed:
        return True
    if "student" in allowed and user.role in {"regular_user", "student"}:
        return True
    if "staff" in allowed and user.role in {"admin", "staff"}:
        return True
    return False


def _json_error(message: str, status_code: int):
    raise HTTPException(status_code=status_code, detail=message)


def _serialize_claim(claim):
    payload = jsonable_encoder(claim)
    if payload.get("date"):
        payload["date"] = claim.date.isoformat()
    return payload


def _serialize_redemption(redemption):
    payload = jsonable_encoder(redemption)
    if payload.get("createdat"):
        payload["createdat"] = redemption.createdat.isoformat()
    return payload


@api_router.post("/auth/login")
async def api_login(request: Request, db: SessionDep, payload: dict | None = Body(default=None)):
    if payload is None:
        payload = await request.json()

    username = str(payload.get("username", "") or "").strip()
    password = str(payload.get("password", "") or "").strip()

    if not username or not password:
        _json_error("Username and password are required.", status.HTTP_400_BAD_REQUEST)

    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)
    access_token = auth_service.authenticate_user(username, password)
    if not access_token:
        _json_error("Invalid username or password.", status.HTTP_401_UNAUTHORIZED)

    user = user_repo.get_by_username(username)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"id": user.id, "username": user.username, "role": user.role},
        },
    )
    response.set_cookie(key="access_token", value=access_token, **access_token_cookie_kwargs())
    return response


@api_router.post("/auth/logout")
async def api_logout(request: Request):
    response = JSONResponse({"message": "Logged out successfully."})
    response.delete_cookie("access_token")
    return response


@api_router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, db: SessionDep, user: ApiAdminDep):
    user_repo = UserRepository(db)
    user_service = UserService(user_repo)
    return user_service.get_all_users()


@api_router.post("/claims")
async def create_claim(request: Request, user: ApiAuthDep, db: SessionDep, payload: dict | None = Body(default=None)):
    if payload is None:
        payload = await request.json()

    activity = str(payload.get("activity", "") or "").strip()
    description = str(payload.get("description", "") or "").strip()
    hours_raw = payload.get("hours")
    proof = payload.get("proof")
    date_raw = payload.get("date")

    if not activity or not description:
        _json_error("Activity and description are required.", status.HTTP_400_BAD_REQUEST)
    try:
        hours_value = float(hours_raw)
    except (TypeError, ValueError):
        _json_error("Hours must be a valid number.", status.HTTP_400_BAD_REQUEST)
    if hours_value <= 0 or hours_value > 24:
        _json_error("Hours must be greater than zero and no more than 24.", status.HTTP_400_BAD_REQUEST)
    try:
        claim_date = date.fromisoformat(str(date_raw))
    except (TypeError, ValueError):
        _json_error("Date must be a valid ISO date string.", status.HTTP_400_BAD_REQUEST)

    service = HoursClaimService(db)
    claim = service.submit_claim(
        user_id=user.id,
        activity=activity,
        claim_date=claim_date,
        hours=hours_value,
        description=description,
        proof=str(proof).strip() if proof is not None and str(proof).strip() else None,
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"message": "Claim submitted successfully.", "claim": _serialize_claim(claim)})


@api_router.get("/claims/me")
async def list_my_claims(user: ApiAuthDep, db: SessionDep):
    if not _role_allowed(user, {"student"}):
        _json_error("Only students can access their own claims.", status.HTTP_403_FORBIDDEN)
    service = HoursClaimService(db)
    claims = service.get_claims_for_user(user.id)
    return [_serialize_claim(claim) for claim in claims]


@api_router.get("/claims")
async def list_claims(user: ApiAdminDep, db: SessionDep, status: str | None = None):
    if not _role_allowed(user, {"staff"}):
        _json_error("Only staff or admins can access claim queues.", status.HTTP_403_FORBIDDEN)
    service = HoursClaimService(db)
    if status:
        allowed = {"pending", "approved", "rejected"}
        normalized = status.lower()
        if normalized not in allowed:
            _json_error("status must be pending, approved, or rejected.", status.HTTP_400_BAD_REQUEST)
        claims = service.get_claims_by_status(normalized)
    else:
        claims = service.get_pending_claims() + service.get_claims_by_status("approved") + service.get_claims_by_status("rejected")
    return [_serialize_claim(claim) for claim in claims]


@api_router.get("/claims/{claim_id}")
async def get_claim(user: ApiAuthDep, db: SessionDep, claim_id: int):
    service = HoursClaimService(db)
    claim = service.repo.get_claim(claim_id)
    if claim is None:
        _json_error("Claim not found.", status.HTTP_404_NOT_FOUND)
    if user.role in {"admin", "staff"} or claim.userid == user.id:
        return _serialize_claim(claim)
    _json_error("You do not have access to this claim.", status.HTTP_403_FORBIDDEN)


@api_router.patch("/claims/{claim_id}")
async def patch_claim(user: ApiAdminDep, db: SessionDep, claim_id: int, payload: dict | None = Body(default=None)):
    if payload is None:
        payload = {}

    service = HoursClaimService(db)
    claim = service.repo.get_claim(claim_id)
    if claim is None:
        _json_error("Claim not found.", status.HTTP_404_NOT_FOUND)
    if claim.status != "pending":
        _json_error("This claim has already been processed.", status.HTTP_409_CONFLICT)

    action = str(payload.get("action", "") or "").strip().lower()
    if action not in {"approve", "reject"}:
        _json_error("Action must be 'approve' or 'reject'.", status.HTTP_400_BAD_REQUEST)

    if action == "reject":
        reason = str(payload.get("reason", "") or "").strip()
        if not reason:
            _json_error("A rejection reason is required.", status.HTTP_400_BAD_REQUEST)
        updated = service.review_claim(claim_id, user.id, "rejected", reject_reason=reason)
        return {"message": "Claim rejected.", "claim": _serialize_claim(updated)}

    approved_hours = payload.get("hours", claim.hours)
    try:
        approved_hours_value = float(approved_hours)
    except (TypeError, ValueError):
        _json_error("Approved hours must be a valid number.", status.HTTP_400_BAD_REQUEST)
    if approved_hours_value <= 0 or approved_hours_value > 24:
        _json_error("Approved hours must be greater than zero and no more than 24.", status.HTTP_400_BAD_REQUEST)
    updated = service.review_claim(claim_id, user.id, "approved", adjusted_hours=approved_hours_value)
    return {"message": "Claim approved.", "claim": _serialize_claim(updated)}


@api_router.get("/me/progress")
async def get_my_progress(user: ApiAuthDep, db: SessionDep):
    if not _role_allowed(user, {"student"}):
        _json_error("Only students can access progress data.", status.HTTP_403_FORBIDDEN)
    service = HoursClaimService(db)
    service.ensure_default_milestones()
    service.sync_user_milestones(user)
    lifetime_hours = float(user.lifetimehours or 0.0)
    current = service.get_current_milestone_for_hours(lifetime_hours)
    next_milestone = service.get_next_milestone_for_hours(lifetime_hours)
    milestone_rows = []
    for milestone in service.get_all_milestones():
        record = service.repo.get_student_milestone(user.id, milestone.milestoneid)
        milestone_rows.append(
            {
                "id": milestone.milestoneid,
                "name": milestone.name,
                "hours_required": milestone.hoursrequired,
                "unlocked": record is not None,
                "unlocked_at": record.unlockedat.isoformat() if record else None,
            }
        )
    return {
        "user_id": user.id,
        "username": user.username,
        "lifetime_hours": lifetime_hours,
        "points": int(user.pointsbalance or 0),
        "rank": next((entry["rank"] for entry in service.get_leaderboard() if entry["user"].id == user.id), None),
        "current_milestone": {"id": current.milestoneid, "name": current.name, "hours_required": current.hoursrequired} if current else None,
        "next_milestone": {"id": next_milestone.milestoneid, "name": next_milestone.name, "hours_required": next_milestone.hoursrequired} if next_milestone else None,
        "unlocked_milestones": milestone_rows,
    }


@api_router.get("/leaderboard")
async def get_leaderboard(user: ApiAuthDep, db: SessionDep):
    service = HoursClaimService(db)
    leaderboard = []
    for item in service.get_leaderboard():
        leaderboard.append(
            {
                "rank": item["rank"],
                "user_id": item["user"].id,
                "username": item["user"].username,
                "lifetime_hours": float(item["user"].lifetimehours or 0.0),
                "points": int(item["user"].pointsbalance or 0),
                "current_milestone": {"name": item["milestone"].name, "hours_required": item["milestone"].hoursrequired} if item["milestone"] else None,
            }
        )
    return leaderboard


@api_router.get("/rewards")
async def list_rewards(user: ApiAuthDep, db: SessionDep):
    service = HoursClaimService(db)
    catalog = service.get_reward_catalog(user)
    rewards = []
    for entry in catalog:
        reward = entry["reward"]
        rewards.append(
            {
                "reward_id": reward.rewardid,
                "name": reward.name,
                "description": reward.description,
                "point_cost": reward.pointscost,
                "stock": reward.stock,
                "required_milestone_id": reward.requiredmilestoneid,
                "eligible": entry["eligible"],
                "reasons": entry["reasons"],
            }
        )
    return rewards


@api_router.post("/redemptions")
async def create_redemption(user: ApiAuthDep, db: SessionDep, payload: dict | None = Body(default=None)):
    if payload is None:
        payload = {}
    if not _role_allowed(user, {"student"}):
        _json_error("Only students can redeem rewards.", status.HTTP_403_FORBIDDEN)
    reward_id = payload.get("reward_id")
    try:
        reward_id_value = int(reward_id)
    except (TypeError, ValueError):
        _json_error("reward_id must be an integer.", status.HTTP_400_BAD_REQUEST)
    if reward_id_value <= 0:
        _json_error("reward_id must be positive.", status.HTTP_400_BAD_REQUEST)
    service = HoursClaimService(db)
    try:
        redemption = service.redeem_reward(user.id, reward_id_value)
    except ValueError as exc:
        _json_error(str(exc), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"message": "Reward requested successfully.", "redemption": _serialize_redemption(redemption)})


@api_router.get("/redemptions/me")
async def list_my_redemptions(user: ApiAuthDep, db: SessionDep):
    if not _role_allowed(user, {"student"}):
        _json_error("Only students can access their redemptions.", status.HTTP_403_FORBIDDEN)
    service = HoursClaimService(db)
    redemptions = []
    for redemption in service.get_redemptions_for_user(user.id):
        reward = service.repo.get_reward_by_id(redemption.rewardid)
        redemptions.append({
            "id": redemption.redemptionid,
            "reward_id": redemption.rewardid,
            "reward_name": reward.name if reward else None,
            "point_cost": redemption.pointsspent,
            "status": redemption.status,
            "created_at": redemption.createdat.isoformat(),
            "staff_note": redemption.staffnote,
        })
    return redemptions


@api_router.get("/redemptions")
async def list_redemptions(user: ApiAdminDep, db: SessionDep, status: str | None = None):
    if not _role_allowed(user, {"staff"}):
        _json_error("Only staff or admins can access redemption queues.", status.HTTP_403_FORBIDDEN)
    service = HoursClaimService(db)
    if status:
        allowed = {"requested", "fulfilled", "cancelled"}
        normalized = status.lower()
        if normalized not in allowed:
            _json_error("status must be requested, fulfilled, or cancelled.", status.HTTP_400_BAD_REQUEST)
        redemptions = [item for item in service.get_all_redemptions() if item.status == normalized]
    else:
        redemptions = list(service.get_all_redemptions())
    payload = []
    for redemption in redemptions:
        reward = service.repo.get_reward_by_id(redemption.rewardid)
        payload.append({
            "id": redemption.redemptionid,
            "user_id": redemption.userid,
            "reward_id": redemption.rewardid,
            "reward_name": reward.name if reward else None,
            "point_cost": redemption.pointsspent,
            "status": redemption.status,
            "created_at": redemption.createdat.isoformat(),
            "staff_note": redemption.staffnote,
        })
    return payload


@api_router.patch("/redemptions/{redemption_id}")
async def patch_redemption(user: ApiAdminDep, db: SessionDep, redemption_id: int, payload: dict | None = Body(default=None)):
    if payload is None:
        payload = {}
    service = HoursClaimService(db)
    redemption = service.repo.get_redemption(redemption_id)
    if redemption is None:
        _json_error("Redemption not found.", status.HTTP_404_NOT_FOUND)
    if redemption.status not in {"requested"}:
        _json_error("This redemption has already been processed.", status.HTTP_409_CONFLICT)

    action = str(payload.get("action", "") or "").strip().lower()
    if action in {"fulfil", "fulfill"}:
        action = "fulfill"
    elif action == "cancel":
        action = "cancel"
    else:
        _json_error("Action must be 'fulfil' or 'cancel'.", status.HTTP_400_BAD_REQUEST)

    try:
        updated = service.process_redemption(redemption_id, user.id, action)
    except ValueError as exc:
        _json_error(str(exc), status.HTTP_400_BAD_REQUEST)
    return {"message": f"Redemption {action}ed.", "redemption": _serialize_redemption(updated)}
