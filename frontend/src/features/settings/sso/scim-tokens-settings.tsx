import * as React from 'react'
import { Plus, Copy, Eye, EyeOff, Trash2, Key, Loader2, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface SCIMToken {
  id: string
  description: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

export function SCIMTokensSettings() {
  const [tokens, setTokens] = React.useState<SCIMToken[]>([])
  const [showDialog, setShowDialog] = React.useState(false)
  const [newDescription, setNewDescription] = React.useState('')
  const [generatedToken, setGeneratedToken] = React.useState<string | null>(null)
  const [showToken, setShowToken] = React.useState(false)
  const [isGenerating, setIsGenerating] = React.useState(false)

  const generateToken = async () => {
    setIsGenerating(true)
    try {
      // TODO: Call API to generate SCIM token
      await new Promise((resolve) => setTimeout(resolve, 1000))

      // Simulate token generation
      const token = `scim_${Math.random().toString(36).substring(2)}${Math.random().toString(36).substring(2)}${Math.random().toString(36).substring(2)}`
      setGeneratedToken(token)

      setTokens([
        ...tokens,
        {
          id: Date.now().toString(),
          description: newDescription,
          prefix: token.substring(0, 12) + '...',
          created_at: new Date().toISOString(),
          last_used_at: null,
        },
      ])
    } catch {
      toast.error('Failed to generate SCIM token')
    } finally {
      setIsGenerating(false)
    }
  }

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const closeDialog = () => {
    setShowDialog(false)
    setNewDescription('')
    setGeneratedToken(null)
    setShowToken(false)
  }

  const handleDeleteToken = async (token: SCIMToken) => {
    try {
      // TODO: Call API to revoke token
      setTokens(tokens.filter((t) => t.id !== token.id))
      toast.success('SCIM token revoked')
    } catch {
      toast.error('Failed to revoke token')
    }
  }

  const scimBaseUrl = `${window.location.origin}/api/scim/v2`

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>SCIM Provisioning</CardTitle>
          <CardDescription>
            Configure SCIM 2.0 tokens to enable automatic user provisioning from your identity provider.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <Alert>
            <AlertDescription className="space-y-2">
              <p>
                <strong>SCIM Base URL:</strong>
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-2 py-1 bg-muted rounded text-sm font-mono break-all">
                  {scimBaseUrl}
                </code>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => copyToClipboard(scimBaseUrl)}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">
                Use this URL when configuring SCIM in your identity provider.
              </p>
            </AlertDescription>
          </Alert>

          {tokens.length === 0 ? (
            <EmptyState
              icon={Key}
              title="No SCIM tokens"
              description="Create a SCIM token to enable automatic user provisioning."
              action={
                <Button onClick={() => setShowDialog(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create SCIM Token
                </Button>
              }
            />
          ) : (
            <>
              <div className="space-y-4">
                {tokens.map((token) => (
                  <div
                    key={token.id}
                    className="flex items-center justify-between p-4 border rounded-lg"
                  >
                    <div>
                      <p className="font-medium">{token.description}</p>
                      <p className="text-sm font-mono text-muted-foreground">
                        {token.prefix}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Created: {new Date(token.created_at).toLocaleDateString()}
                        {token.last_used_at && (
                          <> | Last used: {new Date(token.last_used_at).toLocaleDateString()}</>
                        )}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteToken(token)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button onClick={() => setShowDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create SCIM Token
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>SCIM Documentation</CardTitle>
          <CardDescription>
            Learn how to configure SCIM with your identity provider.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            <a
              href="https://help.okta.com/en-us/content/topics/apps/apps_app_integration_wizard_scim.htm"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-4 border rounded-lg hover:bg-muted transition-colors"
            >
              <div className="flex-1">
                <p className="font-medium">Okta</p>
                <p className="text-sm text-muted-foreground">
                  Configure SCIM provisioning in Okta
                </p>
              </div>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
            <a
              href="https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-4 border rounded-lg hover:bg-muted transition-colors"
            >
              <div className="flex-1">
                <p className="font-medium">Azure AD / Entra ID</p>
                <p className="text-sm text-muted-foreground">
                  Configure SCIM in Microsoft Entra ID
                </p>
              </div>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
            <a
              href="https://support.google.com/a/answer/6126218"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-4 border rounded-lg hover:bg-muted transition-colors"
            >
              <div className="flex-1">
                <p className="font-medium">Google Workspace</p>
                <p className="text-sm text-muted-foreground">
                  Configure user provisioning in Google
                </p>
              </div>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
            <a
              href="https://www.onelogin.com/learn/scim"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-4 border rounded-lg hover:bg-muted transition-colors"
            >
              <div className="flex-1">
                <p className="font-medium">OneLogin</p>
                <p className="text-sm text-muted-foreground">
                  Configure SCIM provisioning in OneLogin
                </p>
              </div>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
          </div>
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={closeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {generatedToken ? 'SCIM Token Created' : 'Create SCIM Token'}
            </DialogTitle>
            <DialogDescription>
              {generatedToken
                ? "Copy your SCIM token now. You won't be able to see it again!"
                : 'Create a bearer token for SCIM provisioning.'}
            </DialogDescription>
          </DialogHeader>

          {generatedToken ? (
            <div className="space-y-4">
              <div className="p-4 bg-muted rounded-lg font-mono text-sm break-all flex items-center justify-between gap-2">
                <span className="flex-1">{showToken ? generatedToken : '•'.repeat(48)}</span>
                <div className="flex gap-1 flex-shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowToken(!showToken)}
                  >
                    {showToken ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => copyToClipboard(generatedToken)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <Alert>
                <AlertDescription>
                  Use this token as the Bearer token in your identity provider's SCIM configuration.
                  Example header: <code>Authorization: Bearer {generatedToken.substring(0, 12)}...</code>
                </AlertDescription>
              </Alert>
              <DialogFooter>
                <Button onClick={closeDialog}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                generateToken()
              }}
              className="space-y-4"
            >
              <div className="grid gap-2">
                <Label htmlFor="token-description">Description</Label>
                <Input
                  id="token-description"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="e.g., Okta SCIM, Azure AD Provisioning"
                  required
                />
                <p className="text-sm text-muted-foreground">
                  A description to help you identify this token.
                </p>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!newDescription || isGenerating}>
                  {isGenerating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    'Create Token'
                  )}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
