/**
 * Signup page.
 *
 * Creates new user account and organization via backend API.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState, FormEvent } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ValidationErrors {
  name?: string;
  email?: string;
  password?: string;
  organizationName?: string;
  organizationDomain?: string;
}

export default function SignupPage() {
  const router = useRouter();

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
    organizationName: "",
    organizationDomain: "",
  });

  const [errors, setErrors] = useState<ValidationErrors>({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const validatePassword = (password: string): string | null => {
    if (password.length < 8) {
      return "Password must be at least 8 characters long";
    }
    if (!/[A-Z]/.test(password)) {
      return "Password must contain at least one uppercase letter";
    }
    if (!/[a-z]/.test(password)) {
      return "Password must contain at least one lowercase letter";
    }
    if (!/[0-9]/.test(password)) {
      return "Password must contain at least one number";
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
      return "Password must contain at least one special character";
    }
    return null;
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrors({});
    setServerError("");
    setLoading(true);

    // Client-side validation
    const newErrors: ValidationErrors = {};

    if (formData.password !== formData.confirmPassword) {
      newErrors.password = "Passwords do not match";
    }

    const passwordError = validatePassword(formData.password);
    if (passwordError) {
      newErrors.password = passwordError;
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/v1/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formData.name,
          email: formData.email,
          password: formData.password,
          organization_name: formData.organizationName,
          organization_domain: formData.organizationDomain || undefined,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        setServerError(data.detail || "Failed to create account");
        setLoading(false);
        return;
      }

      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 2000);
    } catch (err) {
      setServerError("An unexpected error occurred");
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
        <div className="max-w-md w-full">
          <div className="bg-green-900/50 border border-green-700 rounded-lg p-8 text-center">
            <div className="text-green-400 text-5xl mb-4">✓</div>
            <h2 className="text-2xl font-semibold text-white mb-2">
              Account Created!
            </h2>
            <p className="text-slate-300">
              Redirecting you to the login page...
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4 py-12">
      <div className="max-w-md w-full space-y-8">
        {/* Logo and Title */}
        <div className="text-center">
          <h1 className="text-4xl font-bold text-white mb-2">Complira</h1>
          <p className="text-slate-400">Cybersecurity Compliance Platform</p>
        </div>

        {/* Signup Card */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-8">
          <div className="mb-6">
            <h2 className="text-2xl font-semibold text-white">
              Create Account
            </h2>
            <p className="text-slate-400 text-sm mt-1">
              Start your compliance journey
            </p>
          </div>

          {serverError && (
            <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-200 text-sm">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Personal Information */}
            <div>
              <label
                htmlFor="name"
                className="block text-sm font-medium text-slate-300 mb-1"
              >
                Full Name
              </label>
              <input
                id="name"
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="John Doe"
                disabled={loading}
              />
              {errors.name && (
                <p className="mt-1 text-xs text-red-400">{errors.name}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-slate-300 mb-1"
              >
                Email Address
              </label>
              <input
                id="email"
                type="email"
                required
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="you@example.com"
                disabled={loading}
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-400">{errors.email}</p>
              )}
            </div>

            {/* Organization Information */}
            <div className="pt-2">
              <h3 className="text-sm font-medium text-slate-300 mb-3">
                Organization Information
              </h3>

              <div className="space-y-3">
                <div>
                  <label
                    htmlFor="organizationName"
                    className="block text-sm font-medium text-slate-400 mb-1"
                  >
                    Organization Name
                  </label>
                  <input
                    id="organizationName"
                    type="text"
                    required
                    value={formData.organizationName}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        organizationName: e.target.value,
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Acme Medical Devices"
                    disabled={loading}
                  />
                </div>

                <div>
                  <label
                    htmlFor="organizationDomain"
                    className="block text-sm font-medium text-slate-400 mb-1"
                  >
                    Domain (Optional)
                  </label>
                  <input
                    id="organizationDomain"
                    type="text"
                    value={formData.organizationDomain}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        organizationDomain: e.target.value,
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="acme-medical.com"
                    disabled={loading}
                  />
                </div>
              </div>
            </div>

            {/* Password */}
            <div className="pt-2">
              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-slate-300 mb-1"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                  disabled={loading}
                />
                <p className="mt-1 text-xs text-slate-500">
                  Must be 8+ characters with uppercase, lowercase, number, and
                  special character
                </p>
              </div>

              <div className="mt-3">
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium text-slate-300 mb-1"
                >
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  value={formData.confirmPassword}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      confirmPassword: e.target.value,
                    })
                  }
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                  disabled={loading}
                />
                {errors.password && (
                  <p className="mt-1 text-xs text-red-400">
                    {errors.password}
                  </p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900 mt-6"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-slate-400 text-sm">
              Already have an account?{" "}
              <Link
                href="/login"
                className="text-blue-400 hover:text-blue-300 font-medium"
              >
                Sign in
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-slate-500 text-xs">
          <p>
            By creating an account, you agree to our{" "}
            <Link href="/terms" className="underline hover:text-slate-400">
              Terms of Service
            </Link>{" "}
            and{" "}
            <Link href="/privacy" className="underline hover:text-slate-400">
              Privacy Policy
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
