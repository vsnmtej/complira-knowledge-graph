import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import DashboardPage from "../page";

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return { ...actual, useQuery: vi.fn(), useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })) };
});

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const wrap = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);

describe("DashboardPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders dashboard title", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    wrap(<DashboardPage />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("shows stat cards", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
    wrap(<DashboardPage />);
    expect(screen.getByText("API Tokens")).toBeInTheDocument();
    expect(screen.getByText("SBOM Scans")).toBeInTheDocument();
    expect(screen.getByText("Vulnerabilities")).toBeInTheDocument();
  });

  it("shows getting started section", () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
    wrap(<DashboardPage />);
    expect(screen.getByText("Getting Started")).toBeInTheDocument();
  });
});
