"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Receipt, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";
import { ApprovalConfirmModal } from "@/components/hr/ApprovalConfirmModal";
import { DisbursementTracker } from "@/components/hr/DisbursementTracker";
import { WorkerResultCard } from "@/components/hr/WorkerResultCard";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Skeleton } from "@/components/shared/Skeleton";
import { approvePayroll, getHrPayrollResults, getHrWalletBalance, unwrapError } from "@/lib/api";
import { formatNGN, unwrapData } from "@/lib/utils";

const order = { FLAGGED: 0, SUSPICIOUS: 1, VERIFIED: 2 } as Record<string, number>;

export default function HrPayrollReviewPage({ params }: { params: { run_id: string } }) {
  const [run, setRun] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [walletBalance, setWalletBalance] = useState<number>(0);
  const [tab, setTab] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isDisbursing, setIsDisbursing] = useState(false);
  const [insufficientFundsError, setInsufficientFundsError] = useState<any>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [payrollResponse, balanceResponse] = await Promise.all([
        getHrPayrollResults(params.run_id),
        getHrWalletBalance()
      ]);
      const payrollData = unwrapData<any>(payrollResponse);
      const balanceData = unwrapData<any>(balanceResponse);
      
      setRun(payrollData.run);
      setResults(payrollData.results || []);
      setWalletBalance(balanceData.balance_ngn || 0);
    } catch (err) {
      const message = unwrapError(err);
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    document.title = "GhostGuard - HR Payroll Review";
    load();
  }, [params.run_id]);

  const filtered = useMemo(
    () => results.filter((row) => tab === "ALL" || row.verdict === tab).sort((a, b) => (order[a.verdict] ?? 9) - (order[b.verdict] ?? 9)),
    [results, tab],
  );
  const payInclude = (row: any) => row.hr_decision === "INCLUDE" || ((row.hr_decision || "PENDING") === "PENDING" && row.verdict === "VERIFIED");
  const pending = results.filter((row) => ["FLAGGED", "SUSPICIOUS"].includes(row.verdict) && (row.hr_decision || "PENDING") === "PENDING").length;
  const runSummary = {
    total_workers: run?.total_workers || results.length,
    verified_count: run?.verified_count ?? results.filter((row) => row.verdict === "VERIFIED").length,
    included_count: results.filter(payInclude).length,
    excluded_count: results.filter((row) => row.hr_decision === "EXCLUDE").length,
    estimated_total_payout: results.filter(payInclude).reduce((sum, row) => sum + Number(row.net_pay || 0), 0),
    month_year: run?.month_year,
  };

  const isSufficientFunds = walletBalance >= runSummary.estimated_total_payout;

  async function confirmApproval() {
    setIsApproving(true);
    setInsufficientFundsError(null);
    try {
      await approvePayroll(params.run_id);
      toast.success("Payroll approved. Disbursement in progress.");
      setShowConfirmModal(false);
      setIsDisbursing(true);
    } catch (err) {
      const errorData = (err as any).response?.data?.error || (err as any).response?.data;
      if (errorData?.code === "INSUFFICIENT_WALLET_BALANCE") {
        setInsufficientFundsError(errorData.data);
      } else {
        toast.error(unwrapError(err));
      }
      setShowConfirmModal(false);
    } finally {
      setIsApproving(false);
    }
  }

  if (loading) return <main className="p-6"><Skeleton lines={5} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={load} />;
  if (isDisbursing) return <main className="p-4 sm:p-6"><DisbursementTracker runId={params.run_id} onComplete={load} /></main>;

  return (
    <main className="p-4 sm:p-6">
      {/* Insufficient Funds Modal */}
      {insufficientFundsError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-red-600" />
              <h3 className="text-lg font-bold">Insufficient Wallet Balance</h3>
            </div>
            <p className="mt-3 text-sm text-ink-secondary">
              The company wallet does not have enough funds to disburse this payroll.
            </p>
            <div className="mt-4 space-y-2 rounded-lg bg-gray-50 p-4 text-sm">
              <div className="flex justify-between">
                <span className="text-ink-secondary">Required:</span>
                <span className="font-semibold">{formatNGN(insufficientFundsError.required_ngn || runSummary.estimated_total_payout)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-secondary">Available:</span>
                <span className="font-semibold">{formatNGN(insufficientFundsError.available_ngn || walletBalance)}</span>
              </div>
              <div className="border-t border-gray-200 pt-2">
                <div className="flex justify-between">
                  <span className="text-red-600 font-semibold">Shortfall:</span>
                  <span className="font-bold text-red-600">{formatNGN(insufficientFundsError.shortfall_ngn || 0)}</span>
                </div>
              </div>
            </div>
            <p className="mt-4 text-sm text-ink-secondary">
              Please ask the administrator to deposit the shortfall before approving this payroll.
            </p>
            <button
              onClick={() => setInsufficientFundsError(null)}
              className="mt-6 w-full rounded-lg bg-gray-100 px-4 py-2 font-semibold text-ink-primary hover:bg-gray-200"
            >
              Close
            </button>
          </div>
        </div>
      )}

      <div className="sticky top-0 z-20 -mx-4 -mt-4 border-b border-border bg-background/95 px-4 py-4 backdrop-blur sm:-mx-6 sm:-mt-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{run?.month_year || "Payroll review"}</h1>
            <p className="text-sm text-ink-secondary">
              {run?.status} - {pending > 0 ? `${pending} workers need your decision` : `Ready for approval - ${formatNGN(runSummary.estimated_total_payout)}`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/hr/payroll/${params.run_id}/receipts`} className="inline-flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-2 text-sm font-bold text-ink-secondary">
              <Receipt className="h-4 w-4" /> Receipts
            </Link>
            <button
              onClick={() => setShowConfirmModal(true)}
              disabled={pending > 0 || isApproving || !isSufficientFunds}
              title={!isSufficientFunds ? "Insufficient wallet balance" : pending > 0 ? `${pending} decisions pending` : ""}
              className="rounded-lg bg-[#534AB7] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {isApproving ? "Approving..." : pending > 0 ? `${pending} decisions pending` : !isSufficientFunds ? "Insufficient Funds" : "Approve Payroll"}
            </button>
          </div>
        </div>

        {/* Wallet Balance Bar */}
        <div className={`mt-4 rounded-lg p-4 ${isSufficientFunds ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"}`}>
          <div className="flex items-center gap-3">
            <AlertCircle className={`h-5 w-5 ${isSufficientFunds ? "text-green-600" : "text-red-600"}`} />
            <div className="flex-1">
              <p className={`font-semibold ${isSufficientFunds ? "text-green-900" : "text-red-900"}`}>
                Company Wallet Balance: {formatNGN(walletBalance)}
              </p>
              <p className={`text-sm ${isSufficientFunds ? "text-green-700" : "text-red-700"}`}>
                {isSufficientFunds 
                  ? "✓ Sufficient funds. Ready to disburse."
                  : `⚠ Insufficient funds. Payroll requires ${formatNGN(runSummary.estimated_total_payout)} but wallet has ${formatNGN(walletBalance)}. Ask the administrator to deposit ${formatNGN(runSummary.estimated_total_payout - walletBalance)} before approving.`
                }
              </p>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {["ALL", "FLAGGED", "SUSPICIOUS", "VERIFIED"].map((item) => (
            <button key={item} onClick={() => setTab(item)} className={`rounded-lg px-3 py-2 text-sm font-bold ${tab === item ? "bg-[#534AB7] text-white" : "bg-white text-ink-secondary"}`}>
              {item} ({item === "ALL" ? results.length : results.filter((row) => row.verdict === item).length})
            </button>
          ))}
        </div>
      </div>
      <div className="mt-6 space-y-4">{filtered.map((result) => <WorkerResultCard key={result.worker_id} runId={params.run_id} result={result} onChanged={load} />)}</div>
      <ApprovalConfirmModal open={showConfirmModal} onClose={() => setShowConfirmModal(false)} onConfirm={confirmApproval} runSummary={runSummary} isLoading={isApproving} />
    </main>
  );
}
