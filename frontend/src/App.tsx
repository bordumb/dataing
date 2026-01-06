import { Routes, Route } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { Separator } from '@/components/ui/separator'
import { ModeToggle } from '@/components/mode-toggle'
import { ErrorBoundary, FeatureErrorBoundary } from '@/components/error-boundary'

// Pages
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { InvestigationList } from '@/features/investigation/InvestigationList'
import { InvestigationDetail } from '@/features/investigation/InvestigationDetail'
import { NewInvestigation } from '@/features/investigation/NewInvestigation'
import { DataSourcePage } from '@/features/datasources/datasource-page'
import { DatasetListPage, DatasetDetailPage } from '@/features/datasets'
import { SettingsPage } from '@/features/settings/settings-page'
import { UsagePage } from '@/features/usage/usage-page'
import { NotificationsPage } from '@/features/notifications'
import { AdminPage } from '@/features/admin'
import { LoginPage } from '@/features/auth/login-page'
import { SSOLoginPage } from '@/features/auth/sso-login-page'
import { SSOCallbackPage } from '@/features/auth/sso-callback-page'

// Auth
import { AuthProvider, RequireAuth } from '@/lib/auth/context'
import { DemoRoleToggle } from '@/lib/auth/demo-role-toggle'
import { DemoRoleProvider, useDemoRoleContext } from '@/lib/auth/demo-role-context'

/**
 * CRITICAL: DO NOT REMOVE THE ENTITLEMENTS IMPORTS OR DEMO TOGGLE
 *
 * These provide the demo mode toggles in the bottom-right corner for:
 * - Plan tiers: free, pro, enterprise
 *
 * The toggle is ESSENTIAL for testing and demonstrating feature gating.
 * Keyboard shortcut: Ctrl+Shift+P to cycle plans
 */
import {
  EntitlementsProvider,
  useDemoEntitlements,
  DemoToggle,
} from '@/lib/entitlements'

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b px-4">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 h-4" />
            <span className="text-sm text-muted-foreground">Dataing</span>
          </div>
          <ModeToggle />
        </header>
        <main className="flex-1 p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  )
}

/**
 * CRITICAL: DO NOT REMOVE THIS COMPONENT
 *
 * AppWithEntitlements wraps the app with entitlements context and renders:
 * - DemoToggle (bottom-right): Plan tiers (free/pro/enterprise)
 * - DemoRoleToggle (bottom-left): User roles (viewer/member/admin/owner)
 */
function AppWithEntitlements() {
  const { entitlements, plan, setPlan } = useDemoEntitlements()
  const { role, setRole } = useDemoRoleContext()

  return (
    <EntitlementsProvider entitlements={entitlements}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/sso-login" element={<SSOLoginPage />} />
        <Route path="/auth/sso/callback" element={<SSOCallbackPage />} />

        {/* Protected routes */}
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AppLayout>
                <Routes>
                  <Route
                    index
                    element={
                      <FeatureErrorBoundary feature="dashboard">
                        <DashboardPage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="investigations"
                    element={
                      <FeatureErrorBoundary feature="investigations">
                        <InvestigationList />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="investigations/new"
                    element={
                      <FeatureErrorBoundary feature="new investigation">
                        <NewInvestigation />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="investigations/:id"
                    element={
                      <FeatureErrorBoundary feature="investigation details">
                        <InvestigationDetail />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="datasources"
                    element={
                      <FeatureErrorBoundary feature="data sources">
                        <DataSourcePage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="datasources/:datasourceId/datasets"
                    element={
                      <FeatureErrorBoundary feature="datasets">
                        <DatasetListPage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="datasets/:datasetId"
                    element={
                      <FeatureErrorBoundary feature="dataset details">
                        <DatasetDetailPage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="usage"
                    element={
                      <FeatureErrorBoundary feature="usage">
                        <UsagePage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="notifications"
                    element={
                      <FeatureErrorBoundary feature="notifications">
                        <NotificationsPage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="settings"
                    element={
                      <FeatureErrorBoundary feature="settings">
                        <SettingsPage />
                      </FeatureErrorBoundary>
                    }
                  />
                  <Route
                    path="admin"
                    element={
                      <FeatureErrorBoundary feature="admin">
                        <AdminPage />
                      </FeatureErrorBoundary>
                    }
                  />
                </Routes>
              </AppLayout>
            </RequireAuth>
          }
        />
      </Routes>
      {/* CRITICAL: DO NOT REMOVE - Demo toggles for testing */}
      {/* Bottom-right: Plan tiers (free/pro/enterprise) */}
      <DemoToggle plan={plan} onPlanChange={setPlan} />
      {/* Bottom-left: User roles (viewer/member/admin/owner) */}
      <DemoRoleToggle currentRole={role} onRoleChange={setRole} />
      <Toaster />
    </EntitlementsProvider>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <DemoRoleProvider>
          <AppWithEntitlements />
        </DemoRoleProvider>
      </AuthProvider>
    </ErrorBoundary>
  )
}

export default App
