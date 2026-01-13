# fn-6.3 Add Client Secret Encryption

## Description

Add encryption for OIDC client secrets stored in `sso_configs.oidc_client_secret_encrypted`. Currently the code just encodes to bytes without actual encryption.

## Implementation

1. Add `cryptography` package (Fernet symmetric encryption)
2. Create `dataing-ee/src/dataing_ee/core/sso/encryption.py`:
   - `encrypt_secret(plaintext: str) -> bytes`
   - `decrypt_secret(ciphertext: bytes) -> str`
3. Use encryption key from environment: `SSO_SECRET_KEY`
4. Update `SSORepository.create_config()` to encrypt before storing
5. Update `SSORepository.get_config()` to decrypt after reading

## Key Files

- `dataing-ee/src/dataing_ee/adapters/sso/repository.py:82` - Current plaintext storage
- New: `dataing-ee/src/dataing_ee/core/sso/encryption.py`

## Security

- Use Fernet (AES-128-CBC with HMAC)
- Key must be 32 bytes URL-safe base64 encoded
- Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Never log decrypted secrets
## Acceptance
- [ ] `encryption.py` module with encrypt/decrypt functions
- [ ] Uses Fernet symmetric encryption
- [ ] Encryption key loaded from `SSO_SECRET_KEY` env var
- [ ] `SSORepository` encrypts secrets on create/update
- [ ] `SSORepository` decrypts secrets on read
- [ ] Missing key raises clear error on startup
- [ ] Unit tests with test key
## Done summary
Added Fernet encryption for SSO client secrets:

- Created encryption.py module with:
  - encrypt_secret(plaintext) / decrypt_secret(ciphertext) functions
  - Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256)
  - Encryption key loaded from SSO_SECRET_KEY environment variable
  - LRU-cached Fernet instance for performance
  - clear_key_cache() for testing and key rotation
  - generate_key() helper for generating new keys
- Added exception hierarchy: EncryptionError → MissingEncryptionKeyError
- Updated SSORepository:
  - create_sso_config() now encrypts client_secret before storing
  - Added get_decrypted_client_secret(org_id) for IdP API calls
  - Added update_client_secret(org_id, secret) for updating secrets
- Added conftest.py with auto-fixture for test encryption key
- Added 13 unit tests for encryption module
## Evidence
- Commits:
- Tests: dataing-ee/tests/unit/core/sso/test_encryption.py (13 tests)
- PRs:
