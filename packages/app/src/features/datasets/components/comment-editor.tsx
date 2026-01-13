'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/textarea'

interface CommentEditorProps {
  placeholder?: string
  submitLabel?: string
  onSubmit: (content: string) => void
  onCancel?: () => void
  isSubmitting?: boolean
  initialValue?: string
}

export function CommentEditor({
  placeholder = 'Write a comment... (Markdown supported)',
  submitLabel = 'Submit',
  onSubmit,
  onCancel,
  isSubmitting = false,
  initialValue = '',
}: CommentEditorProps) {
  const [content, setContent] = useState(initialValue)

  const handleSubmit = () => {
    if (content.trim()) {
      onSubmit(content.trim())
      setContent('')
    }
  }

  return (
    <div className="space-y-2">
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={placeholder}
        className="min-h-[100px] resize-y"
        disabled={isSubmitting}
      />
      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!content.trim() || isSubmitting}
        >
          {isSubmitting ? 'Submitting...' : submitLabel}
        </Button>
      </div>
    </div>
  )
}
