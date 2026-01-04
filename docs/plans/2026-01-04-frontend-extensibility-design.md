# Frontend Extensibility Architecture - Design Document

**Date:** 2026-01-04
**Status:** Validated
**Source:** `docs/prompts/frontend/extensible_architecture.md`

---

## Summary

This document captures the validated architectural improvements for the Dataing frontend. All recommendations were verified against the actual codebase.

---

## Validated Problems

| Issue | Location | Evidence |
|-------|----------|----------|
| Manual API types | `lib/api/types.ts` | 59 lines of manually synced types |
| Hardcoded form fields | `datasources/datasource-form.tsx` | Only host/port/db/user/pass fields |
| Duplicated loading/error | `investigation/InvestigationList.tsx:26-47` | Same pattern in multiple files |
| No error boundaries | `App.tsx` | No crash recovery |
| Scattered query keys | `datasources.ts` | `datasource-schema`, `table-search` inline |
| Large mixed components | `NewInvestigation.tsx` | 703 lines, 3 inline sub-components |

---

## Implementation Plan

### Phase 0: Unblock Orval (15 min)

**Goal:** Export OpenAPI spec from backend so Orval can generate types.

**Tasks:**
1. Create `backend/scripts/export_openapi.py`:
   ```python
   import json
   from dataing.entrypoints.api.app import app

   with open("openapi.json", "w") as f:
       json.dump(app.openapi(), f, indent=2)
   ```
2. Update `justfile` `generate-client` recipe to run export first
3. Verify `pnpm orval` works

---

### Phase 1: Generate API Types (30 min)

**Goal:** Replace manual types with Orval-generated types and hooks.

**Tasks:**
1. Run `just generate-client`
2. Update imports in `investigations.ts` and `datasources.ts`
3. Delete `lib/api/types.ts`
4. Add generation to CI

**Files changed:**
- `frontend/src/lib/api/investigations.ts`
- `frontend/src/lib/api/datasources.ts`
- `frontend/src/lib/api/types.ts` (deleted)
- New: `frontend/src/lib/api/generated/`

---

### Phase 2: Error Boundaries (30 min)

**Goal:** Prevent component crashes from breaking the whole app.

**Tasks:**
1. Create `components/error-boundary.tsx`
2. Wrap routes in `App.tsx` with error boundaries
3. Add feature-level boundaries for investigations, datasources

**Files changed:**
- New: `frontend/src/components/error-boundary.tsx`
- `frontend/src/App.tsx`

---

### Phase 3: AsyncBoundary Component (45 min)

**Goal:** Eliminate duplicated loading/error handling.

**Tasks:**
1. Create `components/async-boundary.tsx`
2. Create `components/shared/default-error-state.tsx`
3. Refactor `InvestigationList.tsx` to use AsyncBoundary
4. Refactor other pages as needed

**Files changed:**
- New: `frontend/src/components/async-boundary.tsx`
- `frontend/src/features/investigation/InvestigationList.tsx`

---

### Phase 4: Query Key Factory (30 min)

**Goal:** Centralize query keys for better cache management.

**Tasks:**
1. Create `lib/api/query-keys.ts` with factory pattern
2. Update `investigations.ts` to use factory
3. Update `datasources.ts` to use factory

**Files changed:**
- New: `frontend/src/lib/api/query-keys.ts`
- `frontend/src/lib/api/investigations.ts`
- `frontend/src/lib/api/datasources.ts`

---

### Phase 5: Dynamic Forms (2-3 hrs)

**Goal:** Schema-driven forms for different data source types.

**Tasks:**
1. Create `components/forms/dynamic-form.tsx`
2. Create `components/forms/dynamic-field.tsx`
3. Add backend endpoint for source type schemas (or define in frontend initially)
4. Refactor `DataSourceForm` to use dynamic form
5. Test with PostgreSQL, then add S3/MongoDB schemas

**Files changed:**
- New: `frontend/src/components/forms/dynamic-form.tsx`
- New: `frontend/src/components/forms/dynamic-field.tsx`
- `frontend/src/features/datasources/datasource-form.tsx`

---

### Phase 6: Extract Hooks (1-2 hrs)

**Goal:** Separate business logic from UI in NewInvestigation.

**Tasks:**
1. Extract `SchemaViewer` to `features/investigation/components/schema-viewer.tsx`
2. Extract `LineagePanel` to `features/investigation/components/lineage-panel.tsx`
3. Extract `DatasetEntry` to `features/investigation/components/dataset-entry.tsx`
4. Create `hooks/use-investigation-form.ts`
5. Simplify `NewInvestigation.tsx`

**Files changed:**
- New: `frontend/src/features/investigation/components/` (3 files)
- New: `frontend/src/features/investigation/hooks/use-investigation-form.ts`
- `frontend/src/features/investigation/NewInvestigation.tsx`

---

### Phase 7: Feature Flags (Deferred)

Not needed until enterprise customers require incremental feature rollout.

---

## Success Criteria

- [ ] `pnpm orval` generates types without errors
- [ ] No manual type definitions in `lib/api/`
- [ ] Component crashes don't break the app
- [ ] Loading/error handling uses AsyncBoundary
- [ ] Query keys defined in single file
- [ ] DataSourceForm works for PostgreSQL, S3, MongoDB
- [ ] NewInvestigation.tsx < 200 lines

---

## Notes

- All changes are frontend-only except Phase 0 (OpenAPI export script)
- No backwards compatibility concerns (pre-launch)
- Dynamic forms pattern will be reused for lineage providers, LLM settings, notifications
