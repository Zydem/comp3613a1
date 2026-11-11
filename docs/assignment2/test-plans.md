# Assignment 2 Test Plans

## 1. Unit Test Plan

### Scope
Validate the service-layer logic in isolation for the three workflows implemented in the Student Awards app:
- claim submission and validation
- staff approval and rejection decisions
- milestone unlock and points updates
- reward eligibility and redemption logic

### Test cases
| Area | Test | Expected result |
|---|---|---|
| Claim validation | submit claim with zero or invalid hours | validation error and no claim persisted |
| Claim validation | reject with no reason | `400` validation failure |
| Approval logic | approved claim adds hours and points | lifetime hours and points increase |
| Rejection logic | rejected claim keeps totals unchanged | claim marked `rejected` and reason stored |
| Milestone logic | crossing Bronze/Silver/Gold threshold | `StudentMilestone` row created |
| Reward logic | not enough points or stock zero | redemption blocked with clear error |
| Reward logic | valid reward redemption | points deducted and redemption saved |

### Execution
```bash
python -m pytest tests/test_hours_flow.py -q
```

## 2. Integration Test Plan

### Scope
Exercise the FastAPI app end-to-end using `TestClient` to verify route protection, validation, and workflow completion.

### Key scenarios
1. Student logs in through `/api/auth/login` and receives a token.
2. Student submits a valid claim through `/api/claims`.
3. Student reads their claims and progress via `/api/claims/me` and `/api/me/progress`.
4. Staff reads the claim queue with `/api/claims` and reviews a pending claim.
5. Student views reward catalog and attempts redemption with proper validations.
6. Admin reviews redemptions through `/api/redemptions` and processes them.

### Coverage goals
- auth enforced for all protected routes
- role-based authorization enforced (
  student vs admin/staff)
- JSON status codes and messages are returned consistently
- business rules match the web application logic

## 3. User Acceptance Test Plan

### Objective
Confirm the app supports the three core workflows for a real user:
- log volunteer hours
- monitor progress and leaderboard
- redeem rewards

### UAT tasks
| Workflow | User task | Success criteria |
|---|---|---|
| Hours | Student submits a volunteer claim | entry appears in their claim history as pending |
| Hours | Staff approves or rejects claim | status updates correctly and totals reflect the decision |
| Progress | Student checks milestone and leaderboard | rank and milestone values match the expected totals |
| Rewards | Student checks eligibility | eligible and locked reasons are clear |
| Rewards | Staff processes redemption | points and stock are adjusted accordingly |

### Exit criteria
A user acceptance test passes when all actions above can be completed without broken redirects, inconsistent totals, or duplicated rewards.

## 4. Test Implementation Summary

The repository contains the pytest-based validation suite in `tests/test_hours_flow.py`, which covers the service/business logic and route-level flow across the app.
The API collection in `docs/assignment2/postman/StudentAwards_API_Assignment2.postman_collection.json` provides end-to-end verification of the JSON endpoints.
