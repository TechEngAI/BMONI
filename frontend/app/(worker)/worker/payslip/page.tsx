"use client";

import { useEffect, useState } from "react";
import { FileText, Printer } from "lucide-react";
import toast from "react-hot-toast";
import { PayslipCard } from "@/components/worker/PayslipCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Skeleton } from "@/components/shared/Skeleton";
import { getWorkerPayslip, getWorkerPayslips, unwrapError } from "@/lib/api";
import { unwrapData } from "@/lib/utils";

export default function WorkerPayslipPage() {
  const [months, setMonths] = useState<string[]>([]);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [payslip, setPayslip] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(month?: string) {
    setLoading(true);
    setError("");
    try {
      const [monthsRes, payslipRes] = await Promise.all([
        getWorkerPayslips(),
        getWorkerPayslip(month ? { month_year: month } : undefined),
      ]);
      const monthData = unwrapData<any>(monthsRes);
      const list = monthData.months || monthData.payslips || monthData.items || monthData || [];
      const normalizedMonths = Array.isArray(list) ? list.map((item: any) => typeof item === "string" ? item : item.month_year).filter(Boolean) : [];
      const data = unwrapData<any>(payslipRes);
      const nextPayslip = data.payslip || data;
      setMonths(normalizedMonths);
      setSelectedMonth(month || nextPayslip?.month_year || normalizedMonths[0] || "");
      setPayslip(nextPayslip?.id || nextPayslip?.month_year ? nextPayslip : null);
    } catch (err) {
      const message = unwrapError(err);
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    document.title = "GhostGuard - Payslip";
    load();
  }, []);

  async function changeMonth(month: string) {
    setSelectedMonth(month);
    await load(month);
  }

  if (loading) return <main className="p-6"><Skeleton lines={5} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={() => load(selectedMonth)} />;

  return (
    <main className="mx-auto max-w-5xl p-4 sm:p-8">
      <div className="no-print mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-black">Payslip</h1>
          <p className="mt-1 text-sm text-ink-secondary">Your payroll receipt and BMONI payment confirmation.</p>
        </div>
        {payslip && (
          <div className="flex flex-wrap gap-2">
            <select value={selectedMonth} onChange={(event) => changeMonth(event.target.value)} className="rounded-lg border border-border bg-white px-3 py-2 text-sm font-bold">
              {months.map((month) => <option key={month} value={month}>{month}</option>)}
            </select>
            <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white">
              <Printer className="h-4 w-4" /> Print / Download
            </button>
          </div>
        )}
      </div>

      {!payslip ? (
        <EmptyState icon={FileText} title="No payslips yet" description="Your first payslip will appear here after payroll is processed." />
      ) : (
        <PayslipCard payslip={payslip} />
      )}
    </main>
  );
}
