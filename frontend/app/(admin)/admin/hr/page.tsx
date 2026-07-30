"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { Loader2, Plus, ShieldAlert, Trash2, UserCog } from "lucide-react";
import toast from "react-hot-toast";
import { InviteCodeDisplay } from "@/components/admin/InviteCodeDisplay";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Modal } from "@/components/shared/Modal";
import { Skeleton } from "@/components/shared/Skeleton";
import { Input } from "@/components/ui/Input";
import { createHrOfficer, deleteHrOfficer, getHrOfficers, reactivateHrOfficer, suspendHrOfficer, unwrapError } from "@/lib/api";
import { cn, unwrapData } from "@/lib/utils";

type HrOfficer = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  status: string;
  last_login?: string | null;
};

export default function AdminHrPage() {
  const [officers, setOfficers] = useState<HrOfficer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", phone_number: "" });
  const [createdCode, setCreatedCode] = useState("");
  const [suspendTarget, setSuspendTarget] = useState<HrOfficer | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<HrOfficer | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await getHrOfficers();
      const data = unwrapData<any>(response);
      setOfficers(data.hr_officers || data.items || data || []);
    } catch (err) {
      setError(unwrapError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    document.title = "GhostGuard - HR Officers";
    load();
  }, []);

  const sortedOfficers = useMemo(() => [...officers].sort((a, b) => a.last_name.localeCompare(b.last_name)), [officers]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const response = await createHrOfficer(form);
      const data = unwrapData<any>(response);
      setCreatedCode(data.invite_code);
      setForm({ first_name: "", last_name: "", email: "", phone_number: "" });
      await load();
      toast.success("HR officer invite code generated.");
    } catch (err) {
      toast.error(unwrapError(err));
    } finally {
      setSubmitting(false);
    }
  }

  function closeModal() {
    setCreatedCode("");
    setModalOpen(false);
  }

  async function suspend(officer: HrOfficer) {
    try {
      if (officer.status === "SUSPENDED") {
        await reactivateHrOfficer(officer.id);
        toast.success("HR officer reactivated.");
      } else {
        await suspendHrOfficer(officer.id);
        toast.success("HR officer suspended.");
      }
      await load();
    } catch (err) {
      toast.error(unwrapError(err));
    }
  }

  async function remove(officer: HrOfficer) {
    try {
      await deleteHrOfficer(officer.id);
      toast.success("HR officer deleted.");
      await load();
    } catch (err) {
      toast.error(unwrapError(err));
    }
  }

  if (loading) return <main className="p-6"><Skeleton lines={6} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={load} />;

  return (
    <main className="p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-black">HR Officers</h1>
          <p className="mt-1 text-sm text-ink-secondary">Invite and manage payroll approvers for your company.</p>
        </div>
        <button onClick={() => setModalOpen(true)} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white">
          <Plus className="h-4 w-4" /> Add HR Officer
        </button>
      </div>

      <section className="mt-6 overflow-hidden rounded-2xl border border-border bg-white shadow-sm">
        {sortedOfficers.length === 0 ? (
          <div className="p-6">
            <EmptyState icon={UserCog} title="No HR officers yet" description="Add your first HR officer so they can review and approve payroll runs." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs font-black uppercase tracking-widest text-ink-tertiary">
                <tr>
                  <th className="px-5 py-4">Name</th>
                  <th className="px-5 py-4">Email</th>
                  <th className="px-5 py-4">Status</th>
                  <th className="px-5 py-4">Last Login</th>
                  <th className="px-5 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {sortedOfficers.map((officer) => (
                  <tr key={officer.id}>
                    <td className="px-5 py-4 font-bold text-ink">{officer.first_name} {officer.last_name}</td>
                    <td className="px-5 py-4 text-ink-secondary">{officer.email}</td>
                    <td className="px-5 py-4">
                      <span className={cn("rounded-full px-2.5 py-1 text-xs font-black", officer.status === "ACTIVE" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700")}>
                        {officer.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-ink-secondary">{officer.last_login ? format(new Date(officer.last_login), "dd MMM yyyy") : "Never"}</td>
                    <td className="px-5 py-4">
                      <div className="flex justify-end gap-2">
                        <button onClick={() => setSuspendTarget(officer)} className="inline-flex items-center gap-1 rounded-lg border border-amber-200 px-3 py-2 text-xs font-bold text-amber-700 hover:bg-amber-50">
                          <ShieldAlert className="h-3.5 w-3.5" /> {officer.status === "SUSPENDED" ? "Reactivate" : "Suspend"}
                        </button>
                        <button onClick={() => setDeleteTarget(officer)} className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50">
                          <Trash2 className="h-3.5 w-3.5" /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal open={modalOpen && !createdCode} onClose={() => setModalOpen(false)} title="Add HR Officer">
        <form onSubmit={submit} className="space-y-4">
          <Input label="First Name" value={form.first_name} onChange={(event) => setForm((current) => ({ ...current, first_name: event.target.value }))} required />
          <Input label="Last Name" value={form.last_name} onChange={(event) => setForm((current) => ({ ...current, last_name: event.target.value }))} required />
          <Input label="Email" type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} required />
          <Input label="Phone Number" type="tel" value={form.phone_number} onChange={(event) => setForm((current) => ({ ...current, phone_number: event.target.value }))} />
          <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
            <button type="button" onClick={() => setModalOpen(false)} className="rounded-lg border border-border px-4 py-2 text-sm font-bold text-ink-secondary">
              Cancel
            </button>
            <button type="submit" disabled={submitting} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-60">
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {submitting ? "Generating invite code..." : "Generate Invite Code"}
            </button>
          </div>
        </form>
      </Modal>
      <Modal open={!!createdCode} onClose={closeModal} title="HR Officer Invite Code">
        <p className="mb-4 text-sm text-ink-secondary">Share this invite code with the HR officer so they can sign up.</p>
        <InviteCodeDisplay code={createdCode} />
        <button onClick={closeModal} className="mt-6 rounded-lg bg-brand px-4 py-2 font-bold text-white">Done</button>
      </Modal>

      <ConfirmDialog
        open={Boolean(suspendTarget)}
        onClose={() => setSuspendTarget(null)}
        title={suspendTarget?.status === "SUSPENDED" ? "Reactivate HR officer?" : "Suspend HR officer?"}
        description={suspendTarget ? `${suspendTarget.first_name} ${suspendTarget.last_name} will ${suspendTarget.status === "SUSPENDED" ? "regain" : "lose"} access to the HR portal.` : ""}
        confirmLabel={suspendTarget?.status === "SUSPENDED" ? "Reactivate" : "Suspend"}
        confirmVariant={suspendTarget?.status === "SUSPENDED" ? "primary" : "danger"}
        onConfirm={async () => {
          if (suspendTarget) await suspend(suspendTarget);
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Delete HR officer?"
        description={deleteTarget ? `This permanently removes ${deleteTarget.first_name} ${deleteTarget.last_name}'s HR account.` : ""}
        confirmLabel="Delete"
        confirmVariant="danger"
        onConfirm={async () => {
          if (deleteTarget) await remove(deleteTarget);
        }}
      />
    </main>
  );
}
