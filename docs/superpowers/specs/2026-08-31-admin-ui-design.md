# Admin UI & Admin Endpoints — Design Spec

**Status:** Approved (brainstormed 2026-08-31, section-by-section sign-off in conversation)

## Context

The platform has a global `SystemAdmin` role (`users.is_admin`, enforced via `require_admin` in `backend/auth.py`), but no UI to exercise it. Admins today must run raw SQL to promote users, and there is no way at all to list all users, edit users, reset passwords, list all projects, delete a project, deactivate a project, or manage a project's members beyond adding one via the Consultant-only endpoint. This spec adds a dedicated `/admin` UI plus the admin-scoped backend endpoints to support it.

Current state (2026-08-31): Phases 0/A/B/C, Backend API Integration, and Frontend GUI Overhaul are all landed on `main`. `users_db.py` has `create_user`/`get_user_by_email`/`get_user_by_id`; `projects_db.py` has `create_project`/`list_projects_for_user`/`get_project_by_id`/`update_project`/`activate_project`/`get_project_member`/`add_project_member`. `auth.py` has `get_current_user`/`require_admin`/`require_project_role`/`require_active_project` and `hash_password`. The frontend is Next.js (App Router), hand-written CSS, no component library, JWT in `localStorage` (`lib/api-client.ts`).

## Decisions

1. **A dedicated `/admin` page** (Approach A), not changes sprinkled into the consultant pages. One place for the global SystemAdmin to manage users and projects. Rejected: extending consultant pages (muddies them, user management has no natural home) and backend-only (fails the stated need for an admin UI).
2. **All new management endpoints are `require_admin`-gated**, except the project-member endpoints, which are open to an admin *or* that project's Consultant (Consultants already add members today; this extends the same capability to list/change/remove). No new auth mechanisms.
3. **Admin sets a new password directly** (no email, no temporary-password relay, no self-service reset). Reuses `hash_password` from `auth.py`. Self-service/email password reset stays explicitly out of scope (unchanged from prior specs).
4. **`POST /api/admin/users` accepts an optional `is_admin`**, so the SystemAdmin can promote at creation time instead of editing afterwards (or running SQL).
5. **Self-lockout guard**: an admin cannot demote or deactivate their own account — `400`. Prevents the last admin from accidentally locking themselves out. (No "last admin" invariant is enforced beyond this — a multi-admin deployment can still reduce itself to zero admins via other admins; acceptable for a POC.)
6. **Project deletion is a hard delete** and cascades via existing `ON DELETE CASCADE` FKs (`project_members`, `project_artifacts`, `project_kb_chunks`, `responses`, `chat_sessions`). Destructive — confirmed in the UI before firing. No soft-delete/archive state is introduced.
7. **"Deactivate" a project = set status back to `Draft`** (reversible; the existing `activate_project` already does `Draft → Active`, and the client UI already treats any non-`Active` status as "not activated"). No new `Archived`/`Completed` lifecycle states are added.
8. **No new npm dependencies** and no component library. The admin page reuses the existing CSS classes (`.glass-card`, `.screen-intro`, tables, `.btn`, `.status-pill`, etc.) and the existing `authFetch` client.
9. **The `/admin` page gates on `getMe().is_admin`** and redirects to `/` when the caller is not an admin — client-side only, matching the rest of the frontend (the backend is the real enforcement layer).

## Backend — data access

**`backend/users_db.py`** (extend):
- `list_users() -> list` — all users ordered by `created_at`; each dict: `id, email, full_name, is_active, is_admin, created_at`.
- `update_user(user_id, full_name=None, is_admin=None, is_active=None) -> dict | None` — `COALESCE` per column, `RETURNING` the row (mirrors `projects_db.update_project`); `None` if no row matched.
- `set_password(user_id, password_hash) -> bool` — updates `password_hash`; returns whether a row was updated.

**`backend/projects_db.py`** (extend):
- `list_all_projects() -> list` — every project ordered by `created_at DESC`, same shape as `list_projects_for_user`.
- `set_project_status(project_id, status) -> dict | None` — direct `UPDATE ... SET status = %s WHERE id = %s`; caller passes a validated `Draft`/`Active`.
- `delete_project(project_id) -> bool` — `DELETE FROM projects WHERE id = %s`; relies on FK cascades.
- `list_project_members(project_id) -> list` — `project_members JOIN users`, each dict: `id, project_id, user_id, role, org_title, assigned_at, email, full_name`.
- `update_project_member_role(project_id, user_id, role) -> dict | None` — sets role; `None` if no such member.
- `remove_project_member(project_id, user_id) -> bool`.

## Backend — endpoints (in `backend/main.py`)

| Endpoint | Auth | Body / notes |
|---|---|---|
| `GET /api/admin/users` | `require_admin` | — |
| `POST /api/admin/users` | `require_admin` | `{email, password, full_name, is_admin?}` |
| `PATCH /api/admin/users/{user_id}` | `require_admin` | `{full_name?, is_admin?, is_active?}` |
| `POST /api/admin/users/{user_id}/reset-password` | `require_admin` | `{password}` |
| `GET /api/admin/projects` | `require_admin` | — |
| `PATCH /api/admin/projects/{project_id}` | `require_admin` | `{name?, customer_name?, description?, industry_context?}` |
| `PATCH /api/admin/projects/{project_id}/status` | `require_admin` | `{status}` in `{"Draft","Active"}` |
| `DELETE /api/admin/projects/{project_id}` | `require_admin` | — |
| `GET /api/projects/{project_id}/members` | admin or that project's Consultant | — |
| `PATCH /api/projects/{project_id}/members/{user_id}` | admin or that project's Consultant | `{role}` in `{"Consultant","ClientUser"}` |
| `DELETE /api/projects/{project_id}/members/{user_id}` | admin or that project's Consultant | — |

Rules:
- The self-lockout guard is applied in `PATCH /api/admin/users/{user_id}`: if `user_id == current_user["id"]` and the payload sets `is_admin=false` or `is_active=false`, return `400`.
- `POST /api/admin/users` returns `400` on a duplicate email (reuses `users_db.create_user`'s `ValueError` path) and `400` on a non-string/invalid password.
- New user hashing and password reset both go through `auth.hash_password`.
- Endpoints return `404` for unknown `user_id`/`project_id`/member, `400` for invalid `role`/`status`/self-lockout, `403` for insufficient role.

## Frontend

- **New page** `frontend-react/app/admin/page.tsx` ("use client"): on mount calls `getMe()`; if `!user.is_admin`, `router.replace("/")`. Two tabs — **Users** and **Projects** (local state toggle; no router sub-routes).
- **Sidebar** (`components/Sidebar.tsx`): add an "Admin" nav link, rendered only when `user.is_admin`. (The existing `getMe()` result already carries `is_admin`.)
- **Users tab**: a "New user" form (full name, email, password, "admin" checkbox) and a list of all users. Each row shows name, email, admin badge, active/inactive, with actions: toggle admin, activate/deactivate, reset password (inline prompt → `POST .../reset-password`).
- **Projects tab**: a list of all projects. Each row shows name, customer, status, with actions: edit (name/customer/description/industry_context), activate/deactivate (`PATCH .../status`), delete (confirm → `DELETE`), and "Members" (opens a panel: list members, add by email + role, change role, remove).
- **`lib/api-client.ts`**: add typed functions for every endpoint above (mirroring the existing `ProjectArtifact`/`Project` style), plus `User`/`AdminUserRow`/`ProjectMemberDetail` types as needed.
- No new CSS files; extend `app/globals.css` only if a select/table style is missing (reuse existing tokens).

## Edge cases

- Admin demotes/deactivates self → `400` "You cannot modify your own admin/active status."
- Duplicate email on admin user creation → `400` (reuses `create_user`).
- Delete project with existing data → cascades; UI confirms first.
- Non-admin hitting `/admin` → redirected to `/`; non-admin hitting admin endpoints → `403` (backend enforcement).

## Scope boundaries (explicitly out of scope)

- Self-service / email password reset, SSO, password reset tokens — unchanged from prior specs.
- Soft-delete, archive, and `Completed` project lifecycle states.
- Framework Authoring Mode (authoring questions/processes in the UI) — still on the roadmap, not part of this admin work.
- Guided Learning Flow.
- Any change to `/api/evaluate`, `CASES_DATA`, or the chat session legacy path (all already retired or deliberately untouched per prior phases).

## Testing

pytest coverage (following existing patterns in `tests/`, using the same mocking conventions as `test_project_endpoints.py`/`test_users_db.py`):
- `users_db.list_users` / `update_user` / `set_password`.
- `projects_db.list_all_projects` / `set_project_status` / `delete_project` / `list_project_members` / `update_project_member_role` / `remove_project_member`.
- Endpoint tests: admin gating (`403` for non-admin), self-lockout `400`, duplicate email `400`, reset-password success, project delete cascade behavior, member add/change/remove, invalid role/status `400`, unknown id `404`.

Frontend verification is manual (dev server + browser), per the project's existing convention (no frontend test tooling).
