/**
 * Demo role toggle for testing different permission levels.
 * Only visible in demo mode.
 */

import { Shield, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { OrgRole } from './types'

interface DemoRoleToggleProps {
  currentRole: OrgRole
  onRoleChange: (role: OrgRole) => void
}

const ROLE_DESCRIPTIONS: Record<OrgRole, string> = {
  viewer: 'Read-only access',
  member: 'Can create investigations',
  admin: 'Can manage team settings',
  owner: 'Full control + billing',
}

const ROLE_COLORS: Record<OrgRole, string> = {
  viewer: 'text-gray-500',
  member: 'text-blue-500',
  admin: 'text-amber-500',
  owner: 'text-purple-500',
}

export function DemoRoleToggle({ currentRole, onRoleChange }: DemoRoleToggleProps) {
  return (
    <div className="fixed bottom-4 left-4 z-50">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2 shadow-lg">
            <Shield className={`h-4 w-4 ${ROLE_COLORS[currentRole]}`} />
            <span className="capitalize">{currentRole}</span>
            <ChevronDown className="h-3 w-3 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Demo Role Switcher</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={currentRole}
            onValueChange={(v) => onRoleChange(v as OrgRole)}
          >
            {(['viewer', 'member', 'admin', 'owner'] as OrgRole[]).map((role) => (
              <DropdownMenuRadioItem key={role} value={role} className="cursor-pointer">
                <div className="flex flex-col">
                  <span className={`font-medium capitalize ${ROLE_COLORS[role]}`}>
                    {role}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {ROLE_DESCRIPTIONS[role]}
                  </span>
                </div>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
