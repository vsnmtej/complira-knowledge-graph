"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { LayoutDashboard, Key, LogOut, FileSearch, Shield, FolderKanban, GitBranch, BookOpen } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex items-center justify-content h-screen bg-background">
        <div className="mx-auto text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "Scans", href: "/dashboard/scans", icon: FileSearch },
    { name: "VEX", href: "/dashboard/vex", icon: Shield },
    { name: "Projects", href: "/dashboard/projects", icon: FolderKanban },
    { name: "Repositories", href: "/dashboard/repositories", icon: GitBranch },
    { name: "Reference", href: "/dashboard/reference", icon: BookOpen },
    { name: "API Tokens", href: "/dashboard/tokens", icon: Key },
  ];

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-64 border-r border-border bg-card flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-bold bg-gradient-to-r from-primary to-blue-400 bg-clip-text text-transparent">
            Complira
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {session.user?.organizationName}
          </p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                }`}
              >
                <Icon className="h-5 w-5" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* User menu */}
        <div className="p-4 border-t border-border space-y-2">
          <div className="mb-3 px-2">
            <p className="text-sm font-medium">{session.user?.name}</p>
            <p className="text-xs text-muted-foreground truncate">
              {session.user?.email}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                {session.user?.role}
              </span>
              <span className="text-xs px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
                {session.user?.tier}
              </span>
            </div>
          </div>
          <ThemeToggle />
          <button
            onClick={() => {
              import("next-auth/react").then((auth) => auth.signOut());
            }}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}
