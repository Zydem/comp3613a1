# Test plan

## User Acceptance Test Plan

| ID | Wireframe | Role | Steps | Success criteria | Result | Notes |
|---|---|---|---|---|---|---|
| UAT-01 | W1-1 | Student (milo) | Log Hours: Beach clean-up, today, 6 hours, description, proof "Supervisor: Ms Lee", Submit | Success message; claim shows Pending in My Claims | | |
| UAT-02 | W1-1 | Student (milo) | Submit with hours 0, then 30, then empty | Each blocked with an error; no claim created | | |
| UAT-03 | W1-2 | Student (milo) | Open My Claims | Claims listed with date, activity, hours, status, feedback | | |
| UAT-04 | W1-3 | Staff (admin) | Open Review Claims, switch Pending/Approved/Rejected tabs | Pending shows milo's claim with Review; tabs filter correctly | | |
| UAT-05 | W1-4 | Staff (admin) | Open milo's claim, check description and proof, approve 6 hours | Claim moves to Approved with 6 hours | | |
| UAT-06 | W1-4 | Staff (admin) | Reject a pending claim with no reason, then with "No proof provided" | No reason is blocked; with reason it moves to Rejected | | |
| UAT-07 | W1-2 | Student (milo) | Refresh My Claims | Approved shows 6 hours; rejected shows reason; only approved hours count | | |
| UAT-08 | W2-1, W2-2 | Student (milo) | Open Dashboard after approval | 54 hours, 540 points, Gold unlocked with today's date | | |
| UAT-09 | W2-3 | Student (milo) | Open Leaderboard | Sorted by hours; milo highlighted; admin not listed | | |
| UAT-10 | W3-1 | Student (nina) | Open Rewards | Gold Access Pass locked (Gold required); out-of-stock items labelled | | |
| UAT-11 | W3-2 | Student (milo) | Redeem Gold Access Pass, review confirmation, Confirm | Shows eligibility and 540-260=280; after confirm points 280, stock -1, Requested; hours and rank unchanged | | |
| UAT-12 | W3-2 | Student (milo) | Click Redeem then Cancel on the confirmation | Nothing redeemed; points and stock unchanged | | |
| UAT-13 | W3-3 | Student (milo) | Open My Redemptions | Redemption listed as Requested with date and points | | |
| UAT-14 | W3-4 | Staff (admin) | Mark Gold pass Fulfilled; cancel another requested redemption | Fulfilled moves to Fulfilled; cancelled restores points and stock | | |
| UAT-15 | All | Student (milo) | Type the staff Review Claims URL in the address bar | Access denied; students can't use staff pages | | |

## Unit tests (UT)

| ID | What is tested | Steps / input | Expected result |
|---|---|---|---|
| UT01 | approve claim adds hours and unlocks milestone | create a student, pending claim with 5 hours, approve it | user lifetime hours become 5, points 50, Bronze milestone unlocked |
| UT02 | seeded student totals stay consistent and approved claims add points | seed students with lifetime hours and points, approve a new claim for priya | priya lifetime hours and points increase, totals match the expected formula |
| UT03 | reject claim keeps totals unchanged and stores reason | create a pending claim, reject it with reason "Missing proof" | claim is rejected, rejection reason is stored, user totals remain unchanged |
| UT04 | default milestones include Bronze/Silver/Gold | call ensure_default_milestones() | Bronze, Silver, and Gold are created with increasing thresholds |
| UT05 | reward redemption deducts points and reduces stock | create a student with enough points and redeem a valid reward | points fall by the reward cost and stock decreases by one |
| UT06 | zero stock blocks redemption | set reward stock to 0 and try to redeem it | ValueError is raised with an out-of-stock message |
| UT07 | cancelled redemption restores points and stock | redeem a reward, then cancel it | student points are restored and stock returns to the original value |
| UT08 | invalid hours are rejected and no claim is saved | call submit_claim() with 0 or 25 hours | ValueError is raised and no HoursClaim rows are created |
| UT09 | reject without a reason fails | try to reject a claim with no reason | ValueError is raised and claim remains pending |
| UT10 | gold reward is locked for non-gold students | inspect catalog or redeem a Gold Access Pass without the Gold milestone | reward is ineligible and the reason says Gold is required |
| UT11 | processed claims cannot be approved twice | approve an already-approved claim again | ValueError is raised and totals are not doubled |
| UT12 | fulfilling a redemption leaves points and stock unchanged | redeem a reward and fulfill it | points and stock stay at their current values after fulfillment |

## Integration tests (IT)

| ID | What is tested | Steps / input | Expected result |
|---|---|---|---|
| IT01 | login, claim submission, progress, leaderboard, and reward catalog | login as a student, submit a claim, fetch progress, leaderboard, and rewards | all API calls return success and expected JSON data |
| IT02 | missing token, invalid hours, and 401/403 auth checks | hit /api/claims without auth; sign in as student and submit invalid hours; then call admin-only claim queue | unauthenticated requests return 401; invalid payloads return 400; wrong-role requests return 403 |
| IT03 | admin claim review and approval flow | login as admin, fetch claim queue, approve a pending claim | claim is returned from the queue and is approved with updated lifetime hours |
| IT04 | leaderboard and rewards catalog are returned by the API | call /api/leaderboard and /api/rewards as a student | ranked data and reward entries are returned in JSON |
| IT05 | redemption request and staff processing flow | student requests a reward, then admin fulfills it | redemption is created, visible to the student, and fulfilled by staff |
| IT06 | protected /api routes reject unauthorized or wrong-role access | access /api/users without a token and with a student token | no-token requests fail with 401; student access is blocked with 403 |
