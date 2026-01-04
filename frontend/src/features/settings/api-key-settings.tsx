import * as React from 'react'
import { Plus, Copy, Eye, EyeOff, Trash2, Key } from 'lucide-react'
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

interface ApiKey {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

export function ApiKeySettings() {
  const [apiKeys, setApiKeys] = React.useState<ApiKey[]>([
    {
      id: '1',
      name: 'Production Key',
      prefix: 'sk_prod_xxxx',
      created_at: new Date().toISOString(),
      last_used_at: new Date().toISOString(),
    },
  ])
  const [showDialog, setShowDialog] = React.useState(false)
  const [newKeyName, setNewKeyName] = React.useState('')
  const [generatedKey, setGeneratedKey] = React.useState<string | null>(null)
  const [showKey, setShowKey] = React.useState(false)

  const generateApiKey = () => {
    // Simulate API key generation
    const key = `sk_live_${Math.random().toString(36).substring(2, 15)}${Math.random().toString(36).substring(2, 15)}`
    setGeneratedKey(key)
    setApiKeys([
      ...apiKeys,
      {
        id: Date.now().toString(),
        name: newKeyName,
        prefix: key.substring(0, 12) + 'xxxx',
        created_at: new Date().toISOString(),
        last_used_at: null,
      },
    ])
  }

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const closeDialog = () => {
    setShowDialog(false)
    setNewKeyName('')
    setGeneratedKey(null)
    setShowKey(false)
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>API Keys</CardTitle>
          <CardDescription>
            Manage API keys for programmatic access to the Dataing API.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {apiKeys.length === 0 ? (
            <EmptyState
              icon={Key}
              title="No API keys"
              description="Create an API key to access the Dataing API."
              action={
                <Button onClick={() => setShowDialog(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create API Key
                </Button>
              }
            />
          ) : (
            <>
              <div className="space-y-4">
                {apiKeys.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between p-4 border rounded-lg"
                  >
                    <div>
                      <p className="font-medium">{key.name}</p>
                      <p className="text-sm font-mono text-muted-foreground">
                        {key.prefix}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Created: {new Date(key.created_at).toLocaleDateString()}
                        {key.last_used_at && (
                          <> | Last used: {new Date(key.last_used_at).toLocaleDateString()}</>
                        )}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setApiKeys(apiKeys.filter((k) => k.id !== key.id))
                      }
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button onClick={() => setShowDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create API Key
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={closeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {generatedKey ? 'API Key Created' : 'Create API Key'}
            </DialogTitle>
            <DialogDescription>
              {generatedKey
                ? 'Make sure to copy your API key now. You won\'t be able to see it again!'
                : 'Enter a name for your new API key.'}
            </DialogDescription>
          </DialogHeader>

          {generatedKey ? (
            <div className="space-y-4">
              <div className="p-4 bg-muted rounded-lg font-mono text-sm break-all flex items-center justify-between gap-2">
                <span>{showKey ? generatedKey : '•'.repeat(48)}</span>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowKey(!showKey)}
                  >
                    {showKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => copyToClipboard(generatedKey)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={closeDialog}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                generateApiKey()
              }}
              className="space-y-4"
            >
              <div className="grid gap-2">
                <Label htmlFor="key-name">Name</Label>
                <Input
                  id="key-name"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Production Key"
                  required
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!newKeyName}>
                  Create
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
