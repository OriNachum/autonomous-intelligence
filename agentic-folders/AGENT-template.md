# Agent Guide for [Folder Name]

## Context
<!-- Describe what this folder contains, its purpose in the monorepo, and the main domain logic it encapsulates. -->
<!-- Is it a Microservice? A Shared Library? A UI App? -->

## Structure & Navigation
<!-- Explain the folder structure. How to read the code? Where are the entry points? -->
<!-- Common patterns: -->
<!-- - `src/app/` - Main application logic -->
<!-- - `*.module.ts` - NestJS Modules -->
<!-- - `*.controller.ts` - API Controllers -->
<!-- - `*.service.ts` - Business Logic -->
<!-- - `*.entity.ts` / `*.schema.ts` - Database Models -->
<!-- - `dto/` - Data Transfer Objects -->

## Development Workflow
<!-- How to add new code? What patterns should be followed? -->
### Adding New Features
1. Create a new `Module` if the feature is distinct, or add to an existing one.
2. Define DTOs for input/output validation.
3. Implement `Service` methods for business logic.
4. Expose via `Controller` or `Resolver` (GraphQL).

### Testing
<!-- CRITICAL: Specify where the tests for this folder's code are located. -->
- **Test Location**: Are tests co-located (`.spec.ts` next to files) or in a separate `test/` directory?
- **Test Types**:
    - Unit tests (`.spec.ts`) for Services and Controllers?
    - Integration tests?
- **Special Cases**:
    - **No Code**: If this folder is config-only, state "No code to test".
    - **Manual Testing**: If manual testing is required, explain the process.
    - **External Tests**: If tested via "Kits" or external E2E suites (e.g., in `libs/testing` or `apps/e2e`), **explicitly link to those tests**. This is crucial for future migrations and ensuring coverage.

## Dependencies & Connections
<!-- What other files/folders is this folder connected to? Who consumes this? What does it consume? -->
- **Imports**: List key libraries or modules this folder depends on (e.g., `libs/infra`, `apps/pi-gateway`).
- **Consumers**: Who uses this code?

## Injections & Configuration
<!-- Details about dependency injection. -->
- **Providers**: Key services provided by this module.
- **Exports**: What is exposed to other modules?
- **Env Variables**: Key environment variables required.

## Maintenance Guidelines
<!-- Any specific guidelines to help maintain this folder. -->
- Known technical debt or TODOs.
- Performance considerations.
- Security notes.
