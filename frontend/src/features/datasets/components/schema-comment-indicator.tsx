import { MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

interface SchemaCommentIndicatorProps {
  commentCount: number
  fieldName: string
  onClick: () => void
}

export function SchemaCommentIndicator({
  commentCount,
  fieldName,
  onClick,
}: SchemaCommentIndicatorProps) {
  const hasComments = commentCount > 0

  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn(
        'h-7 px-2 opacity-0 group-hover:opacity-100 transition-opacity',
        hasComments && 'opacity-100'
      )}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      title={hasComments ? `${commentCount} comment(s)` : 'Add comment'}
      aria-label={`Comments for ${fieldName}: ${hasComments ? `${commentCount} comment(s)` : 'No comments'}`}
    >
      <MessageSquare
        className={cn('h-4 w-4', hasComments ? 'fill-primary text-primary' : '')}
      />
      {hasComments && <span className="ml-1 text-xs">{commentCount}</span>}
    </Button>
  )
}
