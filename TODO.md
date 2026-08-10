# Task Progress — COMPLETED ✅

## A. Seed the database
- [x] `seed.py` — restructured to seed all login roles + core permissions idempotently (role/permission always syncs; demo data only on fresh DB).
- [x] Ran `python seed.py` → permissions (`admin.access`, `faculty.access`, `student.access`) synced to DB.

## B. Enforce RBAC on faculty_ui.py and auth_ui.py
- [x] `faculty_ui.py` — checks `faculty.access` (Administrator bypass). Already present, now effective.
- [x] `auth_ui.py` — checks `{role}.access` at login for non-Administrators. Already present, now effective.

## C. Admin permissions management UI
- [x] `admin_ui.py` — imported `Permission` (fix NameError in `_permissions_ui`).
- [x] `admin_ui.py` — fixed tab creation: "Permissions" is now a proper tab in the main `st.tabs([...])` list (fixes `ValueError: expected 6, got 5`).
- [x] Interactive permission creation + role assignment implemented in `_permissions_ui`.

## D. Programme master data CRUD (Administrator)
- [x] `models.py` — added `Program` model + `program_id` FK on `Student` + `program_ref` relationship + added to `all_models`.
- [x] `services.py` — added `create_program`, `update_program`, `delete_program` (guarded against enrolled students).
- [x] `admin_ui.py` — added `_program_crud()` with full CRUD UI; added "Programmes" tab under Master data.
- [x] `database.py` — added migration for `students.program_id` column (fixes OperationalError on existing DBs).

## Verification
- [x] All files compile (`py_compile` → ALL_COMPILE_OK).
- [x] All 20 existing tests pass.
- [x] DB initializes cleanly.
