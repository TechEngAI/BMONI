"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Copy, Loader2, RotateCcw, XCircle } from "lucide-react";
import toast from "react-hot-toast";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { formatNGN } from "@/lib/utils";

export function ReceiptsTable({
  receipts,
  onRetry,
}: {
  receipts: any[];
  onRetry: (receipt: any) => Promise<void>;
}) {
  const [copied, setCopied] = useState("");
  const [retryReceipt, setRetryReceipt] = useState<any>(null);

  const totals = useMemo(() => {
    const paidRows = receipts.filter((receipt) => (receipt.squad_status || receipt.status) === "PAID");
    return {
      paid: paidRows.reduce((sum, receipt) => sum + Number(receipt.net_pay || receipt.net_amount || 0), 0),
      failed: receipts.filter((receipt) => (receipt.squad_status || receipt.status) === "FAILED").length,
    };
  }, [receipts]);

  function handleCopy(text?: string) {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(""), 2000);
  }

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-border bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs font-black uppercase tracking-widest text-ink-tertiary">
              <tr>
                <th className="px-4 py-3">Worker Name</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Gross Pay</th>
                <th className="px-4 py-3">Deductions</th>
                <th className="px-4 py-3">Net Pay</th>
                <th className="px-4 py-3">Bank</th>
                <th className="px-4 py-3">BMONI TX ID</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Paid At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {receipts.map((receipt) => {
                const txId = receipt.squad_tx_id || receipt.squad_reference || "";
                const status = receipt.squad_status || receipt.status;
                const workerName = receipt.worker_name || `${receipt.first_name || ""} ${receipt.last_name || ""}`.trim();
                return (
                  <tr key={receipt.id || receipt.receipt_id || txId} className="align-top">
                    <td className="px-4 py-4 font-bold text-ink">{workerName}</td>
                    <td className="px-4 py-4 text-ink-secondary">{receipt.role_name || receipt.role || "-"}</td>
                    <td className="px-4 py-4 font-semibold">{formatNGN(Number(receipt.gross_pay || receipt.gross_salary || 0))}</td>
                    <td className="px-4 py-4">{formatNGN(Number(receipt.deductions || receipt.total_deductions || 0))}</td>
                    <td className="px-4 py-4 font-black text-brand">{formatNGN(Number(receipt.net_pay || receipt.net_amount || 0))}</td>
                    <td className="px-4 py-4 text-xs">{receipt.bank_name || "-"}<br />{receipt.masked_account_number || receipt.account_number_masked || "****"}</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2">
                        <span title={txId} className="max-w-[140px] truncate font-mono text-xs">{txId || "-"}</span>
                        {txId && (
                          <button onClick={() => handleCopy(txId)} className="rounded-md border border-border p-1 text-ink-tertiary hover:text-brand" aria-label="Copy BMONI transaction ID">
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                      {copied === txId && <span className="text-[10px] font-bold text-green-700">Copied</span>}
                    </td>
                    <td className="px-4 py-4"><StatusBadge status={status} onRetry={() => setRetryReceipt(receipt)} /></td>
                    <td className="px-4 py-4 text-xs text-ink-secondary">{receipt.paid_at ? new Date(receipt.paid_at).toLocaleString() : "Pending"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap gap-4 border-t border-border bg-slate-50 px-4 py-3 text-sm font-bold">
          <span className="text-green-700">Total paid: {formatNGN(totals.paid)}</span>
          {totals.failed > 0 && <span className="text-red-700">Total failed: {totals.failed}</span>}
          <span className="text-ink-secondary">Total receipts: {receipts.length}</span>
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(retryReceipt)}
        onClose={() => setRetryReceipt(null)}
        title={`Retry payment for ${retryReceipt?.worker_name || "worker"}?`}
        description="This will initiate a new BMONI transfer."
        confirmLabel="Retry Payment"
        onConfirm={async () => {
          await onRetry(retryReceipt);
          toast.success("Payment retry initiated");
        }}
      />
    </>
  );
}

function StatusBadge({ status, onRetry }: { status: string; onRetry: () => void }) {
  if (status === "PAID") return <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-1 text-xs font-black text-green-700"><CheckCircle2 className="h-3.5 w-3.5" />Paid</span>;
  if (status === "FAILED") return <span className="inline-flex items-center gap-2"><span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-1 text-xs font-black text-red-700"><XCircle className="h-3.5 w-3.5" />Failed</span><button onClick={onRetry} className="rounded-md border border-red-200 px-2 py-1 text-xs font-bold text-red-700"><RotateCcw className="mr-1 inline h-3 w-3" />Retry</button></span>;
  return <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-black text-amber-700"><Loader2 className="h-3.5 w-3.5 animate-spin" />Processing</span>;
}
