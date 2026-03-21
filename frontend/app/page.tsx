import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-primary-50 to-white">
      <main className="container flex flex-col items-center justify-center gap-12 px-4 py-16">
        <div className="flex flex-col items-center gap-6 text-center">
          <h1 className="text-5xl font-extrabold tracking-tight text-primary-900 sm:text-[5rem]">
            <span className="text-primary-700">Complira</span>
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl">
            Cybersecurity Compliance Platform
          </p>
          <p className="text-lg text-gray-500 max-w-xl">
            SBOM analysis, vulnerability enrichment, and regulatory compliance automation
          </p>
        </div>

        <div className="flex gap-4">
          <Link href="/signup">
            <Button size="lg" className="bg-primary-700 hover:bg-primary-900">
              Get Started
            </Button>
          </Link>
          <Link href="/login">
            <Button size="lg" variant="outline">
              Sign In
            </Button>
          </Link>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-3 max-w-4xl">
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-2 text-lg font-semibold text-primary-900">SBOM Analysis</h3>
            <p className="text-gray-600">
              Upload CycloneDX, SPDX, or SARIF files for comprehensive vulnerability analysis
            </p>
          </div>
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-2 text-lg font-semibold text-primary-900">Real-Time Enrichment</h3>
            <p className="text-gray-600">
              CVE, CWE, MITRE ATT&CK, and regulatory framework mapping with live progress updates
            </p>
          </div>
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-2 text-lg font-semibold text-primary-900">Compliance Reports</h3>
            <p className="text-gray-600">
              Generate VEX documents and PDF reports for FDA 524B, EU CRA, IEC 62304, NIST compliance
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
