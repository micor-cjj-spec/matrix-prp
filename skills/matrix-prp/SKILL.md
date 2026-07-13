---
name: matrix-prp
description: Matrix PRP project context, positioning, architecture, and technical stack. Use when working on the matrix-prp repository, especially under app/, when designing or implementing the personal resource management platform, its Spring Boot backend, Vue web app, uni-app mobile app, Node CLI, database schema, API contracts, or module features for finance, social, learning, life, work, interests, dashboard, reviews, or knowledge integration.
---

# Matrix PRP

## Project Positioning

Treat Matrix PRP as a multi-end personal resource management platform evolved from a Markdown knowledge base.

The product should serve one person first, with clean extension paths for more users later. It should help answer:

- What is my current state?
- What should I do next?
- Are my long-term trends improving?

The platform shape is:

```text
Web + Mobile App + CLI
        -> Spring Boot REST API
        -> MySQL + knowledge Markdown
```

## Repository Context

Primary local repository:

```text
D:\project\prp\matrix-prp
```

Current intended layout:

```text
app/
  backend/    Spring Boot API service
  web/        Vue 3 web console
  mobile/     uni-app mobile application
  cli/        Node.js command-line tool
  docs/       product, technical, API, and data model docs
knowledge/   existing Markdown knowledge base
```

Keep `knowledge/` as the durable content asset. Put application source, implementation docs, scripts, and engineering configuration under `app/`.

## Technical Stack

Use this as the default stack unless the user explicitly changes direction.

Backend:

- Spring Boot 3
- Java 17 or Java 21
- Spring Web
- Spring Validation
- Spring Security + JWT
- MyBatis Plus
- MySQL
- AutoTable for early schema/table generation
- Docker Compose for local infrastructure
- OpenAPI documentation with Knife4j or springdoc-openapi

Web:

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- Element Plus
- Axios
- ECharts

Mobile:

- uni-app
- Vue 3
- TypeScript

CLI:

- Node.js
- TypeScript
- Commander
- Axios or generated OpenAPI client

Consider later when needed:

- Flyway or Liquibase for long-term database migration discipline
- Redis for cache, sessions, rate limiting, or async task state
- OpenAPI-generated SDK/types shared by web, mobile, and CLI
- AI integration through backend services for classification, summaries, reviews, and knowledge search

## Product Modules

Design around these first-class modules:

- Dashboard: today, this week, alerts, and cross-module status
- Finance: income, expenses, budgets, accounts, bills, and financial reviews
- Social: contacts, relationship map, interaction logs, reminders, and communication reviews
- Learning: courses, credentials, exams, notes, goals, and progress
- Life: habits, health, routines, shopping, home, and daily records
- Work: projects, meetings, tasks, problems, decisions, and career growth
- Interests: music, travel, reading, sports, creative work, and other long-term hobbies
- Knowledge: browser/search/integration layer over `knowledge/`
- Review: weekly, monthly, annual, and module-level retrospectives

Prefer a shared module pattern:

```text
Record -> Plan -> Action -> Review -> Asset
```

Avoid building each module as a totally isolated one-off system when a common record, tag, attachment, task, reminder, or review model will fit.

## Architecture Principles

- Make the backend the source of truth for structured data and authentication.
- Let Web handle deep management, dashboards, and analysis.
- Let Mobile handle fast capture, reminders, and lightweight review.
- Let CLI handle fast developer-style capture, search, automation, and scripted workflows.
- Keep APIs stable and documented from the start.
- Store `user_id` on user-owned tables even if the first release is single-user.
- Start with REST APIs; only add GraphQL or event-driven complexity when a real need appears.
- Keep Markdown knowledge integration incremental: first browse/read, then index/search, then edit/sync, then AI-assisted workflows.

## Development Defaults

When implementing features:

- Inspect the existing repo before choosing structure.
- Prefer clear module boundaries over premature microservices.
- Put backend code under `app/backend`, web code under `app/web`, mobile code under `app/mobile`, CLI code under `app/cli`, and durable design docs under `app/docs`.
- Use MyBatis Plus conventions for CRUD-heavy domain models.
- Use Spring Security + JWT consistently for Web, Mobile, and CLI auth.
- Use Docker Compose for local MySQL and future infrastructure.
- Add API docs and validation annotations with new backend endpoints.
- Add table/page patterns that can repeat across modules rather than bespoke screens for every domain.

## MVP Direction

Prioritize a thin but coherent first version:

- Backend: auth, users, modules, records, tags, tasks, reviews, and knowledge index APIs
- Web: login, dashboard, navigation, finance records, task list, and knowledge browser
- Mobile: quick capture, quick finance entry, today view, and reminders
- CLI: login/token config, add record, add finance entry, search, and review commands

Do not attempt to fully build all modules at once. Create the shared foundation first, then expand module depth.
