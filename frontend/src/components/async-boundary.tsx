import { ReactNode } from 'react'
import { UseQueryResult } from '@tanstack/react-query'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface AsyncBoundaryProps<T> {
  query: UseQueryResult<T, Error>
  children: (data: T) => ReactNode
  loadingFallback?: ReactNode
  errorFallback?: ReactNode | ((error: Error, retry: () => void) => ReactNode)
}

function DefaultLoading() {
  return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  )
}

interface DefaultErrorProps {
  error: Error
  retry: () => void
}

function DefaultError({ error, retry }: DefaultErrorProps) {
  return (
    <Card>
      <CardContent className="py-8 text-center">
        <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-4" />
        <p className="text-muted-foreground mb-4">
          {error.message || 'An error occurred while loading data'}
        </p>
        <Button onClick={retry} variant="outline">
          <RefreshCw className="h-4 w-4 mr-2" />
          Try Again
        </Button>
      </CardContent>
    </Card>
  )
}

export function AsyncBoundary<T>({
  query,
  children,
  loadingFallback,
  errorFallback,
}: AsyncBoundaryProps<T>) {
  const { data, isLoading, error, refetch } = query

  if (isLoading) {
    return <>{loadingFallback ?? <DefaultLoading />}</>
  }

  if (error) {
    if (typeof errorFallback === 'function') {
      return <>{errorFallback(error, () => refetch())}</>
    }
    return <>{errorFallback ?? <DefaultError error={error} retry={() => refetch()} />}</>
  }

  if (data === undefined || data === null) {
    return null
  }

  return <>{children(data)}</>
}

// Simplified version for common use cases
interface SimpleAsyncBoundaryProps<T> {
  query: UseQueryResult<T, Error>
  children: (data: T) => ReactNode
  emptyMessage?: string
}

export function SimpleAsyncBoundary<T>({
  query,
  children,
  emptyMessage = 'No data found',
}: SimpleAsyncBoundaryProps<T>) {
  const { data, isLoading, error, refetch } = query

  if (isLoading) {
    return <DefaultLoading />
  }

  if (error) {
    return <DefaultError error={error} retry={() => refetch()} />
  }

  if (!data || (Array.isArray(data) && data.length === 0)) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          {emptyMessage}
        </CardContent>
      </Card>
    )
  }

  return <>{children(data)}</>
}
