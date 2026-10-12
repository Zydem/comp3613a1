from fastapi import APIRouter, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import status
from app.dependencies.session import SessionDep
from app.dependencies.auth import AuthDep, IsUserLoggedIn, get_current_user, is_admin
from app.models.hours import Reward
from app.services.hours_service import HoursClaimService
from app.utilities.flash import flash
from . import router, templates


@router.get("/app", response_class=HTMLResponse)
async def user_home_view(
    request: Request,
    user: AuthDep,
    db:SessionDep
):
    service = HoursClaimService(db)
    service.ensure_default_milestones()
    service.sync_user_milestones(user)
    current = service.get_current_milestone_for_hours(float(user.lifetimehours or 0.0))
    next_milestone = service.get_next_milestone_for_hours(float(user.lifetimehours or 0.0))

    milestones = []
    for milestone in service.get_all_milestones():
        record = service.repo.get_student_milestone(user.id, milestone.milestoneid)
        milestones.append({
            "name": milestone.name,
            "hoursrequired": milestone.hoursrequired,
            "unlocked": record is not None,
            "unlock_label": f"Unlocked {record.unlockedat.strftime('%d %b')}" if record else "Locked",
            "unlocked_at": record.unlockedat if record else None,
        })

    recent_activity = []
    for claim in service.get_claims_for_user(user.id):
        if claim.status in {"approved", "rejected"}:
            recent_activity.append({
                "title": f"{claim.status.title()}: {claim.activity}",
                "detail": f"{claim.hours}h",
                "date": claim.date,
            })

    for milestone in service.get_all_milestones():
        record = service.repo.get_student_milestone(user.id, milestone.milestoneid)
        if record:
            recent_activity.append({
                "title": f"{milestone.name} unlocked",
                "detail": "Milestone achieved",
                "date": record.unlockedat.date(),
            })

    recent_activity = sorted(recent_activity, key=lambda item: item["date"], reverse=True)[:5]

    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context={
            "user": user,
            "lifetime_hours": float(user.lifetimehours or 0.0),
            "points_balance": int(user.pointsbalance or 0),
            "current_milestone": current,
            "next_milestone": next_milestone,
            "milestones": milestones,
            "recent_activity": recent_activity,
        }
    )


@router.get("/app/claims", response_class=HTMLResponse)
async def user_claims_view(request: Request, user: AuthDep, db: SessionDep):
    service = HoursClaimService(db)
    claims = service.get_claims_for_user(user.id)
    return templates.TemplateResponse(
        request=request,
        name="my_claims.html",
        context={"user": user, "claims": claims},
    )


@router.get("/app/leaderboard", response_class=HTMLResponse)
async def student_leaderboard_view(request: Request, user: AuthDep, db: SessionDep):
    service = HoursClaimService(db)
    leaderboard = service.get_leaderboard()
    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={"user": user, "leaderboard": leaderboard, "title": "Leaderboard"},
    )


@router.get("/app/rewards", response_class=HTMLResponse)
async def student_rewards_view(request: Request, user: AuthDep, db: SessionDep):
    service = HoursClaimService(db)
    catalog = service.get_reward_catalog(user)
    return templates.TemplateResponse(
        request=request,
        name="rewards.html",
        context={"user": user, "title": "Rewards", "catalog": catalog},
    )


@router.get("/app/rewards/confirm/{reward_id}", response_class=HTMLResponse)
async def student_reward_confirm_view(request: Request, user: AuthDep, db: SessionDep, reward_id: int):
    service = HoursClaimService(db)
    reward = db.get(Reward, reward_id)
    if reward is None:
        flash(request, "Reward not found.", "error")
        return RedirectResponse(url=request.url_for("student_rewards_view"), status_code=status.HTTP_303_SEE_OTHER)

    eligibility = service.get_reward_catalog(user)
    catalog_entry = next((item for item in eligibility if item["reward"].rewardid == reward_id), None)
    if catalog_entry is None:
        catalog_entry = {
            "reward": reward,
            "eligible": False,
            "reasons": ["Reward is unavailable."],
        }

    checks = [
        {
            "label": "Enough points",
            "ok": user.pointsbalance >= reward.pointscost,
        },
        {
            "label": "In stock",
            "ok": reward.stock > 0,
        },
        {
            "label": "Milestone met",
            "ok": reward.requiredmilestoneid is None or service.has_unlocked_milestone(user, reward.requiredmilestoneid),
        },
    ]
    balance_now = int(user.pointsbalance or 0)

    return templates.TemplateResponse(
        request=request,
        name="redeem_confirmation.html",
        context={
            "user": user,
            "reward": reward,
            "title": "Confirm redeem",
            "eligibility_checks": checks,
            "is_eligible": all(item["ok"] for item in checks),
            "balance_now": balance_now,
            "cost": reward.pointscost,
            "balance_after": balance_now - reward.pointscost,
            "catalog_entry": catalog_entry,
        },
    )


@router.post("/app/rewards/redeem/{reward_id}")
async def student_redeem_reward(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    reward_id: int,
    staff_note: str = Form(default=""),
):
    service = HoursClaimService(db)
    try:
        service.redeem_reward(user.id, reward_id, staff_note=staff_note)
        flash(request, "Reward requested successfully. It is now pending staff review.", "success")
    except ValueError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(url=request.url_for("student_rewards_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/app/rewards/confirm/{reward_id}")
async def student_confirm_redeem_reward(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    reward_id: int,
    confirm_redeem: str = Form(default=""),
    staff_note: str = Form(default=""),
):
    if confirm_redeem != "1":
        flash(request, "Redemption was not confirmed.", "error")
        return RedirectResponse(url=request.url_for("student_rewards_view"), status_code=status.HTTP_303_SEE_OTHER)

    service = HoursClaimService(db)
    try:
        service.redeem_reward(user.id, reward_id, staff_note=staff_note)
        flash(request, "Reward requested successfully. It is now pending staff review.", "success")
    except ValueError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(url=request.url_for("student_rewards_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/app/redemptions", response_class=HTMLResponse)
async def student_redemptions_view(request: Request, user: AuthDep, db: SessionDep):
    service = HoursClaimService(db)
    redemptions = []
    for redemption in service.get_redemptions_for_user(user.id):
        reward = db.get(Reward, redemption.rewardid)
        redemptions.append({"redemption": redemption, "reward": reward})
    return templates.TemplateResponse(
        request=request,
        name="redemptions.html",
        context={"user": user, "title": "My Redemptions", "redemptions": redemptions},
    )