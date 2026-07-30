"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { approvePayroll, unwrapError } from "@/lib/api";

export function ApprovePayrollButton({ runId, pendingCount, onApproved }: { runId: string; pendingCount: number; onApproved: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button disabled={pendingCount > 0} onClick={() => setOpen(true)} className="rounded-lg bg-[#534AB7] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-gray-300">
        {pendingCount > 0 ? `${pendingCount} pending` : "Approve Payroll"}
      </button>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        title="Approve payroll?"
        description="Approving payroll will trigger salary disbursement for all included workers via BMONI. This cannot be undone."
        confirmLabel="Approve"
        onConfirm={async () => {
          try {
            await approvePayroll(runId);
            toast.success("Payroll approved.");
            onApproved();
          } catch (error) {
            toast.error(unwrapError(error));
          }
        }}
      />
    </>
  );
}
