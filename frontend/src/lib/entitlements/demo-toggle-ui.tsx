import type { Plan } from './types'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface DemoToggleProps {
  plan: Plan
  onPlanChange: (plan: Plan) => void
}

const PLAN_COLORS: Record<Plan, string> = {
  free: 'bg-gray-500',
  pro: 'bg-blue-500',
  enterprise: 'bg-purple-500',
}

const PLAN_LABELS: Record<Plan, string> = {
  free: 'Free',
  pro: 'Pro',
  enterprise: 'Enterprise',
}

/**
 * Demo toggle UI component for switching between plan tiers.
 * Only shown in development mode.
 *
 * Displays in bottom-right corner with:
 * - Current plan badge
 * - Dropdown to switch plans
 * - Keyboard shortcut hint
 */
export function DemoToggle({ plan, onPlanChange }: DemoToggleProps) {
  // Only show in development
  if (import.meta.env.PROD) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-lg border bg-background p-3 shadow-lg">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Demo Mode
          </span>
          <Badge variant="outline" className={`${PLAN_COLORS[plan]} text-white`}>
            {PLAN_LABELS[plan]}
          </Badge>
        </div>
        <span className="text-[10px] text-muted-foreground">
          Ctrl+Shift+P to cycle
        </span>
      </div>

      <Select value={plan} onValueChange={(value) => onPlanChange(value as Plan)}>
        <SelectTrigger className="w-[120px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="free">
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${PLAN_COLORS.free}`} />
              Free
            </div>
          </SelectItem>
          <SelectItem value="pro">
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${PLAN_COLORS.pro}`} />
              Pro
            </div>
          </SelectItem>
          <SelectItem value="enterprise">
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${PLAN_COLORS.enterprise}`} />
              Enterprise
            </div>
          </SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
