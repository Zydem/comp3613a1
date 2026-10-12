from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies.auth import AdminDep, AuthDep
from app.dependencies.session import SessionDep
from app.repositories.hours import HoursRepository
from app.services.hours_service import HoursClaimService
from app.utilities.flash import flash
from . import router, templates


@router.get("/hours")
async def hours_dashboard(request: Request, user: AuthDep, db: SessionDep):
    service = HoursClaimService(db)
    claims = service.get_claims_for_user(user.id)
    queue = []
    if user.role in {"admin", "staff"}:
        queue = service.get_pending_claims()

    return templates.TemplateResponse(
        request=request,
        name="hours.html",
        context={
            "user": user,
            "claims": claims,
            "queue": queue,
        },
    )


@router.post("/hours/submit")
async def submit_hours_claim(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    activity: str = Form(...),
    claim_date: str = Form(...),
    hours: float = Form(...),
    description: str = Form(...),
    proof: str | None = Form(default=None),
    proof_image: UploadFile | None = File(default=None),
):
    proof_value = proof.strip() if proof and proof.strip() else None

    if proof_image is not None and proof_image.filename:
        allowed_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        file_extension = Path(proof_image.filename).suffix.lower()
        if file_extension not in allowed_extensions:
            raise ValueError("Proof image must be one of: png, jpg, jpeg, gif, webp.")

        upload_dir = Path("app/static/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}{file_extension}"
        with (upload_dir / stored_name).open("wb") as image_file:
            image_file.write(await proof_image.read())
        proof_value = f"/static/uploads/{stored_name}"

    service = HoursClaimService(db)
    service.submit_claim(
        user_id=user.id,
        activity=activity,
        claim_date=date.fromisoformat(claim_date),
        hours=hours,
        description=description,
        proof=proof_value,
    )
    flash(request, "Volunteer claim submitted successfully. It is now pending review.", "success")
    return RedirectResponse(url=request.url_for("user_home_view"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/hours/review/{claim_id}")
async def review_hours_claim(
    request: Request,
    reviewer: AdminDep,
    db: SessionDep,
    claim_id: int,
    decision: str = Form(...),
    reject_reason: str | None = Form(default=None),
):
    service = HoursClaimService(db)
    service.review_claim(
        claim_id=claim_id,
        reviewer_id=reviewer.id,
        decision=decision,
        reject_reason=reject_reason,
    )
    return RedirectResponse(url=request.url_for("admin_home_view"), status_code=status.HTTP_303_SEE_OTHER)
