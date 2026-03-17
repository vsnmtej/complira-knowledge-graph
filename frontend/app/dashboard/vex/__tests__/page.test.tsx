import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import VEXPage from "../page";

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

const mockVexDocs = [
  {
    vex_id: "vex_001",
    vulnerabilities_count: 5,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:05:00Z",
    metadata: { component: { name: "my-app", version: "1.0" } },
  },
];

describe("VEXPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders page title", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: [] }, isLoading: false, error: null } as any);
    wrap(<VEXPage />);
    expect(screen.getAllByText(/VEX/i).length).toBeGreaterThan(0);
  });

  it("renders VEX documents list", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: mockVexDocs }, isLoading: false, error: null } as any);
    wrap(<VEXPage />);
    expect(screen.getByText("vex_001")).toBeInTheDocument();
  });

  it("shows empty state when no documents", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { data: [] }, isLoading: false, error: null } as any);
    wrap(<VEXPage />);
    expect(screen.getByText(/no vex/i)).toBeInTheDocument();
  });

  it("shows loading state", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    wrap(<VEXPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });
});
