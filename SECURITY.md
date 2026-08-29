# Security Policy

## Supported Versions

The following versions of DT-RAM currently receive security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of DT-RAM seriously. If you discover a security vulnerability or sensitive information exposure:

1. **Do not open a public GitHub issue.**
2. Please contact the project maintainers privately or create a GitHub Private Security Advisory.
3. Include detailed steps to reproduce the vulnerability, along with proof of concept if applicable.
4. Maintainers will acknowledge receipt within 48 hours and coordinate remediation before public disclosure.

## Security Practices for Development

- Never commit secrets, API keys, passwords, private keys, or `.env` files into the repository.
- Use `.gitignore` and `.env.example` templates for configuration management.
- Always run microservices within isolated network boundaries and validate inputs before invoking cluster operations.
