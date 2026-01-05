import * as React from 'react'
import {
  Plus,
  Trash2,
  Globe,
  CheckCircle,
  Clock,
  XCircle,
  RefreshCw,
  Copy,
  Loader2,
} from 'lucide-react'
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
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/empty-state'
import { Alert, AlertDescription } from '@/components/ui/alert'

type VerificationStatus = 'pending' | 'verified' | 'failed'

interface DomainClaim {
  id: string
  domain: string
  verification_status: VerificationStatus
  verification_token: string
  dns_record: string
  created_at: string
  verified_at: string | null
}

export function DomainClaimsSettings() {
  const [domains, setDomains] = React.useState<DomainClaim[]>([])
  const [showAddDialog, setShowAddDialog] = React.useState(false)
  const [showVerifyDialog, setShowVerifyDialog] = React.useState(false)
  const [selectedDomain, setSelectedDomain] = React.useState<DomainClaim | null>(null)
  const [newDomain, setNewDomain] = React.useState('')
  const [isAdding, setIsAdding] = React.useState(false)
  const [isVerifying, setIsVerifying] = React.useState(false)

  const handleAddDomain = async () => {
    if (!newDomain) return

    setIsAdding(true)
    try {
      // TODO: Call API to add domain
      await new Promise((resolve) => setTimeout(resolve, 1000))

      const newClaim: DomainClaim = {
        id: Date.now().toString(),
        domain: newDomain.toLowerCase(),
        verification_status: 'pending',
        verification_token: `dataing-verify-${Math.random().toString(36).substring(2, 15)}`,
        dns_record: `_dataing-verification.${newDomain.toLowerCase()}`,
        created_at: new Date().toISOString(),
        verified_at: null,
      }

      setDomains([...domains, newClaim])
      setSelectedDomain(newClaim)
      setShowAddDialog(false)
      setShowVerifyDialog(true)
      setNewDomain('')
      toast.success('Domain added. Complete DNS verification to claim it.')
    } catch {
      toast.error('Failed to add domain')
    } finally {
      setIsAdding(false)
    }
  }

  const handleVerifyDomain = async (domain: DomainClaim) => {
    setIsVerifying(true)
    try {
      // TODO: Call API to verify domain
      await new Promise((resolve) => setTimeout(resolve, 2000))

      // Simulate verification result (random for demo)
      const success = Math.random() > 0.3

      setDomains(
        domains.map((d) =>
          d.id === domain.id
            ? {
                ...d,
                verification_status: success ? 'verified' : 'failed',
                verified_at: success ? new Date().toISOString() : null,
              }
            : d
        )
      )

      if (success) {
        toast.success(`Domain ${domain.domain} verified successfully`)
        setShowVerifyDialog(false)
      } else {
        toast.error('DNS verification failed. Please check your DNS records.')
      }
    } catch {
      toast.error('Failed to verify domain')
    } finally {
      setIsVerifying(false)
    }
  }

  const handleDeleteDomain = async (domain: DomainClaim) => {
    try {
      // TODO: Call API to delete domain
      setDomains(domains.filter((d) => d.id !== domain.id))
      toast.success('Domain removed')
    } catch {
      toast.error('Failed to remove domain')
    }
  }

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const getStatusBadge = (status: VerificationStatus) => {
    switch (status) {
      case 'verified':
        return (
          <Badge variant="default" className="bg-green-500">
            <CheckCircle className="mr-1 h-3 w-3" />
            Verified
          </Badge>
        )
      case 'pending':
        return (
          <Badge variant="secondary">
            <Clock className="mr-1 h-3 w-3" />
            Pending Verification
          </Badge>
        )
      case 'failed':
        return (
          <Badge variant="destructive">
            <XCircle className="mr-1 h-3 w-3" />
            Verification Failed
          </Badge>
        )
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Domain Claims</CardTitle>
          <CardDescription>
            Claim email domains to enable SSO for users with those email addresses.
            Domain ownership is verified via DNS TXT records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {domains.length === 0 ? (
            <EmptyState
              icon={Globe}
              title="No domains claimed"
              description="Add a domain to enable SSO for users with that email domain."
              action={
                <Button onClick={() => setShowAddDialog(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Add Domain
                </Button>
              }
            />
          ) : (
            <>
              <div className="space-y-4">
                {domains.map((domain) => (
                  <div
                    key={domain.id}
                    className="flex items-center justify-between p-4 border rounded-lg"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">{domain.domain}</span>
                        {getStatusBadge(domain.verification_status)}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Added: {new Date(domain.created_at).toLocaleDateString()}
                        {domain.verified_at && (
                          <> | Verified: {new Date(domain.verified_at).toLocaleDateString()}</>
                        )}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      {domain.verification_status !== 'verified' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSelectedDomain(domain)
                            setShowVerifyDialog(true)
                          }}
                        >
                          <RefreshCw className="mr-2 h-4 w-4" />
                          Verify
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteDomain(domain)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <Button onClick={() => setShowAddDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Domain
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {/* Add Domain Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Domain</DialogTitle>
            <DialogDescription>
              Enter the email domain you want to claim for SSO.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleAddDomain()
            }}
            className="space-y-4"
          >
            <div className="grid gap-2">
              <Label htmlFor="domain">Domain</Label>
              <Input
                id="domain"
                value={newDomain}
                onChange={(e) => setNewDomain(e.target.value)}
                placeholder="example.com"
                required
              />
              <p className="text-sm text-muted-foreground">
                Enter just the domain (e.g., "acme.com", not "user@acme.com")
              </p>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowAddDialog(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!newDomain || isAdding}>
                {isAdding ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Adding...
                  </>
                ) : (
                  'Add Domain'
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Verify Domain Dialog */}
      <Dialog open={showVerifyDialog} onOpenChange={setShowVerifyDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Verify Domain Ownership</DialogTitle>
            <DialogDescription>
              Add a DNS TXT record to verify you own {selectedDomain?.domain}.
            </DialogDescription>
          </DialogHeader>
          {selectedDomain && (
            <div className="space-y-4">
              <Alert>
                <AlertDescription className="space-y-3">
                  <p>Add the following TXT record to your DNS configuration:</p>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-2 bg-muted rounded">
                      <div>
                        <span className="text-xs text-muted-foreground">Name/Host:</span>
                        <p className="font-mono text-sm">{selectedDomain.dns_record}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => copyToClipboard(selectedDomain.dns_record)}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="flex items-center justify-between p-2 bg-muted rounded">
                      <div>
                        <span className="text-xs text-muted-foreground">Value:</span>
                        <p className="font-mono text-sm break-all">
                          {selectedDomain.verification_token}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => copyToClipboard(selectedDomain.verification_token)}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="flex items-center justify-between p-2 bg-muted rounded">
                      <div>
                        <span className="text-xs text-muted-foreground">Type:</span>
                        <p className="font-mono text-sm">TXT</p>
                      </div>
                    </div>
                  </div>

                  <p className="text-sm text-muted-foreground">
                    DNS changes may take up to 24 hours to propagate.
                  </p>
                </AlertDescription>
              </Alert>

              <DialogFooter>
                <Button variant="outline" onClick={() => setShowVerifyDialog(false)}>
                  I'll do this later
                </Button>
                <Button
                  onClick={() => handleVerifyDomain(selectedDomain)}
                  disabled={isVerifying}
                >
                  {isVerifying ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Checking DNS...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Verify Now
                    </>
                  )}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
