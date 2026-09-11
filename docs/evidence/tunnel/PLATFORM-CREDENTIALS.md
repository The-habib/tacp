# Platform Credentials & Authority Separation

## Model
* **Scope**: Restricted Runtime Key only.
* **Required Permissions**:
  * `Tunnels: Read`
  * `Tunnels: Use`
* **Zero Persistence**: Key is never written to project files, git history, or database records.
* **Reference**: Referenced strictly via `env:CONTROL_PLANE_API_KEY`.
