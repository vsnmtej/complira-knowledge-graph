"use client";

import { useSearchParams } from "next/navigation";
import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMessage("No verification token provided. Please check your email link.");
      return;
    }

    const verifyEmail = async () => {
      try {
        const response = await fetch(`${API_URL}/v1/auth/verify-email`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });

        if (response.ok) {
          setStatus("success");
        } else {
          const data = await response.json();
          setStatus("error");
          setErrorMessage(data.detail || "Invalid or expired verification token.");
        }
      } catch {
        setStatus("error");
        setErrorMessage("Failed to connect to the server. Please try again.");
      }
    };

    verifyEmail();
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-white mb-2">Complira</h1>
          <p className="text-slate-400">Cybersecurity Compliance Platform</p>
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-8 text-center">
          {status === "verifying" && (
            <>
              <Loader2 className="h-12 w-12 text-blue-400 animate-spin mx-auto mb-4" />
              <h2 className="text-2xl font-semibold text-white mb-2">Verifying Email</h2>
              <p className="text-slate-400">Please wait while we verify your email address...</p>
            </>
          )}

          {status === "success" && (
            <>
              <CheckCircle2 className="h-12 w-12 text-green-400 mx-auto mb-4" />
              <h2 className="text-2xl font-semibold text-white mb-2">Email Verified</h2>
              <p className="text-slate-400 mb-6">
                Your email has been verified successfully. You can now sign in.
              </p>
              <Link
                href="/login"
                className="inline-block w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors text-center"
              >
                Sign In
              </Link>
            </>
          )}

          {status === "error" && (
            <>
              <XCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
              <h2 className="text-2xl font-semibold text-white mb-2">Verification Failed</h2>
              <p className="text-slate-400 mb-6">{errorMessage}</p>
              <Link
                href="/login"
                className="inline-block w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors text-center"
              >
                Back to Sign In
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
        <p className="text-slate-400 mt-2">Verifying...</p>
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  );
}
