/**
 * Dashboard layout with sidebar navigation.
 *
 * Protected route - requires authentication.
 */

"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: "📊" },
    { name: "API Tokens", href: "/dashboard/tokens", icon: "🔑" },
    { name: "Team", href: "/dashboard/team", icon: "👥" },
    { name: "Settings", href: "/dashboard/settings", icon: "⚙️" },
  ];

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
        {/* Logo */}
        <div className="p-6 border-b border-slate-700">
          <h1 className="text-2xl font-bold text-white">Complira</h1>
          <p className="text-sm text-slate-400 mt-1">
            {session.user?.organizationName}
          </p>
        </div>

        {/* Navigation */}
        <nav className="p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-slate-700 text-white"
                    : "text-slate-300 hover:bg-slate-700/50 hover:text-white"
                }`}
              >
                <span>{item.icon}</span>
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* User menu */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-700">
          <div className="flex items-center gap-3 px-4 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {session.user?.name}
              </p>
              <p className="text-xs text-slate-400 truncate">
                {session.user?.email}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {session.user?.role} · {session.user?.tier}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              import("next-auth/react").then((auth) => auth.signOut());
            }}
            className="w-full mt-2 px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700 rounded-md transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}
