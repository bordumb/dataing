import { Link, useLocation } from 'react-router-dom'
import {
  Search,
  Database,
  Settings,
  LayoutDashboard,
  Plus,
  BarChart3,
  Bell,
  ChevronUp,
  LogOut,
} from 'lucide-react'

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { useJwtAuth } from '@/lib/auth'

const mainNavItems = [
  {
    title: 'Dashboard',
    url: '/',
    icon: LayoutDashboard,
  },
  {
    title: 'Investigations',
    url: '/investigations',
    icon: Search,
  },
  {
    title: 'Data Sources',
    url: '/datasources',
    icon: Database,
  },
  {
    title: 'Usage',
    url: '/usage',
    icon: BarChart3,
  },
]

const settingsNavItems = [
  {
    title: 'Settings',
    url: '/settings',
    icon: Settings,
  },
  {
    title: 'Notifications',
    url: '/settings/notifications',
    icon: Bell,
  },
]

export function AppSidebar() {
  const location = useLocation()
  const { state } = useSidebar()
  const { user, organization, logout } = useJwtAuth()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Search className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Dataing</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {organization?.name ?? 'Data Quality'}
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {/* Quick Action */}
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="New Investigation">
                <Link to="/investigations/new">
                  <Plus className="size-4" />
                  <span>New Investigation</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        {/* Main Navigation */}
        <SidebarGroup>
          <SidebarGroupLabel>Platform</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
                <SidebarMenuItem key={item.url}>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === item.url ||
                      (item.url !== '/' && location.pathname.startsWith(item.url))}
                    tooltip={item.title}
                  >
                    <Link to={item.url}>
                      <item.icon className="size-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Settings */}
        <SidebarGroup>
          <SidebarGroupLabel>Settings</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {settingsNavItems.map((item) => (
                <SidebarMenuItem key={item.url}>
                  <SidebarMenuButton
                    asChild
                    isActive={location.pathname === item.url ||
                      (item.url === '/settings' && location.pathname.startsWith('/settings'))}
                    tooltip={item.title}
                  >
                    <Link to={item.url}>
                      <item.icon className="size-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar className="h-8 w-8 rounded-lg">
                    <AvatarFallback className="rounded-lg">
                      {user?.name?.charAt(0) ?? 'U'}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">
                      {user?.name ?? 'User'}
                    </span>
                    <span className="truncate text-xs">
                      {organization?.name ?? 'Organization'}
                    </span>
                  </div>
                  <ChevronUp className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                side={state === 'collapsed' ? 'right' : 'top'}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem asChild>
                  <Link to="/settings">
                    <Settings className="mr-2 size-4" />
                    Settings
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout}>
                  <LogOut className="mr-2 size-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
