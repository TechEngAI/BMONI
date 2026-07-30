"use client";

import { useCallback, useEffect, useState } from "react";
import { Receipt } from "lucide-react";
import toast from "react-hot-toast";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Skeleton } from "@/components/shared/Skeleton";
import { ReceiptsTable } from "@/components/hr/ReceiptsTable";
import { getHrAllReceipts, retryFailedPayment, unwrapError } from "@/lib/api";
import { unwrapData } from "@/lib/utils";

export default function HrReceiptsPage() {
  const [receipts, setReceipts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getHrAllReceipts();
      const data = unwrapData<any>(response);
      const rows = data.receipts || data.items || data || [];
      setReceipts(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(unwrapError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = "GhostGuard - Payment Receipts";
    load();
  }, [load]);

  async function retry(receipt: any) {
    try {
      const runId = receipt.payroll_run_id || receipt.run_id;
      if (!runId) {
        toast.error("Cannot retry: missing payroll run ID.");
        return;
      }
      await retryFailedPayment(runId, receipt.id || receipt.receipt_id);
      toast.success("Payment retry initiated.");
      await load();
    } catch (err) {
      toast.error(unwrapError(err));
    }
  }

  if (loading) return <main className="p-6"><Skeleton lines={6} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={load} />;

  return (
    <main className="p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-black">Payment Receipts</h1>
        <p className="mt-1 text-sm text-ink-secondary">All payment receipts across payroll runs.</p>
      </div>
      {receipts.length === 0 ? (
        <EmptyState icon={Receipt} title="No receipts yet" description="Receipts will appear here once payroll runs are processed." />
      ) : (
        <ReceiptsTable receipts={receipts} onRetry={retry} />
      )}
    </main>
  );
}
