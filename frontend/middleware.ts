/**
 * NextAuth middleware for server-side route protection.
 *
 * Redirects unauthenticated users to /login before the page renders,
 * preventing the flash of protected content.
 */

export { default } from "next-auth/middleware";

export const config = {
  matcher: ["/dashboard/:path*"],
};
