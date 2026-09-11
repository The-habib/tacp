# Evidence: Tunnel Security & Secret Defense

## Secret File Protection Test Evidence
* **Target Files**: `.env`, `id_rsa`, `credentials.json`
* **Test Case**: `TestRemoteSecretDefense` in `tests/security/test_remote_security.py`
* **Result**:
  * `.env` -> `SECRET_PROTECTED` exception raised. Access denied.
  * `id_rsa` -> `SECRET_PROTECTED` exception raised. Access denied.
  * `credentials.json` -> Access denied.

## Path Traversal Defense Test Evidence
* **Attack Vectors**:
  * `../../../etc/passwd` -> `OUTSIDE_WORKSPACE` detected and rejected.
  * `/data/data/com.termux/files/home/.bashrc` -> Absolute path escape rejected.
  * `symlink_escape` -> Symlink pointing outside workspace root resolved and rejected.

## Credential Segregation Verification
* `OPENAI_ADMIN_KEY` is not present in runtime environment or stored anywhere on disk.
* `CONTROL_PLANE_API_KEY` is referenced solely via process environment and is masked in all CLI/doctor outputs (`CONFIGURED (hidden)`).
* `test_no_secrets_in_repository_files` confirms zero secret leaks in git repository.
