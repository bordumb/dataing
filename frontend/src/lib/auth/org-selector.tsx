/**
 * Organization selector for users with multiple org memberships.
 */

import * as React from 'react'
import { Check, ChevronsUpDown, Building2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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
import { useJwtAuth } from './jwt-context'
import type { OrgMembership } from './types'

export function OrgSelector() {
  const { organization, accessToken, switchOrg } = useJwtAuth()
  const [open, setOpen] = React.useState(false)
  const [orgs, setOrgs] = React.useState<OrgMembership[]>([])
  const [loading, setLoading] = React.useState(false)
  const [switching, setSwitching] = React.useState(false)

  // Fetch organizations when popover opens
  React.useEffect(() => {
    if (open && accessToken && orgs.length === 0) {
      setLoading(true)
      getUserOrgs(accessToken)
        .then(setOrgs)
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [open, accessToken, orgs.length])

  const handleSelect = async (orgId: string) => {
    if (orgId === organization?.id) {
      setOpen(false)
      return
    }

    setSwitching(true)
    try {
      await switchOrg(orgId)
      // Reload to apply new org context
      window.location.reload()
    } catch (error) {
      console.error('Failed to switch org:', error)
    } finally {
      setSwitching(false)
      setOpen(false)
    }
  }

  // Don't show if only one org
  if (orgs.length <= 1 && !open) {
    return null
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-[200px] justify-between"
          disabled={switching}
        >
          <Building2 className="mr-2 h-4 w-4 shrink-0" />
          <span className="truncate">{organization?.name ?? 'Select org...'}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[200px] p-0">
        <Command>
          <CommandList>
            {loading ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Loading...
              </div>
            ) : (
              <>
                <CommandEmpty>No organizations found.</CommandEmpty>
                <CommandGroup>
                  {orgs.map((membership) => (
                    <CommandItem
                      key={membership.org.id}
                      value={membership.org.id}
                      onSelect={() => handleSelect(membership.org.id)}
                    >
                      <Check
                        className={cn(
                          'mr-2 h-4 w-4',
                          organization?.id === membership.org.id
                            ? 'opacity-100'
                            : 'opacity-0'
                        )}
                      />
                      <div className="flex flex-col">
                        <span>{membership.org.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {membership.role}
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
