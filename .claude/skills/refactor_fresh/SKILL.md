---
name: refactor-fresh
description: Use this skill when debugging or refactoring code. Enforces clean architecture over duct-tape fixes. Delete bad code, don't patch it. If the user invokes this skill without input, you must first ask them what the issue is.
---

## Core Philosophy

**Delete and rewrite > Patch and pray**

When you encounter buggy or poorly architected code, your instinct should be to:
1. Understand the TRUE root cause
2. Design a clean solution from first principles
3. Delete the problematic code entirely
4. Write fresh, well-architected code

**DO NOT:**
- Add mocks/stubs to make tests pass without fixing the real issue
- Add workarounds that preserve broken behavior
- Create compatibility shims for code that should just be deleted
- Add try/catch blocks to suppress errors instead of fixing them

---

## Before Writing Any Code

### Step 1: Understand the ACTUAL data flow

Before touching code, trace the complete data flow:

```
1. Where does the data originate?
2. What transformations happen along the way?
3. Where does it end up?
4. At which step does the bug manifest?
```

**Run real queries. Look at real data. Don't assume.**

```bash
# Example: Check actual database state
PGPASSWORD=xxx psql -h localhost -U user -d db -c "SELECT * FROM table LIMIT 5;"

# Example: Check actual API response
curl -s http://localhost:8000/api/endpoint | jq .

# Example: Add temporary logging to trace flow
logger.info(f"DEBUG: value at step X = {value}")
```

### Step 2: Identify the ROOT cause, not symptoms

Ask yourself:
- Is this a data problem or a code problem?
- Is this a design flaw or an implementation bug?
- Is the architecture fundamentally broken or just this one function?

**Red flags that you're treating symptoms, not causes:**
- "Let me add a null check here"
- "Let me cache this value"
- "Let me add a retry loop"
- "Let me add a fallback"

**Good signs you found the root cause:**
- "The data is being mutated when it shouldn't be"
- "This function is being called with the wrong arguments"
- "The state is shared when it should be isolated"
- "The sequence of operations is wrong"

### Step 3: Design the fix BEFORE coding

Write out:
1. What the correct behavior should be
2. What architectural changes are needed
3. What files will be modified or deleted
4. What the data flow will look like after the fix

---

## When Refactoring

### Delete First, Write Second

```python
# BAD: Patching broken code
def broken_function():
    # Old broken logic
    result = do_something_wrong()
    # NEW: Add workaround for bug
    if result is None:
        result = fallback_value  # This hides the real problem
    return result

# GOOD: Delete and rewrite
def fixed_function():
    # Fresh implementation that addresses root cause
    return do_something_correct()
```

### No Backwards Compatibility for Pre-Launch Code

Per CLAUDE.md: "DO NOT worry about legacy code or keeping backwards compatibility. We are pre-launch."

This means:
- Delete old implementations entirely
- Don't create adapter/shim layers
- Don't keep old function signatures "for compatibility"
- Don't comment out old code "just in case"

### Proper Isolation Over Shared State

When code has bugs due to shared state:

```python
# BAD: Shared mutable state causing bugs
class BadOrchestrator:
    def __init__(self):
        self.current_result = None  # Shared across all branches!

    async def process_branch(self, branch):
        self.current_result = await execute(branch)  # Race condition!

# GOOD: Isolated state per operation
class GoodOrchestrator:
    async def process_branch(self, branch):
        result = await execute(branch)  # Local, isolated
        return result  # Return instead of storing
```

---

## Debugging Checklist

Before claiming a bug is fixed, verify:

- [ ] I traced the actual data flow with real data
- [ ] I identified the root cause, not just a symptom
- [ ] I deleted broken code instead of patching it
- [ ] The fix addresses the architectural issue, not just this instance
- [ ] I tested with real scenarios, not just mocked ones
- [ ] No new workarounds, fallbacks, or compatibility shims were added

---

## Anti-Patterns to Avoid

### 1. Mock Masking
```python
# BAD: Making tests pass by mocking away the problem
def test_something():
    with patch('module.broken_function', return_value="fake"):
        result = function_under_test()  # Test passes but bug still exists!
```

### 2. Null Suppression
```python
# BAD: Hiding bugs with null checks
value = possibly_broken_call()
if value is not None:  # Why would it be None? Fix the source!
    process(value)
```

### 3. Try-Catch Burial
```python
# BAD: Burying errors instead of fixing them
try:
    result = broken_operation()
except Exception:
    result = default_value  # Bug is hidden, not fixed
```

### 4. Retry Loops for Logic Bugs
```python
# BAD: Retrying when the logic itself is wrong
for attempt in range(3):
    try:
        result = broken_logic()  # If the logic is wrong, retries won't help
        break
    except:
        continue
```

### 5. Adapter/Shim Layers
```python
# BAD: Adding adapters to make broken interfaces work
class BrokenToWorkingAdapter:
    def __init__(self, broken_thing):
        self.broken = broken_thing

    def do_something(self):
        # Translate broken behavior to expected behavior
        raw = self.broken.bad_method()
        return self._fix_broken_output(raw)  # Just fix the source!
```

---

## The Right Way to Debug

### 1. Reproduce with minimal code

Strip away everything until you have the smallest reproduction:

```python
# Minimal reproduction
async def test_minimal_repro():
    # Setup
    x = create_minimal_input()

    # The bug
    result = the_buggy_function(x)

    # Verification
    assert result == expected, f"Got {result}"
```

### 2. Add strategic logging at boundaries

```python
async def function_under_investigation(input_data):
    logger.info(f"INPUT: {input_data}")

    intermediate = step_one(input_data)
    logger.info(f"AFTER STEP 1: {intermediate}")

    result = step_two(intermediate)
    logger.info(f"OUTPUT: {result}")

    return result
```

### 3. Verify fixes with real data

```bash
# Don't just run unit tests - verify with real system e.g.
curl http://localhost:8000/api/endpoint
# or e.g.
SELECT * FROM table WHERE condition;
```

---

## Summary

1. **Understand** the true data flow
2. **Identify** the root cause, not symptoms
3. **Design** the fix architecturally
4. **Delete** broken code entirely
5. **Write** fresh, clean code
6. **Verify** with real data, not mocks
