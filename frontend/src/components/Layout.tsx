import { Outlet, Link } from 'react-router-dom'
import { Search } from 'lucide-react'

export function Layout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex h-16 items-center px-4">
          <Link to="/" className="flex items-center space-x-2">
            <Search className="h-6 w-6" />
            <span className="text-xl font-bold">dataing</span>
          </Link>
          <nav className="ml-6 flex space-x-4">
            <Link
              to="/"
              className="text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              Investigations
            </Link>
            <Link
              to="/investigations/new"
              className="text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              New Investigation
            </Link>
          </nav>
        </div>
      </header>
      <main className="container mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
