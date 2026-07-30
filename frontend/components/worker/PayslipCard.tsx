"use client";

import { useState } from "react";
import { format } from "date-fns";
import { Copy, ShieldCheck } from "lucide-react";
import { formatNGN } from "@/lib/utils";
import { TrustScoreBadge } from "./TrustScoreBadge";

export interface PayslipData {
  id?: string;
  worker?: any;
  worker_id?: string;
  first_name?: string;
  last_name?: string;
  role_name?: string;
  month_year?: string;
  gross_salary?: number;
  gross_pay?: number;
  pension_deduct?: number;
  health_deduct?: number;
  other_deductions?: number;
  net_pay?: number;
  squad_tx_id?: string;
  squad_status?: string;
  status?: string;
  bank_name?: string;
  masked_account_number?: string;
  paid_at?: string;
  days_present?: number;
  working_days?: number;
  trust_score?: number;
  verdict?: string;
}

export function PayslipCard({ payslip }: { payslip: PayslipData }) {
  const [copied, setCopied] = useState(false);
  const worker = payslip.worker || payslip;
  const workerName = `${worker.first_name || payslip.first_name || ""} ${worker.last_name || payslip.last_name || ""}`.trim();
  const gross = Number(payslip.gross_salary || payslip.gross_pay || 0);
  const pension = Number(payslip.pension_deduct || 0);
  const health = Number(payslip.health_deduct || 0);
  const other = Number(payslip.other_deductions || 0);
  const deductions = pension + health + other;
  const net = Number(payslip.net_pay || gross - deductions);
  const attendanceRate = payslip.working_days ? ((Number(payslip.days_present || 0) / Number(payslip.working_days)) * 100).toFixed(1) : "0.0";
  const status = payslip.squad_status || payslip.status || "PENDING";

  function copyTx() {
    if (!payslip.squad_tx_id) return;
    navigator.clipboard.writeText(payslip.squad_tx_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <article className="payslip-print-area rounded-2xl border border-border bg-white p-6 shadow-sm sm:p-8">
      <header className="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand text-white"><ShieldCheck className="h-7 w-7" /></div>
          <div>
            <p className="text-2xl font-black">GhostGuard</p>
            <p className="text-xs font-bold uppercase tracking-widest text-ink-tertiary">Verified payroll receipt</p>
          </div>
        </div>
        <div className="sm:text-right">
          <p className="text-4xl font-black text-ink">PAYSLIP</p>
          <p className="font-bold text-brand">{payslip.month_year}</p>
        </div>
      </header>

      <section className="grid gap-4 border-b border-border py-6 sm:grid-cols-4">
        <Info label="Name" value={workerName || "-"} />
        <Info label="Role" value={payslip.role_name || worker.role_name || worker.roles?.role_name || "-"} />
        <Info label="Worker ID" value={String(payslip.worker_id || worker.id || "").slice(-8) || "-"} />
        <Info label="Pay Period" value={payslip.month_year || "-"} />
      </section>

      <section className="grid gap-6 py-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="overflow-hidden rounded-xl border border-border">
          <div className="bg-slate-50 px-4 py-3 text-sm font-black uppercase tracking-widest text-ink-tertiary">Earnings and Deductions</div>
          <Line label="Basic Salary" value={gross} />
          {pension > 0 && <Line label="Pension" value={pension} muted />}
          {health > 0 && <Line label="Health Insurance" value={health} muted />}
          {other > 0 && <Line label="Other" value={other} muted />}
          <div className="flex items-center justify-between border-t border-border px-4 py-5">
            <span className="text-lg font-black">NET PAY</span>
            <span className="text-3xl font-black text-brand">{formatNGN(net)}</span>
          </div>
        </div>

        <div className="rounded-xl bg-teal-50 p-5">
          <h3 className="text-lg font-black text-teal-900">Payment Confirmation</h3>
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-teal-700">BMONI Reference</p>
              <div className="mt-1 flex items-center gap-2">
                <span className="break-all font-mono font-bold">{payslip.squad_tx_id || "Pending"}</span>
                {payslip.squad_tx_id && <button onClick={copyTx} className="no-print rounded-md border border-teal-200 p-1 text-teal-800"><Copy className="h-3.5 w-3.5" /></button>}
              </div>
              {copied && <p className="no-print mt-1 text-xs font-bold text-green-700">Copied</p>}
            </div>
            <p><strong>Status:</strong> <span className={status === "PAID" ? "text-green-700" : "text-amber-700"}>{status}</span></p>
            <p><strong>Paid via:</strong> BMONI API - Direct Bank Transfer</p>
            <p><strong>Bank:</strong> {payslip.bank_name || "-"} - {payslip.masked_account_number || "****"}</p>
            <p><strong>Date:</strong> {payslip.paid_at ? format(new Date(payslip.paid_at), "dd MMMM yyyy 'at' h:mm a") : "Pending"}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 border-t border-border pt-6 sm:grid-cols-2">
        <div className="rounded-xl bg-slate-50 p-4">
          <p className="text-xs font-black uppercase tracking-widest text-ink-tertiary">Attendance Summary</p>
          <p className="mt-2 text-lg font-black">Days Present: {payslip.days_present || 0} / {payslip.working_days || 0}</p>
          <p className="text-sm text-ink-secondary">Attendance Rate: {attendanceRate}%</p>
        </div>
        <TrustScoreBadge score={payslip.trust_score} verdict={payslip.verdict} />
      </section>
    </article>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs font-black uppercase tracking-widest text-ink-tertiary">{label}</p><p className="mt-1 font-bold text-ink">{value}</p></div>;
}

function Line({ label, value, muted }: { label: string; value: number; muted?: boolean }) {
  return <div className="flex items-center justify-between border-t border-border px-4 py-3"><span className={muted ? "text-ink-secondary" : "font-bold"}>{label}</span><span className={muted ? "text-red-700" : "font-bold"}>{muted ? "-" : ""}{formatNGN(value)}</span></div>;
}
