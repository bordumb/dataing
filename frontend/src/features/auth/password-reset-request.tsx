/**
 * Password reset request page.
 *
 * Allows users to request a password reset. Supports different recovery methods:
 * - email: Sends reset link via email
 * - console: Prints reset link to server console (demo/dev mode)
 * - admin_contact: Shows admin contact info (SSO orgs)
 */

import * as React from 'react'
import { Link } from 'react-router-dom'
import { Search, Mail, ArrowLeft, CheckCircle, Terminal, UserCog } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card'
import { Alert, AlertDescription } from '@/components/ui/alert'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface RecoveryMethod {
  type: string
  message: string
  action_url?: string | null
  admin_email?: string | null
}

export function PasswordResetRequest() {
  const [email, setEmail] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [isSuccess, setIsSuccess] = React.useState(false)
  const [recoveryType, setRecoveryType] = React.useState<string>('email')
  const [adminEmail, setAdminEmail] = React.useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      // First, get the recovery method to know what type of message to show
      const methodResponse = await fetch(`${API_URL}/api/v1/auth/password-reset/recovery-method`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })

      if (methodResponse.ok) {
        const method: RecoveryMethod = await methodResponse.json()
        setRecoveryType(method.type)
        setAdminEmail(method.admin_email ?? null)
      }

      // Then request the password reset
      const response = await fetch(`${API_URL}/api/v1/auth/password-reset/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to request password reset')
      }

      setIsSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsLoading(false)
    }
  }

  // Render different success messages based on recovery type
  const renderSuccessMessage = () => {
    switch (recoveryType) {
      case 'console':
        return (
          <div className="space-y-4">
            <Alert className="bg-blue-50 border-blue-200">
              <Terminal className="h-4 w-4 text-blue-600" />
              <AlertDescription className="text-blue-800">
                <strong>Demo Mode:</strong> Check the server console for your
                password reset link. The link will be printed in the terminal
                where the backend is running.
              </AlertDescription>
            </Alert>
            <Link
              to="/jwt-login"
              className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to login
            </Link>
          </div>
        )

      case 'admin_contact':
        return (
          <div className="space-y-4">
            <Alert className="bg-amber-50 border-amber-200">
              <UserCog className="h-4 w-4 text-amber-600" />
              <AlertDescription className="text-amber-800">
                Your organization uses single sign-on (SSO). Please contact your
                administrator to reset your password.
                {adminEmail && (
                  <p className="mt-2">
                    <strong>Admin contact:</strong>{' '}
                    <a
                      href={`mailto:${adminEmail}`}
                      className="text-primary hover:underline"
                    >
                      {adminEmail}
                    </a>
                  </p>
                )}
              </AlertDescription>
            </Alert>
            <Link
              to="/jwt-login"
              className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to login
            </Link>
          </div>
        )

      case 'email':
      default:
        return (
          <div className="space-y-4">
            <Alert className="bg-green-50 border-green-200">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800">
                If an account with that email exists, we've sent a password
                reset link. Please check your inbox.
              </AlertDescription>
            </Alert>
            <p className="text-sm text-muted-foreground text-center">
              Didn't receive the email? Check your spam folder or{' '}
              <button
                type="button"
                onClick={() => {
                  setIsSuccess(false)
                  setEmail('')
                }}
                className="text-primary hover:underline"
              >
                try again
              </button>
              .
            </p>
            <Link
              to="/jwt-login"
              className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to login
            </Link>
          </div>
        )
    }
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
          <CardTitle className="text-2xl font-bold">Reset Password</CardTitle>
          <CardDescription>
            {isSuccess
              ? recoveryType === 'console'
                ? 'Check the server console'
                : recoveryType === 'admin_contact'
                  ? 'Contact your administrator'
                  : 'Check your email for reset instructions'
              : "Enter your email and we'll help you reset your password"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isSuccess ? (
            renderSuccessMessage()
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9"
                    required
                    autoFocus
                  />
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button
                type="submit"
                className="w-full"
                disabled={isLoading || !email}
              >
                {isLoading ? 'Sending...' : 'Reset Password'}
              </Button>

              <Link
                to="/jwt-login"
                className="flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to login
              </Link>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
