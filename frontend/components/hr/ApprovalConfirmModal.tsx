"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { Modal } from "@/components/shared/Modal";
import { formatNGN } from "@/lib/utils";

interface RunSummary {
  total_workers?: number;
  verified_count?: number;
  included_count?: number;
  excluded_count?: number;
  estimated_total_payout?: number;
  month_year?: string;
}

export function ApprovalConfirmModal({
  open,
  onClose,
  onConfirm,
  runSummary,
  isLoading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  runSummary: RunSummary;
  isLoading?: boolean;
}) {
  const workersToPay = Number(runSummary.verified_count || 0) + Number(runSummary.included_count || 0);

  return (
    <Modal open={open} onClose={onClose} title={`Approve Payroll - ${runSummary.month_year || "Current run"}`}>
      <div className="space-y-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <Summary label="Workers to be paid" value={workersToPay} className="bg-green-50 text-green-700" />
          <Summary label="Workers excluded" value={Number(runSummary.excluded_count || 0)} className="bg-red-50 text-red-700" />
          <Summary label="Estimated total payout" value={formatNGN(Number(runSummary.estimated_total_payout || 0))} className="bg-teal-50 text-teal-700" />
          <Summary label="Payment method" value="BMONI API - Direct bank transfer" className="bg-slate-50 text-slate-700" />
        </div>

        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <p>
            This action cannot be undone. Salaries will be disbursed immediately to all included workers via BMONI.
            Make sure you have reviewed all flagged workers.
          </p>
        </div>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button onClick={onClose} disabled={isLoading} className="rounded-lg border border-border px-4 py-2 text-sm font-bold text-ink-secondary disabled:opacity-60">
            Cancel
          </button>
          <button onClick={onConfirm} disabled={isLoading} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-5 py-2 text-sm font-bold text-white disabled:opacity-60">
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
            {isLoading ? "Initiating payments..." : "Confirm Disbursement"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Summary({ label, value, className }: { label: string; value: string | number; className: string }) {
  return (
    <div className={`rounded-xl p-4 ${className}`}>
      <p className="text-xs font-black uppercase tracking-widest opacity-70">{label}</p>
      <p className="mt-2 text-xl font-black">{value}</p>
    </div>
  );
}
