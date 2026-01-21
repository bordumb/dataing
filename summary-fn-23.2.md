# fn-23.2 Server Extension Credential Storage - Done

## Summary

Implemented credential storage with 3 explicit modes (keychain, env_var, session) and wizard detection for the Jupyter server extension.

## Changes

### New Files
- `python-packages/dataing-notebook/src/dataing_notebook/serverextension/credentials.py` - Credential storage module
- `python-packages/dataing-notebook/tests/test_credentials.py` - Unit tests (17 tests)

### Modified Files
- `python-packages/dataing-notebook/src/dataing_notebook/serverextension/handlers.py`:
  - Added `CredentialHandler` for CRUD operations
  - Updated `get_api_key()` to use new precedence order
  - Registered `/dataing/credentials` endpoint
- `python-packages/dataing-notebook/pyproject.toml` - Added `keyring` optional dependency

## API Endpoints

```
GET /dataing/credentials
  Returns: {mode: "keychain"|"env_var"|"session", stored: bool, explanation: str}

POST /dataing/credentials
  Body: {api_key: "...", persist: bool}
  persist=true: Use keychain if available
  persist=false: Force session-only storage

DELETE /dataing/credentials
  Clears both keychain and session credentials
```

## Credential Precedence (highest first)
1. Session-only memory store
2. OS keychain (via keyring library)
3. DATAING_API_KEY environment variable

## Security Model
- Actual credential values are NEVER returned via API
- XSRF protection enabled for credential endpoints
- Session-only stored in server extension process memory only
- Credentials never logged, even in debug mode

## Acceptance Criteria Met
- [x] GET returns mode, stored, explanation
- [x] POST with persist=true stores in keychain
- [x] POST with persist=false stores session-only
- [x] DELETE clears both keychain and session
- [x] Mode detection correctly identifies available modes
- [x] Env var DATAING_API_KEY is detected as fallback
- [x] Graceful degradation when keyring unavailable
- [x] XSRF protection enabled
- [x] Unit tests written (17 tests)
- [x] Code compiles and passes ruff checks

## Notes
- Tests require full workspace setup due to dataing-sdk dependency
- keyring is an optional dependency (`pip install dataing-notebook[keyring]`)
