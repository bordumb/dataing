import { Routes, Route } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { Separator } from '@/components/ui/separator'
import { ModeToggle } from '@/components/mode-toggle'

// Pages
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { InvestigationList } from '@/features/investigation/InvestigationList'
import { InvestigationDetail } from '@/features/investigation/InvestigationDetail'
import { NewInvestigation } from '@/features/investigation/NewInvestigation'
import { DataSourcePage } from '@/features/datasources/datasource-page'
import { SettingsPage } from '@/features/settings/settings-page'
import { UsagePage } from '@/features/usage/usage-page'
import { LoginPage } from '@/features/auth/login-page'

// Auth
import { AuthProvider, RequireAuth } from '@/lib/auth/context'

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

function App() {
  return (
    <AuthProvider>
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
                  <Route index element={<DashboardPage />} />
                  <Route path="investigations" element={<InvestigationList />} />
                  <Route path="investigations/new" element={<NewInvestigation />} />
                  <Route path="investigations/:id" element={<InvestigationDetail />} />
                  <Route path="datasources" element={<DataSourcePage />} />
                  <Route path="settings/*" element={<SettingsPage />} />
                  <Route path="usage" element={<UsagePage />} />
                </Routes>
              </AppLayout>
            </RequireAuth>
          }
        />
      </Routes>
      <Toaster />
    </AuthProvider>
  )
}

export default App
