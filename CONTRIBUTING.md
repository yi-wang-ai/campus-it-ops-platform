# Contributing

This is a portfolio lab, with explicitly original integration code. Small, focused improvements are welcome.

1. Open an issue describing the bug, impact and reproduction steps, without attaching secrets or real IP addresses.
2. Make a feature branch and keep security controls enabled.
3. Run `python -m pytest -q`, `node scripts/test-webhook.cjs`, and Ansible syntax checks where available.
4. Document new environment variables in `.env.example`; never commit actual credentials.
5. Add tests for every state transition, including failure paths.
6. Submit a pull request with the relevant test output and explain whether the evidence is simulated, local, or from a real isolated lab.

The project does not accept features that execute arbitrary commands from unauthenticated monitoring events.
