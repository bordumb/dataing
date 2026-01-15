/**
 * Step timeline visualization with auto-advancing progress indicators.
 */

import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, Loader2 } from 'lucide-react'
import type { StepHistoryItem } from '@/lib/api/investigations'

const STEP_LABELS: Record<string, string> = {
  gather_context: 'Gather Context',
  check_patterns: 'Check Patterns',
  generate_hypotheses: 'Generate Hypotheses',
  generate_query: 'Generate Query',
  execute_query: 'Execute Query',
  interpret_evidence: 'Interpret Evidence',
  synthesize: 'Synthesize',
  complete: 'Complete',
  fail: 'Failed',
  cancelled: 'Cancelled',
}

interface StepTimelineProps {
  currentStep: string
  stepHistory: StepHistoryItem[]
  animated?: boolean
}

export function StepTimeline({ currentStep, stepHistory, animated = true }: StepTimelineProps) {
  const [animatingStep, setAnimatingStep] = useState<string | null>(null)

  // Animate when step changes
  useEffect(() => {
    if (animated && currentStep) {
      setAnimatingStep(currentStep)
      const timer = setTimeout(() => setAnimatingStep(null), 500)
      return () => clearTimeout(timer)
    }
  }, [currentStep, animated])

  // If no step history, fall back to basic display
  const steps = stepHistory.length > 0
    ? stepHistory
    : [
        { step: 'gather_context', completed: false, timestamp: null },
        { step: 'check_patterns', completed: false, timestamp: null },
        { step: 'generate_hypotheses', completed: false, timestamp: null },
        { step: 'generate_query', completed: false, timestamp: null },
        { step: 'execute_query', completed: false, timestamp: null },
        { step: 'interpret_evidence', completed: false, timestamp: null },
        { step: 'synthesize', completed: false, timestamp: null },
        { step: 'complete', completed: false, timestamp: null },
      ]

  return (
    <div className="flex flex-col gap-1">
      {steps.map((item, index) => {
        const isCurrent = item.step === currentStep
        // Treat terminal steps as completed when it's the current step
        const isTerminalStep = ['complete', 'fail', 'cancelled'].includes(item.step)
        const isCompleted = item.completed || (isTerminalStep && isCurrent)
        const isAnimating = animatingStep === item.step
        const label = STEP_LABELS[item.step] || item.step

        return (
          <div key={item.step} className="flex items-center gap-2">
            {/* Connector line */}
            {index > 0 && (
              <div className="ml-2.5 -mt-1 h-2 w-0.5 bg-border" />
            )}

            {/* Step indicator */}
            <div className="flex items-center gap-2">
              <div
                className={`
                  flex h-5 w-5 items-center justify-center rounded-full
                  transition-all duration-300
                  ${isAnimating ? 'scale-125' : 'scale-100'}
                  ${isCompleted
                    ? 'bg-green-500 text-white'
                    : isCurrent
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  }
                `}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : isCurrent ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Circle className="h-3 w-3" />
                )}
              </div>

              <span
                className={`
                  text-xs font-medium transition-colors
                  ${isCompleted
                    ? 'text-green-600 dark:text-green-400'
                    : isCurrent
                      ? 'text-primary'
                      : 'text-muted-foreground'
                  }
                `}
              >
                {label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
