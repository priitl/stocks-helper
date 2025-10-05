# Project Constitution: Stocks Helper

## Core Principles

### 1. Simplicity First
- Start with the simplest solution that works
- Add complexity only when justified by evidence
- Prefer boring, proven technology over novel approaches

### 2. Quality Over Speed
- Never sacrifice code quality for quick delivery
- Write tests before implementation (TDD)
- Keep functions small and focused (SRP)

### 3. Fail Fast & Loud
- Handle errors explicitly
- Provide clear error messages
- Never swallow exceptions silently

### 4. Self-Documenting Code
- Code should explain what it does
- Comments explain why, not what
- Clear naming over clever tricks

### 5. Continuous Improvement
- Refactor continuously, not in big batches
- Keep technical debt visible
- Regular code reviews

## Technical Standards

### Code Organization
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple, Stupid)
- YAGNI (You Aren't Gonna Need It)
- Single Responsibility Principle

### Testing
- Test-Driven Development (TDD)
- Contract tests for APIs
- Integration tests for user flows
- Unit tests for business logic

### Error Handling
- Explicit error types
- Contextual error messages
- Graceful degradation where appropriate
- No silent failures

### Performance
- Measure before optimizing
- Set clear performance targets
- Monitor key metrics

## Project Constraints

### Technology Choices
- Maximum 2 primary languages per project
- Prefer established libraries over custom solutions
- Justify each external dependency

### Complexity Limits
- Maximum 3 projects in a repository
- Avoid abstraction layers without clear need
- Challenge every "just in case" feature

## Decision Process

1. **Evidence-Based**: Make decisions based on data, not assumptions
2. **Reversible Choices**: Prefer decisions that can be changed later
3. **Document Tradeoffs**: Record why alternatives were rejected
4. **Constitutional Review**: Every architectural decision must align with these principles

---

*This constitution guides all development decisions. When in doubt, return to these principles.*
