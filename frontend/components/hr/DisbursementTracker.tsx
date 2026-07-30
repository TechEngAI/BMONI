"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Receipt, RotateCcw, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { getPayrollReceipts, retryFailedPayment, unwrapError } from "@/lib/api";
import { formatNGN, unwrapData } from "@/lib/utils";

export function DisbursementTracker({ runId, onComplete }: { runId: string; onComplete: () => void }) {
  const router = useRouter();
  const [receipts, setReceipts] = useState<any[]>([]);
  const [completed, setCompleted] = useState(false);
  const monthYear = receipts[0]?.month_year || receipts[0]?.run?.month_year || "payroll";

  async function load() {
    const response = await getPayrollReceipts(runId);
    const data = unwrapData<any>(response);
    const rows = data.receipts || data.items || data || [];
    setReceipts(Array.isArray(rows) ? rows : []);
    const done = rows.length > 0 && rows.every((receipt: any) => (receipt.bmoni_status || receipt.squad_status || receipt.status) !== "PENDING");
    if (done) {
      setCompleted(true);
      onComplete();
    }
  }

  useEffect(() => {
    let active = true;
    load().catch(() => {});
    const id = window.setInterval(() => {
      if (active && !completed) load().catch(() => {});
    }, 3000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [runId, completed]);

  const stats = useMemo(() => {
    const statusVal = (r: any) => r.bmoni_status || r.squad_status || r.status;
    const paid = receipts.filter((r) => statusVal(r) === "PAID");
    const pending = receipts.filter((r) => statusVal(r) === "PENDING");
    const failed = receipts.filter((r) => statusVal(r) === "FAILED");
    return {
      paid: paid.length,
      pending: pending.length,
      failed: failed.length,
      totalPaid: paid.reduce((sum, r) => sum + Number(r.net_pay || r.net_amount || 0), 0),
    };
  }, [receipts]);

  async function retry(receiptId: string) {
    try {
      await retryFailedPayment(runId, receiptId);
      toast.success("Payment retry initiated");
      await load();
    } catch (error) {
      toast.error(unwrapError(error));
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-black">
            {completed ? <CheckCircle2 className="h-7 w-7 text-green-600" /> : <Loader2 className="h-7 w-7 animate-spin text-brand" />}
            {completed ? "Disbursement Complete" : "Disbursement in progress..."}
          </h2>
          {completed && <p className="mt-1 text-sm text-ink-secondary">{stats.paid} workers paid successfully. Total: {formatNGN(stats.totalPaid)} disbursed.</p>}
        </div>
        {completed && (
          <button onClick={() => router.push(`/hr/payroll/${runId}/receipts`)} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white">
            <Receipt className="h-4 w-4" /> View Receipts
          </button>
        )}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Counter label="Paid" value={stats.paid} className="bg-green-50 text-green-700" />
        <Counter label="Pending" value={stats.pending} className="bg-amber-50 text-amber-700" />
        <Counter label="Failed" value={stats.failed} className="bg-red-50 text-red-700" />
      </div>

      {completed && stats.failed > 0 && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm font-semibold text-amber-800">{stats.failed} payments failed. Use the retry button or contact BMONI support.</p>}

      <div className="mt-6 divide-y divide-border overflow-hidden rounded-xl border border-border">
        {receipts.map((receipt) => {
          const status = receipt.bmoni_status || receipt.squad_status || receipt.status;
          return (
            <div key={receipt.id || receipt.receipt_id || receipt.worker_id} className="grid gap-3 p-4 sm:grid-cols-[1fr_auto_180px] sm:items-center">
              <div>
                <p className="font-bold">{receipt.worker_name || `${receipt.first_name || ""} ${receipt.last_name || ""}`.trim()}</p>
                <p className="text-xs text-ink-secondary">{receipt.role_name || receipt.role}</p>
              </div>
              <p className="font-black text-ink">{formatNGN(Number(receipt.net_pay || receipt.net_amount || 0))}</p>
              <StatusCell status={status} txId={receipt.squad_tx_id} onRetry={() => retry(receipt.id || receipt.receipt_id)} />
            </div>
          );
        })}
        {receipts.length === 0 && <p className="p-8 text-center text-sm text-ink-secondary">Waiting for BMONI payment receipts for {monthYear}...</p>}
      </div>
    </section>
  );
}

function Counter({ label, value, className }: { label: string; value: number; className: string }) {
  return <div className={`rounded-xl p-4 text-center font-black ${className}`}><p className="text-3xl">{value}</p><p className="text-xs uppercase tracking-widest">{label}</p></div>;
}

function StatusCell({ status, txId, onRetry }: { status: string; txId?: string; onRetry: () => void }) {
  if (status === "PAID") return <div className="text-sm font-bold text-green-700"><CheckCircle2 className="mr-1 inline h-4 w-4" />Paid<p className="mt-1 truncate font-mono text-[10px] text-ink-tertiary">{txId}</p></div>;
  if (status === "FAILED") return <div className="flex items-center gap-2 text-sm font-bold text-red-700"><XCircle className="h-4 w-4" />Failed<button onClick={onRetry} className="rounded-md border border-red-200 px-2 py-1 text-xs"><RotateCcw className="mr-1 inline h-3 w-3" />Retry</button></div>;
  return <div className="text-sm font-bold text-ink-secondary"><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />Processing...</div>;
}
