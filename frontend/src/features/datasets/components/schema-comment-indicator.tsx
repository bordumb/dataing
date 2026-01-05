'use client'

import { MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { useSchemaComments } from '@/lib/api/schema-comments'

interface SchemaCommentIndicatorProps {
  datasetId: string
  fieldName: string
  onClick: () => void
}

export function SchemaCommentIndicator({
  datasetId,
  fieldName,
  onClick,
}: SchemaCommentIndicatorProps) {
  const { data: comments = [] } = useSchemaComments(datasetId, fieldName)
  const hasComments = comments.length > 0

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
      title={hasComments ? `${comments.length} comment(s)` : 'Add comment'}
    >
      <MessageSquare
        className={cn('h-4 w-4', hasComments ? 'fill-primary text-primary' : '')}
      />
      {hasComments && <span className="ml-1 text-xs">{comments.length}</span>}
    </Button>
  )
}
