"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Receipt } from "lucide-react";
import toast from "react-hot-toast";
import { ReceiptsTable } from "@/components/hr/ReceiptsTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Skeleton } from "@/components/shared/Skeleton";
import { downloadReceiptsCsv, getPayrollReceipts, retryFailedPayment, unwrapError } from "@/lib/api";
import { unwrapData } from "@/lib/utils";

export default function PayrollReceiptsPage({ params }: { params: { run_id: string } }) {
  const [receipts, setReceipts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const monthYear = useMemo(() => receipts[0]?.month_year || receipts[0]?.run?.month_year || "payroll", [receipts]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await getPayrollReceipts(params.run_id);
      const data = unwrapData<any>(response);
      const rows = data.receipts || data.items || data || [];
      setReceipts(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(unwrapError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    document.title = "GhostGuard - Payment Receipts";
    load();
  }, [params.run_id]);

  async function downloadCsv() {
    setDownloading(true);
    try {
      const response = await downloadReceiptsCsv(params.run_id);
      const url = URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `ghostguard_receipts_${monthYear}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(unwrapError(err));
    } finally {
      setDownloading(false);
    }
  }

  async function retry(receipt: any) {
    await retryFailedPayment(params.run_id, receipt.id || receipt.receipt_id);
    setReceipts((current) => current.map((row) => (row.id || row.receipt_id) === (receipt.id || receipt.receipt_id) ? { ...row, squad_status: "PENDING", status: "PENDING" } : row));
    window.setTimeout(load, 3000);
  }

  if (loading) return <main className="p-6"><Skeleton lines={6} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={load} />;

  return (
    <main className="p-4 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link href={`/hr/payroll/${params.run_id}`} className="inline-flex items-center gap-2 text-sm font-bold text-ink-secondary hover:text-brand"><ArrowLeft className="h-4 w-4" />Back to review</Link>
          <h1 className="mt-3 text-3xl font-black">Payment Receipts - {monthYear}</h1>
        </div>
        <button onClick={downloadCsv} disabled={downloading} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-60">
          <Download className="h-4 w-4" />{downloading ? "Downloading..." : "Download CSV"}
        </button>
      </div>

      {receipts.length === 0 ? (
        <EmptyState icon={Receipt} title="No receipts yet" description="Receipts will appear here once BMONI begins processing this payroll run." />
      ) : (
        <ReceiptsTable receipts={receipts} onRetry={retry} />
      )}
    </main>
  );
}
