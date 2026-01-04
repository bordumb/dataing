import NextAuth from "next-auth";
import { authConfig } from "./auth.config";
import OktaProvider from "next-auth/providers/okta";
import Credentials from "next-auth/providers/credentials";

// User role type definition
export type UserRole = "admin" | "member" | "viewer";

// Role-based permissions mapping
export const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
  admin: [
    "investigations:read",
    "investigations:write",
    "investigations:delete",
    "users:read",
    "users:write",
    "users:delete",
    "settings:read",
    "settings:write",
    "analytics:read",
  ],
  member: [
    "investigations:read",
    "investigations:write",
    "analytics:read",
  ],
  viewer: [
    "investigations:read",
    "analytics:read",
  ],
};

// Map Okta groups to application roles
function mapOktaGroupsToRole(groups: string[]): UserRole {
  if (groups.includes("DataDr-Admins")) return "admin";
  if (groups.includes("DataDr-Members")) return "member";
  return "viewer";
}

// Determine which provider to use based on environment
const isDevelopment = process.env.NODE_ENV === "development";
const useOkta = process.env.OKTA_CLIENT_ID && process.env.OKTA_CLIENT_SECRET && process.env.OKTA_ISSUER;

export const {
  handlers: { GET, POST },
  auth,
  signIn,
  signOut,
} = NextAuth({
  ...authConfig,
  providers: [
    // Production: Okta OIDC for enterprise authentication
    ...(useOkta
      ? [
          OktaProvider({
            clientId: process.env.OKTA_CLIENT_ID!,
            clientSecret: process.env.OKTA_CLIENT_SECRET!,
            issuer: process.env.OKTA_ISSUER!,
            authorization: {
              params: { scope: "openid email profile groups" },
            },
          }),
        ]
      : []),

    // Development fallback: Credentials provider (disabled in production)
    ...(isDevelopment && !useOkta
      ? [
          Credentials({
            credentials: {
              email: { label: "Email", type: "email" },
              password: { label: "Password", type: "password" },
            },
            async authorize(credentials) {
              // ⚠️ DEVELOPMENT ONLY - This accepts any credentials
              // Never use this in production
              if (credentials?.email && credentials?.password) {
                return {
                  id: "dev-user-1",
                  name: "Demo User",
                  email: credentials.email as string,
                  role: "admin",
                };
              }
              return null;
            },
          }),
        ]
      : []),
  ],
  callbacks: {
    async jwt({ token, account, user, profile }) {
      // On initial sign-in
      if (account) {
        token.accessToken = account.access_token;
      }

      // Map Okta groups to roles and permissions
      if (profile?.groups) {
        const groups = profile.groups as string[];
        const role = mapOktaGroupsToRole(groups);
        token.role = role;
        token.permissions = ROLE_PERMISSIONS[role] || [];
      } else if (user) {
        // Fallback for dev mode
        token.role = user.role || "viewer";
        token.permissions = ROLE_PERMISSIONS[(user.role as UserRole) || "viewer"] || [];
      }

      return token;
    },
    async session({ session, token }) {
      // Send properties to the client
      if (session.user) {
        session.user.id = token.sub as string;
        session.user.role = token.role as string;
      }
      session.accessToken = token.accessToken as string;
      session.permissions = token.permissions as string[];
      return session;
    },
  },
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60, // 8 hours
  },
});
