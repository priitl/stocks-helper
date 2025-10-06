# Stocks Helper Constitution

<!--
Sync Impact Report:
Version: 1.0.0 → 1.0.0 (Initial formalization)
Modified Principles: None (formalized existing principles)
Added Sections:
  - Governance section with amendment procedures
  - Version tracking and ratification dates
Templates Status:
  ✅ plan-template.md - Constitution Check section aligned
  ✅ spec-template.md - Requirements completeness aligned
  ✅ tasks-template.md - TDD and testing discipline aligned
Follow-up TODOs: None
-->

## Core Principles

### I. Simplicity First
Start with the simplest solution that works. Add complexity only when justified by evidence. Prefer boring, proven technology over novel approaches.

**Rationale**: Complexity is the enemy of maintainability. Simple solutions are easier to understand, debug, and extend. Every layer of abstraction must earn its place by solving a real problem.

### II. Quality Over Speed (NON-NEGOTIABLE)
Never sacrifice code quality for quick delivery. Write tests before implementation (TDD). Keep functions small and focused (Single Responsibility Principle).

**Rationale**: Technical debt compounds. Fast shortcuts today become tomorrow's bottlenecks. Quality code is faster to change than rushed code is to fix.

### III. Fail Fast & Loud
Handle errors explicitly. Provide clear error messages. Never swallow exceptions silently.

**Rationale**: Silent failures hide problems until they become critical. Explicit error handling surfaces issues during development, not production.

### IV. Self-Documenting Code
Code should explain what it does. Comments explain why, not what. Clear naming over clever tricks.

**Rationale**: Code is read far more often than written. Self-documenting code reduces cognitive load and onboarding time. Comments rot, but well-named functions don't.

### V. Continuous Improvement
Refactor continuously, not in big batches. Keep technical debt visible. Regular code reviews.

**Rationale**: Small, incremental improvements prevent large, risky refactorings. Visible debt gets addressed; hidden debt accumulates.

## Technical Standards

### Code Organization
- **DRY (Don't Repeat Yourself)**: Extract common patterns into reusable functions
- **KISS (Keep It Simple, Stupid)**: Simple solutions beat clever ones
- **YAGNI (You Aren't Gonna Need It)**: Build what's needed now, not what might be needed
- **Single Responsibility**: Each function/class has one reason to change

### Testing (NON-NEGOTIABLE)
- **Test-Driven Development (TDD)**: Tests written → User approved → Tests fail → Then implement
- **Contract tests** for APIs: Verify request/response schemas
- **Integration tests** for user flows: End-to-end scenario validation
- **Unit tests** for business logic: Function-level correctness

**Red-Green-Refactor** cycle strictly enforced:
1. Write failing test (Red)
2. Write minimal code to pass (Green)
3. Improve code while keeping tests passing (Refactor)

### Error Handling
- **Explicit error types**: No generic exceptions
- **Contextual error messages**: Include what failed and why
- **Graceful degradation** where appropriate: Fallback to cached data, alternative APIs
- **No silent failures**: Log all errors, fail loudly

### Performance
- **Measure before optimizing**: Profile to find real bottlenecks
- **Set clear performance targets**: Response time, throughput, memory limits
- **Monitor key metrics**: Track performance over time

## Project Constraints

### Technology Choices
- **Maximum 2 primary languages** per project: Python for core, Shell for scripts
- **Prefer established libraries** over custom solutions: SQLAlchemy over raw SQL, TA-Lib over custom indicators
- **Justify each external dependency**: Document why needed in requirements

### Complexity Limits
- **Maximum 3 projects** in a repository: Current structure (CLI, models, services) is within limit
- **Avoid abstraction layers** without clear need: Repository pattern only if multiple storage backends
- **Challenge every "just in case" feature**: YAGNI principle applies to all new code

## Decision Process

1. **Evidence-Based**: Make decisions based on data, not assumptions
   - Profile before optimizing
   - A/B test before major UI changes
   - Benchmark before choosing libraries

2. **Reversible Choices**: Prefer decisions that can be changed later
   - Use adapters for external dependencies
   - Keep configuration external to code
   - Document migration paths

3. **Document Tradeoffs**: Record why alternatives were rejected
   - Architecture Decision Records (ADRs) for major choices
   - Comments explaining non-obvious decisions
   - README sections for design rationale

4. **Constitutional Review**: Every architectural decision must align with these principles
   - Simplicity First: Is this the simplest solution?
   - Quality Over Speed: Does this maintain code quality?
   - Fail Fast: Does this handle errors explicitly?
   - Self-Documenting: Is the code clear without comments?
   - Continuous Improvement: Does this reduce technical debt?

## Governance

### Amendment Procedure
1. **Propose change**: Document principle addition/modification with rationale
2. **Impact assessment**: Identify affected code, templates, workflows
3. **Review period**: Allow time for feedback and discussion
4. **Approval**: Consensus required for constitutional changes
5. **Migration plan**: Document how existing code adapts to new principles
6. **Update templates**: Propagate changes to spec, plan, and task templates
7. **Version bump**: Increment version according to semantic versioning

### Versioning Policy
- **MAJOR**: Backward incompatible principle removals or redefinitions
- **MINOR**: New principle added or materially expanded guidance
- **PATCH**: Clarifications, wording fixes, non-semantic refinements

### Compliance Review
- **All PRs** must verify alignment with constitutional principles
- **Complexity deviations** must be explicitly justified in design docs
- **Template consistency**: Spec, plan, and task templates must reflect current principles
- **Regular audits**: Quarterly review of adherence to principles

### Constitutional Supremacy
This constitution supersedes all other project practices. When local conventions conflict with constitutional principles, the constitution prevails. Teams may add additional practices but cannot remove constitutional requirements.

---

**Version**: 1.0.0 | **Ratified**: 2025-10-06 | **Last Amended**: 2025-10-06

*This constitution guides all development decisions. When in doubt, return to these principles.*
