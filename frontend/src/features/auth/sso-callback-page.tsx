import * as React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, Loader2, AlertCircle } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useAuth } from '@/lib/auth/context'

type CallbackStatus = 'processing' | 'success' | 'error'

export function SSOCallbackPage() {
  const [status, setStatus] = React.useState<CallbackStatus>('processing')
  const [error, setError] = React.useState<string | null>(null)

  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  React.useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get('code')
      const state = searchParams.get('state')
      const errorParam = searchParams.get('error')
      const errorDescription = searchParams.get('error_description')

      // Handle error from IdP
      if (errorParam) {
        setStatus('error')
        setError(errorDescription || `Authentication failed: ${errorParam}`)
        return
      }

      // Missing required params
      if (!code || !state) {
        setStatus('error')
        setError('Invalid callback: missing authorization code or state')
        return
      }

      try {
        // Exchange code for tokens via backend
        const response = await fetch('/api/v1/auth/sso/callback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code, state }),
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || 'Failed to complete authentication')
        }

        const data = await response.json()

        if (data.access_token) {
          setStatus('success')
          await login(data.access_token)

          // Redirect to dashboard after short delay
          setTimeout(() => {
            navigate('/', { replace: true })
          }, 1000)
        } else {
          throw new Error('No access token received')
        }
      } catch (err) {
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Authentication failed')
      }
    }

    handleCallback()
  }, [searchParams, login, navigate])

  const handleRetry = () => {
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Search className="h-6 w-6" />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">
            {status === 'processing' && 'Signing you in...'}
            {status === 'success' && 'Success!'}
            {status === 'error' && 'Authentication Failed'}
          </CardTitle>
          <CardDescription>
            {status === 'processing' && 'Please wait while we complete your sign in.'}
            {status === 'success' && 'Redirecting to dashboard...'}
            {status === 'error' && 'There was a problem signing you in.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {status === 'processing' && (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          )}

          {status === 'success' && (
            <div className="flex justify-center py-8">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-green-600">
                <svg
                  className="h-8 w-8"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-4">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                  <AlertCircle className="h-8 w-8" />
                </div>
              </div>

              {error && (
                <p className="text-center text-sm text-muted-foreground">
                  {error}
                </p>
              )}

              <Button
                onClick={handleRetry}
                className="w-full"
              >
                Try again
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
