"use client";

import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api-client";
import { User, Mail, Building2, Shield, Crown, Calendar, CheckCircle2, XCircle, AlertCircle, ExternalLink } from "lucide-react";
import { format } from "date-fns";
import Link from "next/link";

interface UserProfile {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  organization_id: string;
  organization_name: string;
  role: string;
  tier: string;
  frameworks: string[];
  created_at: string;
}

export default function ProfilePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["profile"],
    queryFn: () => apiRequest<UserProfile>("/v1/auth/me"),
  });

  const profile = data;

  const getRoleBadge = (role: string) => {
    const colors: Record<string, string> = {
      owner: "bg-amber-500/10 text-amber-500 border-amber-500/20",
      admin: "bg-blue-500/10 text-blue-500 border-blue-500/20",
      member: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    };
    return colors[role] || colors.member;
  };

  const getTierBadge = (tier: string) => {
    const colors: Record<string, string> = {
      enterprise: "bg-purple-500/10 text-purple-500 border-purple-500/20",
      pro: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
      free: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    };
    return colors[tier] || colors.free;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="font-medium">Failed to load profile</p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">My Profile</h1>
        <p className="text-muted-foreground mt-1">Manage your account and organization settings</p>
      </div>

      {/* Profile Card */}
      <div className="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
        <div className="bg-gradient-to-r from-primary/10 via-blue-500/5 to-transparent p-8">
          <div className="flex items-start gap-6">
            <div className="h-16 w-16 rounded-full bg-primary/20 flex items-center justify-center">
              <User className="h-8 w-8 text-primary" />
            </div>
            <div className="flex-1">
              <h2 className="text-2xl font-bold">{profile.name}</h2>
              <div className="flex items-center gap-2 mt-1 text-muted-foreground">
                <Mail className="h-4 w-4" />
                <span>{profile.email}</span>
                {profile.email_verified ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-yellow-500" />
                )}
              </div>
              <div className="flex items-center gap-2 mt-3">
                <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${getRoleBadge(profile.role)}`}>
                  <Crown className="h-3 w-3 inline mr-1" />
                  {profile.role}
                </span>
                <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${getTierBadge(profile.tier)}`}>
                  {profile.tier}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="divide-y divide-border">
          {/* Organization */}
          <div className="p-6">
            <h3 className="text-sm font-medium text-muted-foreground mb-4 flex items-center gap-2">
              <Building2 className="h-4 w-4" />
              Organization
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground">Name</p>
                <p className="font-medium mt-0.5">{profile.organization_name}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Organization ID</p>
                <p className="font-mono text-sm mt-0.5">{profile.organization_id}</p>
              </div>
            </div>
          </div>

          {/* Compliance Frameworks */}
          <div className="p-6">
            <h3 className="text-sm font-medium text-muted-foreground mb-4 flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Compliance Frameworks
            </h3>
            {profile.frameworks.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {profile.frameworks.map((fw) => (
                  <span
                    key={fw}
                    className="text-xs px-3 py-1.5 rounded-lg bg-primary/10 text-primary font-medium"
                  >
                    {fw}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No frameworks configured</p>
            )}
          </div>

          {/* Account Details */}
          <div className="p-6">
            <h3 className="text-sm font-medium text-muted-foreground mb-4 flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Account Details
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground">Account Created</p>
                <p className="text-sm mt-0.5">{profile.created_at ? format(new Date(profile.created_at), "PPP") : "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Email Status</p>
                <p className="text-sm mt-0.5 flex items-center gap-1.5">
                  {profile.email_verified ? (
                    <><CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> Verified</>
                  ) : (
                    <><XCircle className="h-3.5 w-3.5 text-yellow-500" /> Not verified</>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="p-6 flex items-center gap-3">
            <Link
              href="/forgot-password"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
            >
              Change Password
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
            <Link
              href="/dashboard/tokens"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
            >
              Manage API Tokens
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
