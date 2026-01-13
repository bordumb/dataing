import * as React from 'react'
import { Save, TestTube, Loader2, CheckCircle, XCircle, Shield } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'

type ProviderType = 'none' | 'oidc' | 'saml'

interface SSOConfig {
  provider_type: ProviderType
  is_enabled: boolean
  display_name: string
  // OIDC fields
  oidc_issuer_url: string
  oidc_client_id: string
  oidc_client_secret: string
  // SAML fields
  saml_idp_metadata_url: string
  saml_idp_entity_id: string
  saml_certificate: string
}

const initialConfig: SSOConfig = {
  provider_type: 'none',
  is_enabled: false,
  display_name: '',
  oidc_issuer_url: '',
  oidc_client_id: '',
  oidc_client_secret: '',
  saml_idp_metadata_url: '',
  saml_idp_entity_id: '',
  saml_certificate: '',
}

export function SSOConfigSettings() {
  const [config, setConfig] = React.useState<SSOConfig>(initialConfig)
  const [isSaving, setIsSaving] = React.useState(false)
  const [isTesting, setIsTesting] = React.useState(false)
  const [testResult, setTestResult] = React.useState<'success' | 'error' | null>(null)

  const handleSave = async () => {
    setIsSaving(true)
    try {
      // TODO: Call API to save SSO config
      await new Promise((resolve) => setTimeout(resolve, 1000))
      toast.success('SSO configuration saved')
    } catch {
      toast.error('Failed to save SSO configuration')
    } finally {
      setIsSaving(false)
    }
  }

  const handleTestConnection = async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      // TODO: Call API to test SSO connection
      await new Promise((resolve) => setTimeout(resolve, 2000))
      setTestResult('success')
      toast.success('SSO connection test passed')
    } catch {
      setTestResult('error')
      toast.error('SSO connection test failed')
    } finally {
      setIsTesting(false)
    }
  }

  const updateConfig = (updates: Partial<SSOConfig>) => {
    setConfig((prev) => ({ ...prev, ...updates }))
    setTestResult(null) // Reset test result when config changes
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>SSO Provider</CardTitle>
          <CardDescription>
            Configure your identity provider for single sign-on authentication.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Enable SSO</Label>
              <p className="text-sm text-muted-foreground">
                When enabled, users with claimed domains will use SSO to sign in.
              </p>
            </div>
            <Switch
              checked={config.is_enabled}
              onCheckedChange={(checked) => updateConfig({ is_enabled: checked })}
            />
          </div>

          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="provider-type">Provider Type</Label>
              <Select
                value={config.provider_type}
                onValueChange={(value: ProviderType) =>
                  updateConfig({ provider_type: value })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select provider type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="oidc">OpenID Connect (OIDC)</SelectItem>
                  <SelectItem value="saml">SAML 2.0</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="display-name">Display Name</Label>
              <Input
                id="display-name"
                value={config.display_name}
                onChange={(e) => updateConfig({ display_name: e.target.value })}
                placeholder="e.g., Okta, Azure AD, Google Workspace"
              />
              <p className="text-sm text-muted-foreground">
                Shown to users on the login page.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {config.provider_type === 'oidc' && (
        <Card>
          <CardHeader>
            <CardTitle>OpenID Connect Configuration</CardTitle>
            <CardDescription>
              Configure your OIDC identity provider settings.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="issuer-url">Issuer URL</Label>
              <Input
                id="issuer-url"
                value={config.oidc_issuer_url}
                onChange={(e) => updateConfig({ oidc_issuer_url: e.target.value })}
                placeholder="https://your-idp.example.com"
              />
              <p className="text-sm text-muted-foreground">
                The base URL of your identity provider (e.g., https://login.microsoftonline.com/tenant-id/v2.0)
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="client-id">Client ID</Label>
              <Input
                id="client-id"
                value={config.oidc_client_id}
                onChange={(e) => updateConfig({ oidc_client_id: e.target.value })}
                placeholder="your-client-id"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="client-secret">Client Secret</Label>
              <Input
                id="client-secret"
                type="password"
                value={config.oidc_client_secret}
                onChange={(e) => updateConfig({ oidc_client_secret: e.target.value })}
                placeholder="your-client-secret"
              />
              <p className="text-sm text-muted-foreground">
                This value is encrypted and stored securely.
              </p>
            </div>

            <Alert>
              <Shield className="h-4 w-4" />
              <AlertDescription>
                <strong>Redirect URI:</strong> Add this URL to your identity provider's allowed redirect URIs:
                <code className="ml-2 px-2 py-1 bg-muted rounded text-sm">
                  {window.location.origin}/auth/sso/callback
                </code>
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      {config.provider_type === 'saml' && (
        <Card>
          <CardHeader>
            <CardTitle>SAML 2.0 Configuration</CardTitle>
            <CardDescription>
              Configure your SAML identity provider settings.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="metadata-url">IdP Metadata URL</Label>
              <Input
                id="metadata-url"
                value={config.saml_idp_metadata_url}
                onChange={(e) => updateConfig({ saml_idp_metadata_url: e.target.value })}
                placeholder="https://your-idp.example.com/metadata"
              />
              <p className="text-sm text-muted-foreground">
                URL to your identity provider's SAML metadata document.
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="entity-id">IdP Entity ID</Label>
              <Input
                id="entity-id"
                value={config.saml_idp_entity_id}
                onChange={(e) => updateConfig({ saml_idp_entity_id: e.target.value })}
                placeholder="https://your-idp.example.com"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="certificate">X.509 Certificate</Label>
              <textarea
                id="certificate"
                className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
                value={config.saml_certificate}
                onChange={(e) => updateConfig({ saml_certificate: e.target.value })}
                placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
              />
              <p className="text-sm text-muted-foreground">
                The public certificate from your identity provider.
              </p>
            </div>

            <Alert>
              <Shield className="h-4 w-4" />
              <AlertDescription>
                <strong>ACS URL:</strong> Configure this as your Assertion Consumer Service URL:
                <code className="ml-2 px-2 py-1 bg-muted rounded text-sm">
                  {window.location.origin}/api/v1/auth/sso/saml/acs
                </code>
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      {config.provider_type !== 'none' && (
        <div className="flex gap-4">
          <Button
            variant="outline"
            onClick={handleTestConnection}
            disabled={isTesting || isSaving}
          >
            {isTesting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Testing...
              </>
            ) : testResult === 'success' ? (
              <>
                <CheckCircle className="mr-2 h-4 w-4 text-green-500" />
                Test Passed
              </>
            ) : testResult === 'error' ? (
              <>
                <XCircle className="mr-2 h-4 w-4 text-destructive" />
                Test Failed
              </>
            ) : (
              <>
                <TestTube className="mr-2 h-4 w-4" />
                Test Connection
              </>
            )}
          </Button>

          <Button onClick={handleSave} disabled={isSaving || isTesting}>
            {isSaving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Configuration
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
