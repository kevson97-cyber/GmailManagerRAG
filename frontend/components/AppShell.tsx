"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChatIcon, GearIcon, SyncIcon } from "./icons";
import SettingsSheet from "./SettingsSheet";

const NAV_ITEMS = [
  { href: "/sync", label: "Sync", Icon: SyncIcon },
  { href: "/assistant", label: "Assistant", Icon: ChatIcon },
] as const;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const pathname = usePathname();

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Top bar — app name + settings gear, always reachable regardless of viewport. */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 py-3 backdrop-blur md:px-6">
        <span className="text-base font-semibold tracking-tight text-slate-100">
          GmailManager<span className="text-indigo-400">RAG</span>
        </span>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          aria-label="Open settings"
          className="flex h-11 w-11 items-center justify-center rounded-full text-slate-300 transition-colors hover:bg-slate-800 hover:text-slate-100"
        >
          <GearIcon />
        </button>
      </header>

      <div className="flex flex-1 md:flex-row">
        {/* Left sidebar nav — desktop/tablet only. */}
        <aside className="hidden shrink-0 border-r border-slate-800 bg-slate-900/40 md:flex md:w-56 md:flex-col md:py-4">
          <nav className="flex flex-col gap-1 px-3">
            {NAV_ITEMS.map(({ href, label, Icon }) => {
              const active = pathname?.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    active
                      ? "bg-indigo-500/15 text-indigo-300"
                      : "text-slate-300 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </aside>

        <main className="min-w-0 flex-1 overflow-x-hidden pb-24 md:pb-6">
          <div className="mx-auto w-full max-w-5xl px-4 py-4 md:px-6 md:py-6">{children}</div>
        </main>
      </div>

      {/* Bottom tab bar — mobile only. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-800 bg-slate-900/95 backdrop-blur md:hidden">
        {NAV_ITEMS.map(({ href, label, Icon }) => {
          const active = pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium transition-colors ${
                active ? "text-indigo-300" : "text-slate-400"
              }`}
            >
              <Icon className="h-5 w-5" />
              {label}
            </Link>
          );
        })}
      </nav>

      <SettingsSheet open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
