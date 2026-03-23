/**
 * NextAuth.js configuration for Complira authentication.
 *
 * Integrates with backend FastAPI authentication endpoints:
 * - POST /v1/auth/login - User login
 * - POST /v1/auth/signup - User registration
 * - GET /v1/auth/me - Get current user profile
 */

import { NextAuthOptions, User } from "next-auth";
import { JWT } from "next-auth/jwt";
import CredentialsProvider from "next-auth/providers/credentials";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Extended user type with organization details.
 */
export interface CompliraUser extends User {
  id: string;
  email: string;
  name: string;
  emailVerified: boolean;
  organizationId: string;
  organizationName: string;
  role: "owner" | "admin" | "member";
  tier: "free" | "professional" | "enterprise";
  frameworks: string[];
  accessToken: string;
  refreshToken: string;
}

/**
 * Login response from backend API.
 */
interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    name: string;
    email_verified: boolean;
    organization_id: string;
    organization_name: string;
    role: "owner" | "admin" | "member";
    tier: "free" | "professional" | "enterprise";
    frameworks: string[];
    created_at: string;
  };
}

/**
 * NextAuth.js configuration options.
 */
export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      id: "credentials",
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials): Promise<CompliraUser | null> {
        if (!credentials?.email || !credentials?.password) {
          throw new Error("Email and password are required");
        }

        try {
          // Call backend login endpoint
          const response = await fetch(`${API_URL}/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Invalid email or password");
          }

          const data: LoginResponse = await response.json();

          // Transform backend user to NextAuth user
          return {
            id: data.user.id,
            email: data.user.email,
            name: data.user.name,
            emailVerified: data.user.email_verified,
            organizationId: data.user.organization_id,
            organizationName: data.user.organization_name,
            role: data.user.role,
            tier: data.user.tier,
            frameworks: data.user.frameworks,
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
          };
        } catch (error) {
          console.error("Authentication error:", error);
          throw error;
        }
      },
    }),
  ],

  callbacks: {
    /**
     * JWT callback - called when JWT is created or updated.
     * Store user data and tokens in JWT.
     */
    async jwt({ token, user, trigger }): Promise<JWT> {
      // Initial sign in - user object is available
      if (user) {
        const compliraUser = user as CompliraUser;
        token.id = compliraUser.id;
        token.email = compliraUser.email;
        token.name = compliraUser.name;
        token.emailVerified = compliraUser.emailVerified;
        token.organizationId = compliraUser.organizationId;
        token.organizationName = compliraUser.organizationName;
        token.role = compliraUser.role;
        token.tier = compliraUser.tier;
        token.frameworks = compliraUser.frameworks;
        token.accessToken = compliraUser.accessToken;
        token.refreshToken = compliraUser.refreshToken;
        // Store expiry: access token is valid for 15 min from now
        token.accessTokenExpires = Date.now() + 59 * 60 * 1000;
      }

      // Auto-refresh when access token is expired or about to expire (within 60s)
      const shouldRefresh =
        trigger === "update" ||
        (token.accessTokenExpires && Date.now() > (token.accessTokenExpires as number) - 120_000);

      if (shouldRefresh) {
        try {
          // Try to refresh the access token via backend
          const refreshResponse = await fetch(`${API_URL}/v1/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: token.refreshToken }),
          });

          if (refreshResponse.ok) {
            const refreshData = await refreshResponse.json();
            token.accessToken = refreshData.access_token;
            token.accessTokenExpires = Date.now() + 59 * 60 * 1000;
            if (refreshData.refresh_token) {
              token.refreshToken = refreshData.refresh_token;
            }
          }

          // Also refresh user profile data
          const profileResponse = await fetch(`${API_URL}/v1/auth/me`, {
            headers: {
              Authorization: `Bearer ${token.accessToken}`,
            },
          });

          if (profileResponse.ok) {
            const profile = await profileResponse.json();
            token.name = profile.name;
            token.organizationName = profile.organization_name;
            token.role = profile.role;
            token.tier = profile.tier;
            token.frameworks = profile.frameworks;
          }
        } catch (error) {
          console.error("Failed to refresh session:", error);
        }
      }

      return token;
    },

    /**
     * Session callback - called when session is accessed.
     * Expose user data to client.
     */
    async session({ session, token }) {
      if (token) {
        session.user = {
          id: token.id as string,
          email: token.email as string,
          name: token.name as string,
          emailVerified: token.emailVerified as boolean,
          organizationId: token.organizationId as string,
          organizationName: token.organizationName as string,
          role: token.role as "owner" | "admin" | "member",
          tier: token.tier as "free" | "professional" | "enterprise",
          frameworks: token.frameworks as string[],
        };
        session.accessToken = token.accessToken as string;
        session.refreshToken = token.refreshToken as string;
      }

      return session;
    },
  },

  pages: {
    signIn: "/login",
    signOut: "/",
    error: "/login",
  },

  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days (matches refresh token expiry)
  },

  secret: process.env.NEXTAUTH_SECRET,

  debug: process.env.NODE_ENV === "development",
};
