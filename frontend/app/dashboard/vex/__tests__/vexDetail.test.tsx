import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import VEXDetailsPage from "../[vexId]/page";

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...actual,
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, error: null })),
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  };
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ vexId: "vex_abc123" }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  usePathname: () => "/dashboard/vex/vex_abc123",
}));

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrap = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);

const mockVexDoc = {
  success: true,
  data: {
    vex_id: "vex_abc123",
    bomFormat: "CycloneDX",
    specVersion: "1.5",
    version: 1,
    vulnerabilities: [
      {
        cve_id: "CVE-2021-44228",
        state: "not_affected",
        justification: "code_not_reachable",
        detail: "Log4j not used in production",
        enrichment: {
          in_kev: true,
          epss_score: 0.97,
          cvss_score: 10.0,
          cvss_severity: "CRITICAL",
          weaknesses: [{ cwe_id: "CWE-502", name: "Deserialization" }],
          attack_techniques: [{ technique_id: "T1190", name: "Exploit Public-Facing App" }],
          nist_controls: [],
          d3fend_defenses: [],
          regulatory_violations: [],
        },
      },
    ],
    metadata: { component: { name: "my-app" } },
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
    customer_id: "customer_001",
  },
};

describe("VEXDetailsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders VEX document details", () => {
    vi.mocked(useQuery).mockReturnValue({ data: mockVexDoc, isLoading: false, error: null } as any);
    wrap(<VEXDetailsPage />);
    expect(screen.getByText(/vex_abc123/i)).toBeInTheDocument();
  });

  it("shows vulnerability with enrichment", () => {
    vi.mocked(useQuery).mockReturnValue({ data: mockVexDoc, isLoading: false, error: null } as any);
    wrap(<VEXDetailsPage />);
    expect(screen.getByText("CVE-2021-44228")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    wrap(<VEXDetailsPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("shows error when VEX not found", () => {
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("VEX not found"),
    } as any);
    wrap(<VEXDetailsPage />);
    expect(screen.getAllByText(/error|failed|not found/i).length).toBeGreaterThan(0);
  });
});
