from fastapi import APIRouter, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import status
from app.dependencies.session import SessionDep
from app.dependencies.auth import AdminDep, IsUserLoggedIn, get_current_user, is_admin
from app.models.hours import Reward
from app.models.user import User
from app.services.hours_service import HoursClaimService
from app.utilities.flash import flash
from . import router, templates


@router.get("/admin", response_class=HTMLResponse)
async def admin_home_view(
    request: Request,
    user: AdminDep,
    db:SessionDep
):
    service = HoursClaimService(db)
    pending_claims = service.get_pending_claims()
    approved_claims = service.get_claims_by_status("approved")
    rejected_claims = service.get_claims_by_status("rejected")

    queue = []
    for claim in pending_claims:
        queue.append({
            "claim": claim,
            "student": db.get(User, claim.userid),
        })

    approved = []
    for claim in approved_claims:
        approved.append({
            "claim": claim,
            "student": db.get(User, claim.userid),
        })

    rejected = []
    for claim in rejected_claims:
        rejected.append({
            "claim": claim,
            "student": db.get(User, claim.userid),
        })

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "queue": queue,
            "approved": approved,
            "rejected": rejected,
        }
    )


@router.get("/admin/claims/{claim_id}", response_class=HTMLResponse)
async def admin_claim_detail_view(
    request: Request,
    user: AdminDep,
    db: SessionDep,
    claim_id: int,
):
    service = HoursClaimService(db)
    claim = service.repo.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found.")
    return templates.TemplateResponse(
        request=request,
        name="admin_claim_detail.html",
        context={
            "user": user,
            "claim": claim,
            "student": db.get(User, claim.userid),
        },
    )


@router.post("/admin/claims/{claim_id}/review")
async def admin_review_claim(
    request: Request,
    user: AdminDep,
    db: SessionDep,
    claim_id: int,
    decision: str = Form(...),
    reject_reason: str | None = Form(default=None),
    adjusted_hours: float | None = Form(default=None),
):
    service = HoursClaimService(db)
    if decision is None:
        raise HTTPException(status_code=400, detail="Decision is required.")
    service.review_claim(
        claim_id=claim_id,
        reviewer_id=user.id,
        decision=decision,
        reject_reason=reject_reason,
        adjusted_hours=adjusted_hours,
    )
    flash(request, "Claim recorded.", "success")
    return RedirectResponse(url=request.url_for("admin_home_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/redemptions", response_class=HTMLResponse)
async def admin_redemptions_view(request: Request, user: AdminDep, db: SessionDep):
    service = HoursClaimService(db)
    redemptions = []
    for redemption in service.get_all_redemptions():
        reward = db.get(Reward, redemption.rewardid)
        redemptions.append({"redemption": redemption, "reward": reward})
    return templates.TemplateResponse(
        request=request,
        name="admin_redemptions.html",
        context={"user": user, "title": "Redemptions", "redemptions": redemptions},
    )


@router.post("/admin/redemptions/{redemption_id}/fulfill")
async def fulfill_redemption(request: Request, user: AdminDep, db: SessionDep, redemption_id: int):
    service = HoursClaimService(db)
    service.process_redemption(redemption_id, user.id, "fulfill")
    flash(request, "Redemption fulfilled.", "success")
    return RedirectResponse(url=request.url_for("admin_redemptions_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/redemptions/{redemption_id}/cancel")
async def cancel_redemption(request: Request, user: AdminDep, db: SessionDep, redemption_id: int):
    service = HoursClaimService(db)
    service.process_redemption(redemption_id, user.id, "cancel")
    flash(request, "Redemption cancelled and points refunded.", "success")
    return RedirectResponse(url=request.url_for("admin_redemptions_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/leaderboard", response_class=HTMLResponse)
async def admin_leaderboard_view(request: Request, user: AdminDep, db: SessionDep):
    service = HoursClaimService(db)
    leaderboard = service.get_leaderboard()
    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={"user": user, "leaderboard": leaderboard, "title": "Leaderboard"},
    )
