# Agent Teams - Urban Intelligence

How we use parallel subagents in this codebase.

---

## When to Spawn Subagents

| Scenario | Profile | Mode |
|----------|---------|------|
| Research TfL API docs or camera coverage | `subagent_explore` | Background |
| Explore Gemini vision model capabilities | `subagent_explore` | Background |
| Implement new incident detection types | `subagent_general` | Foreground |
| Add tests for video analysis pipeline | `subagent_general` | Background |
| Refactor config or add new camera sources | `subagent_general` | Foreground |
| Security audit of API key handling | `subagent_explore` | Background |

---

## Domain-Specific Guidance

### Video Analysis Pipeline

The core loop: fetch → download → analyze → alert.

When modifying this flow in subagents:
- Always test with a real camera ID (use `list_cameras.py` to find one)
- Mock Gemini calls in tests - don't burn API credits
- Keep incident detection thresholds in `config.py`, not hardcoded

### TfL API Integration

- API is public but rate-limited
- Camera IDs are stable; video URLs rotate
- Subagents should use `requests_cache` when exploring endpoints

### Gemini Vision

- File API requires upload → poll → analyze → delete cycle
- Subagents must handle `PROCESSING` state properly
- Model version is configurable in `config.py`

---

## Conventions

**Error Handling**
- Use `try/finally` for temp file cleanup (see `main.py` pattern)
- Log errors with context; don't swallow exceptions silently

**Configuration**
- All tunables in `config.py` - never hardcode in logic
- Environment variables for secrets only

**Testing**
- Mock external APIs (TfL, Gemini)
- Test incident classification logic with synthetic JSON responses

---

## Custom Profiles

Create in `.devin/agents/<name>/AGENT.md` when needed:

- `vision-tester` - Specialized for testing Gemini prompt variations
- `incident-classifier` - Focused on severity ranking logic
- `api-explorer` - For TfL API discovery and documentation

See Devin docs: https://docs.devin.ai/subagents#custom-subagents
