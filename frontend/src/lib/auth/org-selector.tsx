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
  const { org, accessToken, switchOrg } = useJwtAuth()
  const [open, setOpen] = React.useState(false)
  const [orgs, setOrgs] = React.useState<OrgMembership[]>([])
  const [loading, setLoading] = React.useState(true)
  const [switching, setSwitching] = React.useState(false)

  // Fetch organizations on mount (when authenticated)
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

  const handleSelect = async (membership: OrgMembership) => {
    if (membership.org.id === org?.id) {
      setOpen(false)
      return
    }

    setSwitching(true)
    try {
      await switchOrg(membership.org.id, membership.org.name, membership.org.slug)
      setOpen(false)
    } catch (error) {
      console.error('Failed to switch org:', error)
    } finally {
      setSwitching(false)
    }
  }

  // Don't show while loading or if only one org
  if (loading || orgs.length <= 1) {
    return null
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
          disabled={switching}
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
                  key={membership.org.id}
                  value={membership.org.id}
                  onSelect={() => handleSelect(membership)}
                >
                  <Check
                    className={cn(
                      'mr-2 h-4 w-4',
                      org?.id === membership.org.id
                        ? 'opacity-100'
                        : 'opacity-0'
                    )}
                  />
                  <div className="flex flex-col">
                    <span>{membership.org.name}</span>
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
