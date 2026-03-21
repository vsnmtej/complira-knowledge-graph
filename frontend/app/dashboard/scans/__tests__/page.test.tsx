import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ScansPage from "../page";

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...actual,
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, error: null })),
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  };
});

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrap = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);

const mockScans = [
  {
    session_id: "sess_001",
    tool_name: "syft",
    tool_version: "1.0",
    scan_type: "sbom",
    scan_timestamp: "2026-01-15T10:00:00Z",
    status: "completed",
    findings_count: 42,
    components_count: 120,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:05:00Z",
    metadata: {},
  },
];

describe("ScansPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders page title", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: [] }, isLoading: false, error: null } as any);
    wrap(<ScansPage />);
    expect(screen.getByText("SBOM Scans")).toBeInTheDocument();
  });

  it("shows upload button", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: [] }, isLoading: false, error: null } as any);
    wrap(<ScansPage />);
    expect(screen.getAllByText("Upload Scan").length).toBeGreaterThan(0);
  });

  it("renders scan table with data", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: mockScans }, isLoading: false, error: null } as any);
    wrap(<ScansPage />);
    expect(screen.getByText("sess_001")).toBeInTheDocument();
    expect(screen.getByText("syft")).toBeInTheDocument();
  });

  it("shows empty state when no scans", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: [] }, isLoading: false, error: null } as any);
    wrap(<ScansPage />);
    expect(screen.getByText("No scans yet")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    wrap(<ScansPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });
});
