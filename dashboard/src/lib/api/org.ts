// Use internal URL for server-side requests, public URL for client-side
const API_BASE_URL = typeof window === 'undefined'
  ? (process.env.API_INTERNAL_URL || "http://api:8000")
  : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

export async function getOrganization() {
  try {
    // For now, return the seeded organization data
    // In the future, we can add a dedicated /api/v1/organization endpoint
    const response = await fetch(`${API_BASE_URL}/api/v1/analytics/stats`);
    if (!response.ok) {
      throw new Error(`Failed to fetch organization: ${response.statusText}`);
    }

    // Return hardcoded organization data based on the seeded demo org
    return {
      id: "org-acme",
      name: "Acme Analytics",
      user_count: 4,
      team_count: 3,
      plan: "Enterprise",
    };
  } catch (error) {
    console.error("Error fetching organization:", error);
    // Return fallback data
    return {
      id: "org-acme",
      name: "Acme Analytics",
      user_count: 4,
      team_count: 3,
      plan: "Enterprise",
    };
  }
}
