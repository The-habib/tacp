# Remote Lockdown & Emergency Controls

## Emergency Procedures
* **Process Kill**: `pkill -f tunnel-client` terminates outbound TLS instantly.
* **Policy Kill Switch**: `export TACP_REMOTE_ENABLED=false` immediately causes fail-closed rejection of all incoming remote requests.
* **Lockdown Profile**: `export TACP_TRUST_PROFILE=LOCKDOWN` disables all mutating and executing capabilities across all principals.
