# Remote Security & Boundary Defenses

## Defense Layers
1. **Path Jailing**: Strict resolution relative to authorized workspace roots. Traversals (`../`) rejected.
2. **Secret Defense**: `.env`, `id_rsa`, `credentials.json` blocked with `SECRET_PROTECTED`.
3. **Injection Resistance**: Hostile prompt injections in files remain passive text; zero elevation.
4. **Output Limits**: File reads and listings strictly bounded by `OutputLimits`.
