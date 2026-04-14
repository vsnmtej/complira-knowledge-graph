"use client";

import { useState } from "react";
import { getSession } from "next-auth/react";
import { SimulationLivePanel } from "@/components/situation/SimulationLivePanel";
import { SimulationResultCard } from "@/components/situation/SimulationResultCard";
import type { CSERunStatus } from "@/lib/types/situation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TriggerType = "kev_triggered" | "monthly_posture_sim";
type WizardStep = "select" | "confirm" | "running" | "complete";

const TRIGGER_DESCRIPTIONS: Record<TriggerType, { label: string; description: string; rounds: string }> = {
  kev_triggered: {
    label:       "KEV-triggered run",
    description: "Simulates an active threat actor exploiting known exploited vulnerabilities (KEVs) in your environment. 48 simulation rounds covering initial access through exfiltration.",
    rounds:      "48 rounds (≈ 48 simulated hours)",
  },
  monthly_posture_sim: {
    label:       "Monthly posture simulation",
    description: "Full-cycle red/blue team simulation against your complete attack surface. Evaluates attacker persistence, defender detection time, CRA compliance posture, and board-level risk metrics.",
    rounds:      "720 rounds (≈ 30 simulated days)",
  },
};

export default function SimulationPage() {
  const [step, setStep]                   = useState<WizardStep>("select");
  const [triggerType, setTriggerType]     = useState<TriggerType>("kev_triggered");
  const [simId, setSimId]                 = useState<string | null>(null);
  const [finalRun, setFinalRun]           = useState<CSERunStatus | null>(null);
  const [launching, setLaunching]         = useState(false);
  const [launchError, setLaunchError]     = useState<string | null>(null);

  async function handleLaunch() {
    setLaunching(true);
    setLaunchError(null);
    try {
      const session = await getSession();
      if (!session?.accessToken) {
        setLaunchError("Not authenticated. Please sign in.");
        return;
      }
      const res = await fetch(`${API_URL}/v1/cse/simulations/create`, {
        method:  "POST",
        headers: {
          Authorization:  `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ trigger_type: triggerType }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setLaunchError(err.detail ?? `Launch failed: ${res.status}`);
        return;
      }

      const data = await res.json();
      setSimId(data.sim_id);
      setStep("running");
    } catch (err) {
      setLaunchError(String(err));
    } finally {
      setLaunching(false);
    }
  }

  function handleComplete(run: CSERunStatus) {
    setFinalRun(run);
    setStep("complete");
  }

  function handleReset() {
    setStep("select");
    setSimId(null);
    setFinalRun(null);
    setLaunchError(null);
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Run Simulation</h1>
        <p className="text-sm text-muted-foreground mt-1">
          CSE cybersecurity simulation — attacker vs. defender agent environment
        </p>
      </div>

      {/* Step: Select trigger type */}
      {step === "select" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Choose a simulation type to run against your attack surface.</p>

          <div className="space-y-3">
            {(["kev_triggered", "monthly_posture_sim"] as TriggerType[]).map((t) => {
              const info = TRIGGER_DESCRIPTIONS[t];
              const selected = triggerType === t;
              return (
                <button
                  key={t}
                  onClick={() => setTriggerType(t)}
                  className={`w-full text-left rounded-lg border p-4 transition-colors ${
                    selected
                      ? "border-primary bg-primary/5"
                      : "border-border bg-card hover:border-primary/50"
                  }`}
                >
                  <div className="flex items-center gap-3 mb-1">
                    <div className={`h-3.5 w-3.5 rounded-full border-2 shrink-0 ${
                      selected ? "border-primary bg-primary" : "border-muted-foreground"
                    }`} />
                    <span className="text-sm font-semibold text-foreground">{info.label}</span>
                  </div>
                  <p className="text-[13px] text-muted-foreground pl-6">{info.description}</p>
                  <p className="text-[11px] text-muted-foreground/70 pl-6 mt-1">{info.rounds}</p>
                </button>
              );
            })}
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={() => setStep("confirm")}
              className="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* Step: Confirm */}
      {step === "confirm" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground">Confirm simulation</h2>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Type</span>
                <span className="font-medium text-foreground">{TRIGGER_DESCRIPTIONS[triggerType].label}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Duration</span>
                <span className="font-medium text-foreground">{TRIGGER_DESCRIPTIONS[triggerType].rounds}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Agents</span>
                <span className="font-medium text-foreground">Attacker, SOCAnalyst, DevSecOps, CISO, Regulator</span>
              </div>
            </div>

            <p className="text-[12px] text-muted-foreground border-t border-border pt-3">
              The simulation will run as a background process. Results and board narrative will be available when complete.
              No CVE IDs appear in the board report (ATT&amp;CK tactic names only).
            </p>
          </div>

          {launchError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {launchError}
            </div>
          )}

          <div className="flex justify-between pt-1">
            <button
              onClick={() => setStep("select")}
              className="px-4 py-2 rounded-md text-sm font-medium border border-border text-foreground hover:bg-muted/50 transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleLaunch}
              disabled={launching}
              className="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {launching ? "Starting…" : "Start simulation"}
            </button>
          </div>
        </div>
      )}

      {/* Step: Running */}
      {step === "running" && simId && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Simulation is running. The page will update automatically when complete.
          </p>
          <SimulationLivePanel simId={simId} onComplete={handleComplete} />
        </div>
      )}

      {/* Step: Complete */}
      {step === "complete" && finalRun && (
        <div className="space-y-4">
          <SimulationResultCard run={finalRun} />
          <div className="flex justify-end">
            <button
              onClick={handleReset}
              className="px-4 py-2 rounded-md text-sm font-medium border border-border text-foreground hover:bg-muted/50 transition-colors"
            >
              Run another simulation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
