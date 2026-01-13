import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VoteButtons } from './VoteButtons'

describe('VoteButtons', () => {
  describe('toggle behavior', () => {
    it('calls onVote(1) when clicking upvote with no current vote', async () => {
      const user = userEvent.setup()
      const onVote = vi.fn()
      const onRemoveVote = vi.fn()

      render(
        <VoteButtons
          upvotes={0}
          downvotes={0}
          userVote={null}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />
      )

      await user.click(screen.getByRole('button', { name: /upvote/i }))

      expect(onVote).toHaveBeenCalledWith(1)
      expect(onRemoveVote).not.toHaveBeenCalled()
    })

    it('calls onRemoveVote when clicking upvote while already upvoted', async () => {
      const user = userEvent.setup()
      const onVote = vi.fn()
      const onRemoveVote = vi.fn()

      render(
        <VoteButtons
          upvotes={1}
          downvotes={0}
          userVote={1}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />
      )

      await user.click(screen.getByRole('button', { name: /upvote/i }))

      expect(onRemoveVote).toHaveBeenCalled()
      expect(onVote).not.toHaveBeenCalled()
    })

    it('calls onVote(-1) when clicking downvote while upvoted', async () => {
      const user = userEvent.setup()
      const onVote = vi.fn()
      const onRemoveVote = vi.fn()

      render(
        <VoteButtons
          upvotes={1}
          downvotes={0}
          userVote={1}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />
      )

      await user.click(screen.getByRole('button', { name: /downvote/i }))

      expect(onVote).toHaveBeenCalledWith(-1)
      expect(onRemoveVote).not.toHaveBeenCalled()
    })

    it('calls onRemoveVote when clicking downvote while already downvoted', async () => {
      const user = userEvent.setup()
      const onVote = vi.fn()
      const onRemoveVote = vi.fn()

      render(
        <VoteButtons
          upvotes={0}
          downvotes={1}
          userVote={-1}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />
      )

      await user.click(screen.getByRole('button', { name: /downvote/i }))

      expect(onRemoveVote).toHaveBeenCalled()
      expect(onVote).not.toHaveBeenCalled()
    })

    it('calls onVote(1) when clicking upvote while downvoted', async () => {
      const user = userEvent.setup()
      const onVote = vi.fn()
      const onRemoveVote = vi.fn()

      render(
        <VoteButtons
          upvotes={0}
          downvotes={1}
          userVote={-1}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />
      )

      await user.click(screen.getByRole('button', { name: /upvote/i }))

      expect(onVote).toHaveBeenCalledWith(1)
      expect(onRemoveVote).not.toHaveBeenCalled()
    })
  })

  describe('display', () => {
    it('shows net vote count', () => {
      render(
        <VoteButtons
          upvotes={5}
          downvotes={2}
          userVote={null}
          onVote={vi.fn()}
          onRemoveVote={vi.fn()}
        />
      )

      expect(screen.getByText('3')).toBeInTheDocument()
    })

    it('highlights upvote button when user has upvoted', () => {
      render(
        <VoteButtons
          upvotes={1}
          downvotes={0}
          userVote={1}
          onVote={vi.fn()}
          onRemoveVote={vi.fn()}
        />
      )

      const upvoteButton = screen.getByRole('button', { name: /upvote/i })
      expect(upvoteButton).toHaveClass('text-green-600')
    })

    it('highlights downvote button when user has downvoted', () => {
      render(
        <VoteButtons
          upvotes={0}
          downvotes={1}
          userVote={-1}
          onVote={vi.fn()}
          onRemoveVote={vi.fn()}
        />
      )

      const downvoteButton = screen.getByRole('button', { name: /downvote/i })
      expect(downvoteButton).toHaveClass('text-red-600')
    })
  })
})
