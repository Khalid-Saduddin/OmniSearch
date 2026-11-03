import React from "react";
import { ShieldCheck, HardDrive, Cpu, Terminal } from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col justify-between p-6 sm:p-12 relative overflow-hidden bg-navy-950">
      {/* Subtle background ambient gradients */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-cyan-500/5 blur-[120px] pointer-events-none rounded-full" />
      <div className="absolute bottom-0 right-0 w-[400px] h-[250px] bg-blue-600/5 blur-[100px] pointer-events-none rounded-full" />

      {/* Header */}
      <header className="flex items-center justify-between border-b border-navy-800/80 pb-4 relative z-10">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-navy-900 border border-navy-700 flex items-center justify-center text-cyan-400 font-semibold shadow-inner">
            <span className="text-sm tracking-wider">Ω</span>
          </div>
          <span className="text-sm font-medium tracking-tight text-slate-300">
            OmniSearch
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-cyan-950/60 text-cyan-400 border border-cyan-800/50">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 mr-1.5 animate-pulse" />
            Phase 1 • Foundation
          </span>
        </div>
      </header>

      {/* Main Hero Section */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-4 py-16 relative z-10 max-w-3xl mx-auto">
        <div className="mb-6 inline-flex p-3 rounded-2xl bg-navy-900/90 border border-navy-700/80 shadow-xl shadow-black/40">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-navy-800 to-navy-900 border border-cyan-500/20 flex items-center justify-center text-cyan-400 shadow-inner">
            <Terminal className="w-6 h-6 stroke-[1.75]" />
          </div>
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white mb-3">
          OmniSearch
        </h1>

        <p className="text-lg sm:text-xl font-normal text-slate-400 max-w-lg mb-8 leading-relaxed">
          One search. Your entire digital world.
        </p>

        {/* Foundation Architecture Specifications */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-2xl text-left">
          <div className="p-4 rounded-xl bg-navy-900/60 border border-navy-800/80">
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1.5">
              <HardDrive className="w-4 h-4" />
              <span>Local-First</span>
            </div>
            <p className="text-xs text-slate-400">
              Files and search indices stay entirely on local disk storage.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-navy-900/60 border border-navy-800/80">
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1.5">
              <ShieldCheck className="w-4 h-4" />
              <span>Privacy Preserved</span>
            </div>
            <p className="text-xs text-slate-400">
              Zero cloud uploads required for document discovery and indexing.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-navy-900/60 border border-navy-800/80">
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1.5">
              <Cpu className="w-4 h-4" />
              <span>Decoupled API</span>
            </div>
            <p className="text-xs text-slate-400">
              FastAPI core mounted on local loopback interface (127.0.0.1:8000).
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-navy-800/80 pt-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 relative z-10">
        <div>
          <span>OmniSearch Architecture Foundation • v0.1.0</span>
        </div>
        <div className="flex items-center gap-4 font-mono text-[11px]">
          <span>FastAPI</span>
          <span>•</span>
          <span>Next.js App Router</span>
          <span>•</span>
          <span>Tailwind CSS</span>
        </div>
      </footer>
    </main>
  );
}

