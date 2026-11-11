# ADR-0001: One FastAPI app with clear modules, PostgreSQL, Docker Compose

- Status: Proposed (needs Architect + Product Owner sign-off)
- Date: 2026-11-06
- Work items: A-101, INFRA-001, CORE-001, NUT-001

## Context
Phase 1 needs a small, testable vertical slice for a personal pilot. The handbook warns against
over-engineering before validation and asks for a modular monolith with explicit domain boundaries
and versioned APIs.

## Options
1. Microservices (one service per domain): high setup and operations cost for one developer.
2. **Modular monolith (chosen):** one FastAPI process, one PostgreSQL database, folders per domain
   (`users`, `targets`, `foods`, `meals`, `audit`), all routes under `/v1`.
3. Serverless functions: harder to run locally, and the plan calls for a local Docker pilot.

## Decision
Option 2. Business rules live in plain service functions (`meals/service.py`, `meals/nutrition.py`),
not in route handlers or AI prompts. Nutrition math is deterministic `Decimal` math.
Meals use a draft → confirm flow so nothing reaches a user's log without their OK.
Audit events are written in the same transaction as the change, and the database blocks edits to them.

## Consequences
- Simple to run (`docker compose up`) and test against real PostgreSQL.
- One process means the in-memory login limiter only works with a single API container.
  Move it to Redis/DB before scaling out.
- Modules may only call each other through service functions, so one can be split out later if needed.

## Rollback / migration path
Each module owns its tables and routes, so a module can move to its own service by moving its folder,
pointing it at its own schema, and keeping the `/v1` contract unchanged.
