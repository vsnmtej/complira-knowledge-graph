/**
 * NextAuth.js type declarations.
 *
 * Extends default NextAuth types with Complira-specific user fields.
 */

import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  /**
   * Extended Session type with Complira user and tokens.
   */
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      emailVerified: boolean;
      organizationId: string;
      organizationName: string;
      role: "owner" | "admin" | "member";
      tier: "free" | "professional" | "enterprise";
      frameworks: string[];
    };
    accessToken: string;
    refreshToken: string;
  }

  /**
   * Extended User type with organization details.
   */
  interface User {
    id: string;
    email: string;
    name: string;
    emailVerified: boolean;
    organizationId: string;
    organizationName: string;
    role: "owner" | "admin" | "member";
    tier: "free" | "professional" | "enterprise";
    frameworks: string[];
  }
}

declare module "next-auth/jwt" {
  /**
   * Extended JWT type with user data and tokens.
   */
  interface JWT {
    id?: string;
    email?: string;
    name?: string;
    emailVerified?: boolean;
    organizationId?: string;
    organizationName?: string;
    role?: "owner" | "admin" | "member";
    tier?: "free" | "professional" | "enterprise";
    frameworks?: string[];
    accessToken?: string;
    refreshToken?: string;
  }
}
