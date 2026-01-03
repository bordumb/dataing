import customInstance from './client'

export interface DashboardStats {
  activeInvestigations: number
  completedToday: number
  dataSources: number
  pendingApprovals: number
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  try {
    return await customInstance<DashboardStats>({
      url: '/dashboard/stats',
      method: 'GET',
    })
  } catch {
    // Return mock data if endpoint doesn't exist
    return {
      activeInvestigations: 3,
      completedToday: 7,
      dataSources: 2,
      pendingApprovals: 1,
    }
  }
}
