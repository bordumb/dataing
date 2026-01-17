# Compliance

dataing is designed to help you meet your compliance requirements while investigating data quality issues.

---

## SOC 2 Type II <span class="beta-badge">Planned</span>

We are pursuing SOC 2 Type II certification with an expected completion in 2026.

### Trust Service Criteria

Our certification will cover these criteria:

| Criteria | Status | Controls |
|----------|--------|----------|
| **Security** | In Progress | Access controls, encryption, network security |
| **Availability** | In Progress | Uptime SLAs, disaster recovery |
| **Processing Integrity** | In Progress | Data validation, error handling |
| **Confidentiality** | In Progress | Data classification, encryption at rest |

### Control Framework

Key controls we implement:

- **Access Management** - RBAC with principle of least privilege
- **Audit Logging** - All API calls and data access logged
- **Encryption** - TLS 1.3 in transit, AES-256 at rest
- **Change Management** - Code review, CI/CD gates, rollback procedures
- **Incident Response** - Documented procedures, regular drills

!!! info "Certification Timeline"
    SOC 2 Type II audit is planned for Q3 2026. Contact sales@dataing.io for current status or to request our SOC 2 readiness report.

---

## Self-Hosted Deployment

For organizations with strict data residency requirements, dataing offers self-hosted deployment.

### Deployment Options

| Option | Description | Data Location |
|--------|-------------|---------------|
| **SaaS** | Fully managed cloud service | Our infrastructure |
| **Self-Hosted** | Deploy in your infrastructure | Your VPC/datacenter |
| **Hybrid** | Self-hosted with managed updates | Your infrastructure |

### Self-Hosted Benefits

- **Data Never Leaves Your Network** - All processing happens in your environment
- **Compliance Friendly** - Meet data residency and sovereignty requirements
- **Custom Security Controls** - Integrate with your existing security stack
- **Air-Gapped Option** - No external network access required

### Requirements

```yaml
# Minimum infrastructure requirements
compute:
  api_server:
    cpu: 2 cores
    memory: 4 GB
    storage: 20 GB SSD
  worker:
    cpu: 4 cores
    memory: 8 GB
    storage: 50 GB SSD

database:
  postgresql: ">=14"
  storage: 100 GB SSD

network:
  # Only required for SaaS LLM access
  outbound:
    - api.anthropic.com:443

# Optional: Self-hosted LLM
llm:
  provider: ollama  # or vllm, text-generation-inference
  models:
    - llama-3-70b
```

---

## Data Residency

### Current Regions

| Region | SaaS | Self-Hosted |
|--------|------|-------------|
| US (us-east-1) | :material-check-circle:{ .green } | :material-check-circle:{ .green } |
| EU | :material-clock-outline: Coming Soon | :material-check-circle:{ .green } |
| APAC | :material-clock-outline: Coming Soon | :material-check-circle:{ .green } |

### EU Data Protection

For EU customers, we commit to:

- Data processed only in EU regions (self-hosted available now)
- Standard Contractual Clauses (SCCs) for data transfers
- DPA (Data Processing Agreement) available on request

---

## Audit Logging <span class="enterprise-badge">Enterprise</span>

Enterprise Edition provides comprehensive audit logging for compliance:

### Logged Events

| Event Category | Examples |
|----------------|----------|
| **Authentication** | Login success/failure, API key usage |
| **Authorization** | Permission grants, role changes |
| **Data Access** | Investigation views, query execution |
| **Administration** | User management, settings changes |
| **Security** | Failed validation, circuit breaker trips |

### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "event_type": "investigation.query_executed",
  "actor": {
    "user_id": "user_123",
    "email": "analyst@company.com",
    "ip_address": "10.0.1.50"
  },
  "resource": {
    "type": "investigation",
    "id": "inv_456"
  },
  "action": "query_executed",
  "result": "success",
  "metadata": {
    "datasource": "snowflake_prod",
    "query_hash": "abc123..."
  }
}
```

### Export & Integration

Audit logs can be exported to:

- **SIEM Systems** - Splunk, Datadog, Sumo Logic
- **Cloud Storage** - S3, GCS, Azure Blob
- **Custom Webhooks** - Your logging infrastructure

---

## Security Questionnaires

We provide pre-filled responses for common security questionnaires:

| Questionnaire | Status |
|---------------|--------|
| SIG Lite | Available |
| CAIQ | Available |
| VSA | Available |
| Custom | Contact us |

Contact security@dataing.io to request questionnaire responses.

---

## Vulnerability Disclosure

### Responsible Disclosure

If you discover a security vulnerability, please report it responsibly:

1. Email security@dataing.io with details
2. Include steps to reproduce
3. Allow 90 days for remediation before public disclosure
4. We will acknowledge receipt within 24 hours

### Bug Bounty

We offer rewards for qualifying security reports. See our [Bug Bounty Program](https://dataing.io/security/bug-bounty) for details.

---

## Compliance Resources

| Resource | Description |
|----------|-------------|
| [Data Privacy](data-privacy.md) | How we protect your data |
| [RBAC & SSO](rbac.md) | Access control details |
| Security Whitepaper | Architecture and controls (contact sales) |
| DPA Template | Data Processing Agreement (contact legal) |
| Penetration Test Report | Third-party assessment (under NDA) |

!!! tip "Enterprise Compliance Support"
    Enterprise customers receive dedicated compliance support, including custom security reviews and integration assistance. Contact sales@dataing.io.
