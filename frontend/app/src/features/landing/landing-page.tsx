import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  Zap,
  Shield,
  Database,
  GitBranch,
  Terminal,
  ArrowRight,
  Check,
  ExternalLink,
} from 'lucide-react'

type TabId = 'install' | 'docs' | 'pricing'

export function LandingPage() {
  const [activeTab, setActiveTab] = useState<TabId>('install')

  return (
    <div className="landing-page">
      {/* Animated grid background */}
      <div className="landing-grid-bg" />
      <div className="landing-glow" />

      {/* Navigation */}
      <header className="landing-header">
        <div className="landing-container">
          <nav className="landing-nav">
            <div className="landing-logo">
              <div className="landing-logo-icon">
                <Database className="h-5 w-5" />
              </div>
              <span className="landing-logo-text">dataing</span>
            </div>

            <div className="landing-tabs">
              <button
                className={`landing-tab ${activeTab === 'install' ? 'active' : ''}`}
                onClick={() => setActiveTab('install')}
              >
                Install
              </button>
              <button
                className={`landing-tab ${activeTab === 'docs' ? 'active' : ''}`}
                onClick={() => setActiveTab('docs')}
              >
                Docs
              </button>
              <button
                className={`landing-tab ${activeTab === 'pricing' ? 'active' : ''}`}
                onClick={() => setActiveTab('pricing')}
              >
                Pricing
              </button>
            </div>

            <div className="landing-nav-actions">
              <a
                href="https://github.com/dataing/dataing"
                target="_blank"
                rel="noopener noreferrer"
                className="landing-github-link"
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
              </a>
              <Link to="/login" className="landing-btn-secondary">
                Sign in
              </Link>
              <Link to="/login" className="landing-btn-primary">
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </nav>
        </div>
      </header>

      {/* Main content based on active tab */}
      <main className="landing-main">
        {activeTab === 'install' && <InstallSection />}
        {activeTab === 'docs' && <DocsSection />}
        {activeTab === 'pricing' && <PricingSection />}
      </main>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-container">
          <div className="landing-footer-content">
            <div className="landing-footer-brand">
              <div className="landing-logo">
                <div className="landing-logo-icon">
                  <Database className="h-5 w-5" />
                </div>
                <span className="landing-logo-text">dataing</span>
              </div>
              <p className="landing-footer-tagline">
                Autonomous data quality investigation
              </p>
            </div>
            <div className="landing-footer-links">
              <a href="https://github.com/dataing/dataing" target="_blank" rel="noopener noreferrer">
                GitHub
              </a>
              <a href="#" onClick={() => setActiveTab('docs')}>
                Documentation
              </a>
              <a href="#" onClick={() => setActiveTab('pricing')}>
                Pricing
              </a>
            </div>
          </div>
          <div className="landing-footer-bottom">
            <p>&copy; {new Date().getFullYear()} Dataing. Open-core software.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

function InstallSection() {
  return (
    <>
      {/* Hero */}
      <section className="landing-hero">
        <div className="landing-container">
          <div className="landing-hero-content">
            <div className="landing-badge">
              <span className="landing-badge-dot" />
              Open Source
            </div>
            <h1 className="landing-title">
              <span className="landing-title-accent">Autonomous</span> data quality
              <br />
              investigation platform
            </h1>
            <p className="landing-subtitle">
              Detect anomalies. Generate hypotheses. Test with SQL. Synthesize root causes.
              <br />
              All powered by LLMs working in parallel.
            </p>
            <div className="landing-cta-group">
              <Link to="/login" className="landing-btn-primary landing-btn-lg">
                Start investigating
                <ArrowRight className="h-5 w-5" />
              </Link>
              <a
                href="https://github.com/dataing/dataing"
                target="_blank"
                rel="noopener noreferrer"
                className="landing-btn-secondary landing-btn-lg"
              >
                View on GitHub
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>

            {/* Install command */}
            <div className="landing-install-box">
              <div className="landing-install-header">
                <Terminal className="h-4 w-4" />
                <span>Quick install</span>
              </div>
              <div className="landing-install-commands">
                <code>
                  <span className="landing-code-comment"># Clone and setup</span>
                  <br />
                  git clone https://github.com/bordumb/dataing.git
                  <br />
                  cd dataing
                  <br />
                  just setup
                  <br />
                  <br />
                  <span className="landing-code-comment"># Run development stack</span>
                  <br />
                  just dev
                </code>
              </div>
            </div>
          </div>

          {/* Animated visualization */}
          <div className="landing-hero-visual">
            <div className="landing-data-flow">
              <DataFlowAnimation />
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="landing-features">
        <div className="landing-container">
          <div className="landing-section-header">
            <h2 className="landing-section-title">How it works</h2>
            <p className="landing-section-subtitle">
              Dataing automates the tedious parts of data investigation
            </p>
          </div>

          <div className="landing-features-grid">
            <FeatureCard
              icon={<Search />}
              title="Anomaly Detection"
              description="Automatically detect data quality issues like null spikes, volume drops, schema drift, and duplicates."
              delay={0}
            />
            <FeatureCard
              icon={<Zap />}
              title="Hypothesis Generation"
              description="LLMs generate multiple hypotheses about potential root causes based on context and patterns."
              delay={100}
            />
            <FeatureCard
              icon={<Database />}
              title="Parallel SQL Testing"
              description="Test hypotheses concurrently with safe, validated SQL queries against your data warehouse."
              delay={200}
            />
            <FeatureCard
              icon={<GitBranch />}
              title="Lineage Integration"
              description="Connect to OpenLineage, dbt, Dagster, Airflow, or DataHub for full data lineage context."
              delay={300}
            />
            <FeatureCard
              icon={<Shield />}
              title="Enterprise Ready"
              description="SSO/OIDC, SCIM, audit logging, and role-based access control for enterprise deployments."
              delay={400}
            />
            <FeatureCard
              icon={<Terminal />}
              title="Open Core"
              description="Community Edition is fully open source. Enterprise Edition adds advanced features."
              delay={500}
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="landing-cta-section">
        <div className="landing-container">
          <div className="landing-cta-box">
            <h2>Ready to automate your data investigations?</h2>
            <p>Get started in minutes with our quick setup guide.</p>
            <Link to="/login" className="landing-btn-primary landing-btn-lg">
              Get Started Free
              <ArrowRight className="h-5 w-5" />
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}

function DocsSection() {
  const docLinks = [
    {
      title: 'Getting Started',
      description: 'Installation, configuration, and your first investigation',
      href: 'https://docs.dataing.io/getting-started',
      icon: <Terminal />,
    },
    {
      title: 'Architecture',
      description: 'Understanding the maestro workflow engine and bond agent runtime',
      href: 'https://docs.dataing.io/architecture',
      icon: <GitBranch />,
    },
    {
      title: 'Data Sources',
      description: 'Connect SQL databases, document stores, and enterprise systems',
      href: 'https://docs.dataing.io/datasources',
      icon: <Database />,
    },
    {
      title: 'Lineage Providers',
      description: 'Integrate with OpenLineage, dbt, Dagster, Airflow, DataHub',
      href: 'https://docs.dataing.io/lineage',
      icon: <GitBranch />,
    },
    {
      title: 'API Reference',
      description: 'REST API endpoints for programmatic access',
      href: 'https://docs.dataing.io/api',
      icon: <Zap />,
    },
    {
      title: 'Enterprise Edition',
      description: 'SSO, SCIM, audit logging, and advanced datasource adapters',
      href: 'https://docs.dataing.io/enterprise',
      icon: <Shield />,
    },
  ]

  return (
    <section className="landing-docs">
      <div className="landing-container">
        <div className="landing-section-header">
          <h1 className="landing-section-title">Documentation</h1>
          <p className="landing-section-subtitle">
            Everything you need to get started with Dataing
          </p>
        </div>

        <div className="landing-docs-grid">
          {docLinks.map((doc, index) => (
            <a
              key={doc.title}
              href={doc.href}
              target="_blank"
              rel="noopener noreferrer"
              className="landing-doc-card"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div className="landing-doc-icon">{doc.icon}</div>
              <div className="landing-doc-content">
                <h3>{doc.title}</h3>
                <p>{doc.description}</p>
              </div>
              <ExternalLink className="landing-doc-arrow" />
            </a>
          ))}
        </div>

        <div className="landing-docs-cta">
          <p>Can't find what you're looking for?</p>
          <a
            href="https://github.com/dataing/dataing/discussions"
            target="_blank"
            rel="noopener noreferrer"
            className="landing-btn-secondary"
          >
            Ask the community
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </section>
  )
}

function PricingSection() {
  return (
    <section className="landing-pricing">
      <div className="landing-container">
        <div className="landing-section-header">
          <h1 className="landing-section-title">Simple, transparent pricing</h1>
          <p className="landing-section-subtitle">
            Start free with Community Edition. Upgrade for enterprise features.
          </p>
        </div>

        <div className="landing-pricing-grid">
          {/* Community */}
          <div className="landing-pricing-card">
            <div className="landing-pricing-header">
              <h3>Community</h3>
              <div className="landing-pricing-price">
                <span className="landing-price-amount">$0</span>
                <span className="landing-price-period">forever</span>
              </div>
              <p className="landing-pricing-desc">
                Full-featured open source edition
              </p>
            </div>
            <ul className="landing-pricing-features">
              <li>
                <Check className="h-4 w-4" />
                Unlimited investigations
              </li>
              <li>
                <Check className="h-4 w-4" />
                All anomaly detection types
              </li>
              <li>
                <Check className="h-4 w-4" />
                SQL datasource adapters
              </li>
              <li>
                <Check className="h-4 w-4" />
                OpenLineage integration
              </li>
              <li>
                <Check className="h-4 w-4" />
                Webhook notifications
              </li>
              <li>
                <Check className="h-4 w-4" />
                Community support
              </li>
            </ul>
            <a
              href="https://github.com/dataing/dataing"
              target="_blank"
              rel="noopener noreferrer"
              className="landing-btn-secondary landing-btn-full"
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>

          {/* Pro */}
          <div className="landing-pricing-card landing-pricing-featured">
            <div className="landing-pricing-badge">Most Popular</div>
            <div className="landing-pricing-header">
              <h3>Pro</h3>
              <div className="landing-pricing-price">
                <span className="landing-price-amount">$49</span>
                <span className="landing-price-period">/user/month</span>
              </div>
              <p className="landing-pricing-desc">
                For growing data teams
              </p>
            </div>
            <ul className="landing-pricing-features">
              <li>
                <Check className="h-4 w-4" />
                Everything in Community
              </li>
              <li>
                <Check className="h-4 w-4" />
                Priority investigation queue
              </li>
              <li>
                <Check className="h-4 w-4" />
                Advanced datasource adapters
              </li>
              <li>
                <Check className="h-4 w-4" />
                Slack & email notifications
              </li>
              <li>
                <Check className="h-4 w-4" />
                Usage analytics dashboard
              </li>
              <li>
                <Check className="h-4 w-4" />
                Email support
              </li>
            </ul>
            <Link to="/login" className="landing-btn-primary landing-btn-full">
              Start Free Trial
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* Enterprise */}
          <div className="landing-pricing-card">
            <div className="landing-pricing-header">
              <h3>Enterprise</h3>
              <div className="landing-pricing-price">
                <span className="landing-price-amount">Custom</span>
              </div>
              <p className="landing-pricing-desc">
                For large organizations
              </p>
            </div>
            <ul className="landing-pricing-features">
              <li>
                <Check className="h-4 w-4" />
                Everything in Pro
              </li>
              <li>
                <Check className="h-4 w-4" />
                SSO / OIDC / SAML
              </li>
              <li>
                <Check className="h-4 w-4" />
                SCIM provisioning
              </li>
              <li>
                <Check className="h-4 w-4" />
                Audit logging
              </li>
              <li>
                <Check className="h-4 w-4" />
                Salesforce, HubSpot, Stripe adapters
              </li>
              <li>
                <Check className="h-4 w-4" />
                Dedicated support
              </li>
            </ul>
            <a href="mailto:sales@dataing.io" className="landing-btn-secondary landing-btn-full">
              Contact Sales
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}

function FeatureCard({
  icon,
  title,
  description,
  delay,
}: {
  icon: React.ReactNode
  title: string
  description: string
  delay: number
}) {
  return (
    <div className="landing-feature-card" style={{ animationDelay: `${delay}ms` }}>
      <div className="landing-feature-icon">{icon}</div>
      <h3 className="landing-feature-title">{title}</h3>
      <p className="landing-feature-desc">{description}</p>
    </div>
  )
}

function DataFlowAnimation() {
  return (
    <svg viewBox="0 0 400 300" className="landing-data-svg">
      {/* Grid lines */}
      <defs>
        <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--landing-accent)" stopOpacity="0" />
          <stop offset="50%" stopColor="var(--landing-accent)" stopOpacity="0.8" />
          <stop offset="100%" stopColor="var(--landing-accent)" stopOpacity="0" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Animated data nodes */}
      <g className="landing-nodes">
        {/* Source nodes */}
        <circle cx="60" cy="80" r="8" className="landing-node node-1" />
        <circle cx="60" cy="150" r="8" className="landing-node node-2" />
        <circle cx="60" cy="220" r="8" className="landing-node node-3" />

        {/* Processing node */}
        <rect
          x="170"
          y="130"
          width="60"
          height="40"
          rx="4"
          className="landing-processor"
        />
        <text x="200" y="155" className="landing-processor-text">
          LLM
        </text>

        {/* Output nodes */}
        <circle cx="340" cy="100" r="6" className="landing-node node-4" />
        <circle cx="340" cy="150" r="6" className="landing-node node-5" />
        <circle cx="340" cy="200" r="6" className="landing-node node-6" />
      </g>

      {/* Flow lines */}
      <g className="landing-flow-lines">
        <path d="M68 80 Q120 80 170 140" className="landing-flow flow-1" />
        <path d="M68 150 L170 150" className="landing-flow flow-2" />
        <path d="M68 220 Q120 220 170 160" className="landing-flow flow-3" />

        <path d="M230 140 Q280 100 334 100" className="landing-flow flow-4" />
        <path d="M230 150 L334 150" className="landing-flow flow-5" />
        <path d="M230 160 Q280 200 334 200" className="landing-flow flow-6" />
      </g>

      {/* Data packets */}
      <g className="landing-packets">
        <circle r="3" className="landing-packet packet-1">
          <animateMotion
            dur="2s"
            repeatCount="indefinite"
            path="M68 80 Q120 80 170 140"
          />
        </circle>
        <circle r="3" className="landing-packet packet-2">
          <animateMotion
            dur="1.8s"
            repeatCount="indefinite"
            path="M68 150 L170 150"
          />
        </circle>
        <circle r="3" className="landing-packet packet-3">
          <animateMotion
            dur="2.2s"
            repeatCount="indefinite"
            path="M68 220 Q120 220 170 160"
          />
        </circle>
        <circle r="3" className="landing-packet packet-4">
          <animateMotion
            dur="1.5s"
            repeatCount="indefinite"
            begin="0.5s"
            path="M230 140 Q280 100 334 100"
          />
        </circle>
        <circle r="3" className="landing-packet packet-5">
          <animateMotion
            dur="1.3s"
            repeatCount="indefinite"
            begin="0.3s"
            path="M230 150 L334 150"
          />
        </circle>
        <circle r="3" className="landing-packet packet-6">
          <animateMotion
            dur="1.7s"
            repeatCount="indefinite"
            begin="0.7s"
            path="M230 160 Q280 200 334 200"
          />
        </circle>
      </g>

      {/* Labels */}
      <g className="landing-labels">
        <text x="60" y="50" className="landing-label">Data Sources</text>
        <text x="200" y="195" className="landing-label">Analysis</text>
        <text x="340" y="250" className="landing-label">Insights</text>
      </g>
    </svg>
  )
}
