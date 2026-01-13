import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/Button'
import { Progress } from '@/components/ui/progress'

export interface UpgradeError {
  error: 'feature_not_available' | 'limit_exceeded'
  feature: string
  message: string
  upgrade_url: string
  contact_sales: boolean
  limit?: number
  usage?: number
}

interface UpgradeRequiredModalProps {
  error: UpgradeError | null
  onClose: () => void
}

export function UpgradeRequiredModal({ error, onClose }: UpgradeRequiredModalProps) {
  if (!error) return null

  const isLimitError = error.error === 'limit_exceeded'
  const usagePercent =
    error.limit && error.usage !== undefined ? (error.usage / error.limit) * 100 : 0

  return (
    <Dialog open={!!error} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isLimitError ? 'Limit Reached' : 'Upgrade Required'}</DialogTitle>
          <DialogDescription>{error.message}</DialogDescription>
        </DialogHeader>

        {isLimitError && error.limit && error.usage !== undefined && (
          <div className="py-4">
            <div className="mb-2 flex justify-between text-sm">
              <span>Current usage</span>
              <span>
                {error.usage} / {error.limit}
              </span>
            </div>
            <Progress value={usagePercent} className="h-2" />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          {error.contact_sales ? (
            <Button asChild>
              <a href="mailto:sales@dataing.io?subject=Enterprise%20Upgrade">Contact Sales</a>
            </Button>
          ) : (
            <Button asChild>
              <a href={error.upgrade_url}>Upgrade Plan</a>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
