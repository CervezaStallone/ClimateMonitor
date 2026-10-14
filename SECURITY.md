# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.5.x   | :white_check_mark: |
| 1.4.x   | :x:                |
| 1.3.x   | :x:                |
| < 1.3   | :x:                |

## Reporting a Vulnerability

We take the security of Climate Monitor seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please Do NOT:

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before it has been addressed
- Exploit the vulnerability for any reason

### Please DO:

**Report security vulnerabilities privately** by:

1. **Creating a private security advisory** on GitHub:
   - Go to the repository's Security tab
   - Click "Report a vulnerability"
   - Fill out the form with details

2. **Or contact the maintainers directly** via email (if listed in the repository)

### What to Include in Your Report

To help us understand and address the issue quickly, please include:

- **Type of vulnerability** (e.g., SQL injection, authentication bypass, etc.)
- **Full path of affected source file(s)** with line numbers if possible
- **Location of affected code** (tag/branch/commit or direct URL)
- **Step-by-step instructions** to reproduce the issue
- **Proof of concept** or exploit code (if possible)
- **Impact of the vulnerability** - what an attacker could achieve
- **Suggested fix** (if you have one)

### Response Timeline

- **Initial Response**: Within 48 hours of report submission
- **Status Update**: Within 7 days with assessment and action plan
- **Fix Timeline**: Critical vulnerabilities will be addressed within 30 days
- **Disclosure**: We will coordinate disclosure timing with you

## Security Best Practices for Users

### Network Security

- **Run on trusted networks only** - avoid exposing the application directly to the internet
- **Use firewall rules** to restrict access to port 8050 (default)
- **Consider reverse proxy** (nginx/Apache) with HTTPS for remote access
- **Use VPN** for remote monitoring instead of direct exposure

### Configuration Security

- **Protect .env file** - never commit it to version control
- **Use strong credentials** if adding authentication
- **Limit file permissions** on configuration files:
  ```bash
  chmod 600 .env  # Linux/macOS
  ```
- **Regular updates** - keep Python and dependencies up to date

### Database Security

- **Protect database file** - located in `src/modbus_sensor_data.db`
- **Regular backups** - keep backups of sensor data
- **Access control** - limit read/write permissions to application user only

### Serial Port Access

- **Physical security** - secure RS-485 connections to prevent tampering
- **Verify sensor** - ensure XY-MD02 sensor is legitimate hardware
- **Monitor logs** - check for unusual Modbus communication patterns

### Python Environment

- **Use virtual environments** - isolate dependencies
- **Pin dependency versions** - specified in `requirements.txt`
- **Audit dependencies** - use `pip-audit` or similar tools:
  ```bash
  pip install pip-audit
  pip-audit
  ```

## Known Security Considerations

### Current Architecture

This application is designed for **local network deployment** and includes:

- **No built-in authentication** - suitable for trusted local networks only
- **HTTP only** - HTTPS should be added via reverse proxy for remote access
- **Direct database access** - file-based SQLite with no access control
- **Serial port access** - requires elevated permissions on some systems

### Not Recommended For

- **Direct internet exposure** without additional security layers
- **Multi-tenant environments** without authentication/authorization
- **Sensitive/regulated environments** without additional hardening
- **Production systems** handling critical infrastructure

## Security Updates

Security updates will be released as:

- **Patch versions** (e.g., 1.5.3 → 1.5.4) for minor security fixes
- **Minor versions** (e.g., 1.5.x → 1.6.0) for moderate security improvements
- **Immediate hotfixes** for critical vulnerabilities

Check the [Releases](https://github.com/CervezaStallone/ClimateMonitor/releases) page for security-related updates.

## Acknowledgments

We appreciate security researchers and users who report vulnerabilities responsibly. Contributors who report valid security issues may be acknowledged in:

- Release notes (with permission)
- This security policy
- Project README (for significant findings)

---

**Thank you for helping keep Climate Monitor and its users safe!** 🔒
