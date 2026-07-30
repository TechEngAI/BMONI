"use client";

import { useEffect, useState } from "react";
import { Info, X } from "lucide-react";

const DISMISS_KEY = "ghostguard_disclosure_acknowledged";

export function DataDisclosureBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem(DISMISS_KEY) === "true";
    if (!dismissed) setVisible(true);
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "true");
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
        <div className="flex-1 space-y-2 text-sm text-blue-900">
          <p className="font-bold">Privacy notice: remote check-in</p>
          <p>
            This system collects a non-invasive device fingerprint (SHA-256 hash
            of browser type, screen size, timezone, and language — no canvas or
            WebGL data) and your approximate IP-based location. This is used only
            to detect account sharing and impossible-travel patterns for payroll
            fraud prevention. It is not used for continuous tracking or
            surveillance outside this purpose.
          </p>
        </div>
        <button
          onClick={dismiss}
          className="shrink-0 rounded-xl p-1.5 text-blue-500 hover:bg-blue-100 transition-colors"
          aria-label="Dismiss notice"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <button
        onClick={dismiss}
        className="mt-3 ml-8 rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-blue-700 transition-colors"
      >
        I understand
      </button>
    </div>
  );
}
