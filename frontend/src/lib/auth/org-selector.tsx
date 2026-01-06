/**
 * IMPORTANT: Organization selector for multi-tenant support.
 * DO NOT REMOVE - This component is critical for users with multiple org memberships.
 *
 * This component requires JWT authentication to function.
 * In API key auth mode, it will render nothing (returns null).
 */

import * as React from 'react'
import { Check, ChevronsUpDown, Building2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

import { getUserOrgs } from './api'
import type { OrgMembership } from './types'

// Safe hook to check if JWT auth is available
function useJwtAuthSafe() {
  // Try to get the context, return null if not available
  const [authState, setAuthState] = React.useState<{
    org: { id: string; name: string } | null
    accessToken: string | null
    switchOrg: ((orgId: string, orgName?: string, orgSlug?: string) => Promise<void>) | null
  } | null>(null)

  React.useEffect(() => {
    // Check if JWT auth data is in localStorage (indicating JWT auth mode)
    const accessToken = localStorage.getItem('dataing_access_token')
    const orgJson = localStorage.getItem('dataing_org')

    if (accessToken && orgJson) {
      try {
        const org = JSON.parse(orgJson)
        setAuthState({
          org,
          accessToken,
          switchOrg: null, // Cannot switch in safe mode
        })
      } catch {
        setAuthState(null)
      }
    }
  }, [])

  return authState
}

export function OrgSelector() {
  // Use safe hook that doesn't throw if JWT context is missing
  const authState = useJwtAuthSafe()
  const [open, setOpen] = React.useState(false)
  const [orgs, setOrgs] = React.useState<OrgMembership[]>([])
  const [loading, setLoading] = React.useState(true)

  // Extract values from authState (may be null in API key auth mode)
  const org = authState?.org
  const accessToken = authState?.accessToken

  // Fetch organizations on mount (when authenticated with JWT)
  React.useEffect(() => {
    if (!accessToken) {
      setLoading(false)
      return
    }

    setLoading(true)
    getUserOrgs(accessToken)
      .then(setOrgs)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [accessToken])

  // Don't render in API key auth mode (no JWT context)
  // or while loading, or if only one org
  if (!authState || loading || orgs.length <= 1) {
    return null
  }

  // Note: Org switching is disabled in safe mode (would need full JWT context)
  // This component shows the current org but switching requires JWT auth provider

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
          disabled={true} // Disabled in safe mode - full JWT context needed for switching
        >
          <Building2 className="mr-2 h-4 w-4 shrink-0" />
          <span className="truncate flex-1 text-left">
            {org?.name ?? 'Select org...'}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[200px] p-0">
        <Command>
          <CommandList>
            <CommandEmpty>No organizations found.</CommandEmpty>
            <CommandGroup>
              {orgs.map((membership) => (
                <CommandItem
                  key={membership.org_id}
                  value={membership.org_id}
                  disabled={true}
                >
                  <Check
                    className={cn(
                      'mr-2 h-4 w-4',
                      org?.id === membership.org_id
                        ? 'opacity-100'
                        : 'opacity-0'
                    )}
                  />
                  <div className="flex flex-col">
                    <span>{membership.org_name}</span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {membership.role}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
