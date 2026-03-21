import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import TokensPage from "../page";

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

const mockTokens = {
  tokens: [
    {
      id: "token_001",
      name: "CI/CD Token",
      token_prefix: "complira_tk_abc",
      scopes: ["scan:write"],
      rate_limit: 1000,
      created_at: "2026-01-15T10:00:00Z",
      expires_at: "2027-01-15T10:00:00Z",
      revoked: false,
      organization_id: "org_001",
      created_by_user_id: "user_001",
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

describe("TokensPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders page title", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { tokens: [], total: 0 }, isLoading: false, error: null } as any);
    wrap(<TokensPage />);
    expect(screen.getByText("API Tokens")).toBeInTheDocument();
  });

  it("shows create token button", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { tokens: [], total: 0 }, isLoading: false, error: null } as any);
    wrap(<TokensPage />);
    expect(screen.getAllByText("Create Token").length).toBeGreaterThan(0);
  });

  it("renders token table with data", () => {
    vi.mocked(useQuery).mockReturnValue({ data: mockTokens, isLoading: false, error: null } as any);
    wrap(<TokensPage />);
    expect(screen.getByText("CI/CD Token")).toBeInTheDocument();
    expect(screen.getByText("complira_tk_abc")).toBeInTheDocument();
  });

  it("shows empty state when no tokens", () => {
    vi.mocked(useQuery).mockReturnValue({ data: { tokens: [], total: 0 }, isLoading: false, error: null } as any);
    wrap(<TokensPage />);
    expect(screen.getByText(/no.*token/i)).toBeInTheDocument();
  });
});
