# Phase 3 Evidence — Secret Redaction & Log Protection Audit

**Document ID**: TACP-EV-P3-10  
**Status**: VERIFIED  

## 1. Pattern Redaction
The following sensitive tokens are automatically scrubbed from inputs, outputs, error messages, and audit payloads:
- OpenSSH / RSA / Ed25519 Private Keys
- GitHub Personal Access Tokens (`ghp_...`, `github_pat_...`)
- OpenAI API Keys (`sk-...`)
- Google OAuth Access Tokens (`ya29....`)
- Bearer tokens in error strings

## 2. Error Message Sanitization
- MCP `tools/call` redacts secrets from all `TacpError` exception strings.
- Unhandled internal exceptions log detailed tracebacks to system logger and emit generic messages to callers with request IDs.
- Raw bearer approval tokens are never written to audit logs or database tables.
