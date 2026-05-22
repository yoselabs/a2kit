## MODIFIED Requirements

### Requirement: Cleanup stack unwinds in LIFO order with per-resource exception isolation

When a scope closes, the framework SHALL iterate the cleanup stack in reverse insertion order (LIFO) and invoke each entry's cleanup callable.
Each invocation SHALL be wrapped in `try`/`except` such that a raised exception during one resource's cleanup SHALL be logged through the framework's dedicated DI-cleanup logger (a `logging` channel scoped to the cleanup stack, defined in `a2kit.packages.di`) at WARN level with traceback, and unwinding SHALL continue with the remaining entries. The framework SHALL NOT re-raise individual cleanup exceptions during unwind.

#### Scenario: Bad cleanup logged and skipped

- **GIVEN** three resources entered in order `A`, `B`, `C` where `B`'s cleanup raises `RuntimeError("bad")`
- **WHEN** the scope closes
- **THEN** `C`'s cleanup runs first
- **AND** `B`'s cleanup raises and is logged at WARN with the traceback
- **AND** `A`'s cleanup runs after `B`'s logged failure
- **AND** the scope close completes without re-raising `RuntimeError("bad")`

#### Scenario: Body exception is preserved when cleanup also raises

- **GIVEN** a per-call scope where the tool body raised `ToolError("x")` and a per-call resource's cleanup raises `ShutdownError("y")`
- **WHEN** the per-call scope closes
- **THEN** the dispatcher's caller sees `ToolError("x")` (the original tool exception)
- **AND** `ShutdownError("y")` was logged at WARN
