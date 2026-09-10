import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/nav-bar";

export const metadata: Metadata = {
  title: "LLM Chess Control Room",
  description: "Live games, experiments, and human vs LLM play for llmchess."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <NavBar />
          {process.env.NEXT_PUBLIC_USE_MOCKS === "true" && <div role="status" style={{background:"#ffd275",color:"#172130",padding:"12px",textAlign:"center"}}>Synthetic demo data — these are not experiment results.</div>}
          <main className="page-shell">{children}</main>
        </div>
      </body>
    </html>
  );
}
