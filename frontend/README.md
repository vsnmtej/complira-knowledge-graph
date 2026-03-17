# Complira Frontend

Modern Next.js 14 frontend for the Complira cybersecurity compliance platform.

## Features

### 🔐 Authentication
- NextAuth.js with JWT tokens
- Automatic token refresh on 401 errors
- Role-based access control
- Session management

### 📊 Dashboard
- Real-time statistics (API tokens, scans, vulnerabilities)
- Recent scans activity feed
- Quick navigation cards
- Getting started guide

### 🔑 API Token Management (`/dashboard/tokens`)
- Create tokens with custom scopes and rate limits
- View all active tokens
- Rotate tokens with grace period
- Revoke and delete tokens
- Copy tokens to clipboard

### 🔍 SBOM Scanning (`/dashboard/scans`)
- **Upload**: Drag & drop support for SARIF, CycloneDX, SPDX files
- **Auto-detection**: Automatic format detection from file content
- **List view**: All scans with status, findings, and components
- **Details**: Individual scan view with:
  - Findings table with severity filtering
  - Severity distribution visualization
  - VEX document generation
  - CPE matching

### 🛡️ VEX Management (`/dashboard/vex`)
- **List view**: Card-based view of all VEX documents
- **Details**: Enriched vulnerability data including:
  - **KEV**: CISA Known Exploited Vulnerabilities status
  - **EPSS**: Exploit Prediction Scoring System
  - **CVSS**: Common Vulnerability Scoring System
  - **CWE**: Common Weakness Enumeration
  - **ATT&CK**: MITRE ATT&CK techniques
  - **NIST**: 800-53 security controls
  - **D3FEND**: Defensive techniques
  - **Regulatory**: EU CRA, FDA 524B violations
- **Edit**: Update vulnerability assessments inline
- **Download**: Export VEX documents as JSON

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS + shadcn/ui
- **State Management**: TanStack Query (React Query)
- **Authentication**: NextAuth.js v4
- **HTTP Client**: Fetch API with automatic retry
- **Icons**: Lucide React
- **Date Formatting**: date-fns

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend API running on port 8000

### Installation

```bash
# Install dependencies
npm install
```

### Development

```bash
# Start development server
npm run dev

# Open http://localhost:3000
```

The app will be available at `http://localhost:3000`

### Build for Production

```bash
# Create optimized production build
npm run build

# Start production server
npm start
```

## Project Structure

```
frontend/
├── app/
│   ├── (auth)/              # Authentication routes
│   │   ├── login/
│   │   └── signup/
│   ├── dashboard/           # Protected dashboard
│   │   ├── layout.tsx       # Dashboard layout with sidebar
│   │   ├── page.tsx         # Dashboard home
│   │   ├── tokens/          # API token management
│   │   ├── scans/           # SBOM scanning
│   │   │   ├── page.tsx             # Scans list
│   │   │   └── [sessionId]/page.tsx # Scan details
│   │   ├── vex/             # VEX management
│   │   │   ├── page.tsx             # VEX list
│   │   │   └── [vexId]/page.tsx     # VEX details
│   │   ├── team/            # Team management (placeholder)
│   │   └── settings/        # Settings (placeholder)
│   ├── api/
│   │   └── auth/
│   │       └── [...nextauth]/route.ts  # NextAuth configuration
│   └── layout.tsx           # Root layout
├── components/
│   ├── theme-toggle.tsx     # Dark/light mode toggle
│   └── ui/                  # shadcn/ui components
├── lib/
│   ├── api-client.ts        # HTTP client with auto token refresh
│   └── api/                 # API client functions
│       ├── tokens.ts        # Token management API
│       ├── scans.ts         # Scan management API
│       └── vex.ts           # VEX management API
└── public/                  # Static assets
```

## Adding shadcn/ui Components

```bash
# Install components as needed
npx shadcn-ui@latest add button
npx shadcn-ui@latest add input
npx shadcn-ui@latest add form
npx shadcn-ui@latest add card
npx shadcn-ui@latest add table
```

## Environment Variables

Create a `.env.local` file:

```env
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000

# NextAuth Configuration
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-secret-key-here
```

Generate `NEXTAUTH_SECRET` with:
```bash
openssl rand -base64 32
```

## API Integration

### Authentication Flow

1. User signs up at `/signup`
2. Backend returns JWT access token (15min) and refresh token (7 days)
3. NextAuth stores tokens in session
4. API client automatically refreshes tokens on 401 errors

### API Client

The `apiRequest()` function in `lib/api-client.ts` handles:
- Automatic token injection
- Token refresh on expiration
- Error handling
- Type safety

Example:
```typescript
import { apiRequest } from "@/lib/api-client";

const response = await apiRequest<{ data: User }>("/v1/auth/me");
```

### Token Refresh

Automatic token refresh flow:
1. API returns 401 Unauthorized
2. Client attempts refresh with refresh token
3. On success: retry original request with new token
4. On failure: redirect to login

## API Endpoints Used

### Authentication
- `POST /v1/auth/signup` - Create new account
- `POST /v1/auth/login` - Login
- `POST /v1/auth/refresh` - Refresh access token
- `GET /v1/auth/me` - Get current user

### Tokens
- `GET /v1/tokens` - List tokens
- `POST /v1/tokens` - Create token
- `PATCH /v1/tokens/{id}` - Update token
- `POST /v1/tokens/{id}/rotate` - Rotate token
- `POST /v1/tokens/{id}/revoke` - Revoke token
- `DELETE /v1/tokens/{id}` - Delete token

### Scans
- `POST /v1/scan/ingest` - Upload scan file
- `GET /v1/scans` - List scans
- `GET /v1/scan/{id}` - Get scan details
- `GET /v1/scan/{id}/findings` - Get findings
- `POST /v1/scan/{id}/vex` - Generate VEX
- `POST /v1/scan/{id}/cpe-match` - Match CPEs

### VEX
- `POST /v1/vex` - Create VEX document
- `GET /v1/vex` - List VEX documents
- `GET /v1/vex/{id}` - Get VEX with enrichment
- `PUT /v1/vex/{id}` - Update VEX
- `PATCH /v1/vex/{id}/vulnerability/{cve}` - Update vulnerability
- `DELETE /v1/vex/{id}` - Delete VEX

## Deployment

### Vercel (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Environment Variables in Production

Set these in your deployment platform:
- `NEXT_PUBLIC_API_URL` - Your production API URL
- `NEXTAUTH_URL` - Your production frontend URL
- `NEXTAUTH_SECRET` - Generate with `openssl rand -base64 32`

## Troubleshooting

### Token Expiration Errors

If you see "Invalid or expired token":
1. Sign out
2. Sign back in to get fresh tokens
3. Check that `NEXT_PUBLIC_API_URL` is correct

### CORS Errors

Ensure backend CORS configuration allows your frontend origin.

## License

Proprietary - All rights reserved
