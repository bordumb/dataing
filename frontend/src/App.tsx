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
import { LoginPage } from '@/features/auth/login-page'

// Auth
import { AuthProvider, RequireAuth } from '@/lib/auth/context'

// Entitlements
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

function AppWithEntitlements() {
  const { entitlements, plan, setPlan } = useDemoEntitlements()

  return (
    <EntitlementsProvider entitlements={entitlements}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

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
                    path="settings/*"
                    element={
                      <FeatureErrorBoundary feature="settings">
                        <SettingsPage />
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
                </Routes>
              </AppLayout>
            </RequireAuth>
          }
        />
      </Routes>
      <DemoToggle plan={plan} onPlanChange={setPlan} />
      <Toaster />
    </EntitlementsProvider>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppWithEntitlements />
      </AuthProvider>
    </ErrorBoundary>
  )
}

export default App
