"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Loader, Wallet as WalletIcon } from "lucide-react";
import toast from "react-hot-toast";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Skeleton } from "@/components/shared/Skeleton";
import { getWallet, initiateDeposit, getWalletTransactions, unwrapError } from "@/lib/api";
import { formatNGN, unwrapData } from "@/lib/utils";

export function WalletContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [wallet, setWallet] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showDepositModal, setShowDepositModal] = useState(false);
  const [depositAmount, setDepositAmount] = useState("");
  const [isDepositing, setIsDepositing] = useState(false);
  const [page, setPage] = useState(1);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const walletResponse = await getWallet();
      const walletData = unwrapData<any>(walletResponse);
      setWallet(walletData);
      setTransactions(walletData.recent_transactions || []);
    } catch (err) {
      const message = unwrapError(err);
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    document.title = "GhostGuard - Wallet";
    load();

    // Check for deposit=success query param
    if (searchParams.get("deposit") === "success") {
      toast.success("Deposit initiated! Your balance will update within a few minutes.");
      router.replace("/admin/wallet");
      setTimeout(load, 3000);
    }
  }, [searchParams]);

  async function handleInitiateDeposit() {
    const amount = parseFloat(depositAmount);
    if (!depositAmount || isNaN(amount) || amount < 1000) {
      toast.error("Minimum deposit is NGN 1,000");
      return;
    }

    setIsDepositing(true);
    try {
      const response = await initiateDeposit({ amount_ngn: amount });
      const data = unwrapData<any>(response);
      window.location.href = data.checkout_url;
    } catch (err) {
      toast.error(unwrapError(err));
    } finally {
      setIsDepositing(false);
    }
  }

  async function loadMoreTransactions() {
    try {
      const response = await getWalletTransactions({ page: page + 1, page_size: 20 });
      const data = unwrapData<any>(response);
      setTransactions([...transactions, ...data]);
      setPage(page + 1);
    } catch (err) {
      toast.error(unwrapError(err));
    }
  }

  if (loading) return <main className="p-6"><Skeleton lines={8} /></main>;
  if (error) return <ErrorBoundary message={error} onRetry={load} />;

  const balanceNgn = wallet?.balance_ngn || 0;
  const totalDepositedNgn = wallet?.total_deposited_ngn || 0;
  const totalDisbursedNgn = wallet?.total_disbursed_ngn || 0;

  return (
    <main className="p-4 sm:p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Company Wallet</h1>
        <p className="text-sm text-ink-secondary">Deposit funds to pay your workers after payroll approval.</p>
      </div>

      {/* Balance Card */}
      <div className="mb-6 rounded-xl bg-gradient-to-r from-teal-600 to-teal-700 p-6 text-white shadow-lg">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-semibold opacity-90">Available Balance</p>
            <h2 className="mt-2 text-4xl font-bold">{formatNGN(balanceNgn)}</h2>
            <div className="mt-4 flex gap-8">
              <div>
                <p className="text-xs opacity-75">Total Deposited</p>
                <p className="mt-1 text-lg font-semibold">{formatNGN(totalDepositedNgn)}</p>
              </div>
              <div>
                <p className="text-xs opacity-75">Total Disbursed</p>
                <p className="mt-1 text-lg font-semibold">{formatNGN(totalDisbursedNgn)}</p>
              </div>
            </div>
          </div>
          <button
            onClick={() => setShowDepositModal(true)}
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 font-semibold text-teal-700 hover:bg-gray-100"
          >
            <WalletIcon className="h-5 w-5" />
            Deposit
          </button>
        </div>
      </div>

      {/* Deposit Modal */}
      {showDepositModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-bold">Deposit Funds</h3>
            <p className="mt-2 text-sm text-ink-secondary">
              Enter the amount you want to add to your company wallet. You will be redirected to a secure payment page to complete the deposit.
            </p>

            {/* Amount Input */}
            <div className="mt-4">
              <label className="block text-sm font-semibold">Amount (NGN)</label>
              <div className="mt-2 flex items-center rounded-lg border border-border bg-white">
                <span className="px-3 font-semibold text-ink-secondary">₦</span>
                <input
                  type="number"
                  min="1000"
                  step="1000"
                  value={depositAmount}
                  onChange={(e) => setDepositAmount(e.target.value)}
                  placeholder="0"
                  className="flex-1 border-0 bg-transparent py-2 outline-none"
                />
              </div>
              <p className="mt-2 text-xs text-ink-secondary">Your current balance: {formatNGN(balanceNgn)}</p>
              <p className="mt-1 text-xs text-ink-secondary">Minimum deposit: {formatNGN(1000)}</p>
            </div>

            {/* Actions */}
            <div className="mt-6 flex gap-3">
              <button
                onClick={() => setShowDepositModal(false)}
                disabled={isDepositing}
                className="flex-1 rounded-lg border border-border bg-white px-4 py-2 font-semibold text-ink-secondary hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleInitiateDeposit}
                disabled={isDepositing || !depositAmount}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                {isDepositing ? (
                  <>
                    <Loader className="h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  "Proceed to Payment"
                )}
              </button>
            </div>

            {/* Footer Note */}
            <p className="mt-4 text-xs text-center text-ink-secondary">
              Powered by BMONI.
            </p>

            {/* Close Button */}
            <button
              onClick={() => setShowDepositModal(false)}
              className="absolute right-4 top-4 text-ink-secondary hover:text-ink-primary"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Transaction History */}
      <div className="rounded-xl border border-border bg-white">
        <div className="border-b border-border px-6 py-4">
          <h3 className="font-semibold">Transaction History</h3>
        </div>

        {transactions.length === 0 ? (
          <div className="px-6 py-8 text-center">
            <p className="text-ink-secondary">No transactions yet.</p>
          </div>
        ) : (
          <>
            <div className="divide-y divide-border">
              {transactions.map((tx: any) => (
                <div key={tx.id} className="flex items-center justify-between border-b border-border px-6 py-4 last:border-0">
                  <div className="flex-1">
                    <p className="font-medium">{tx.description}</p>
                    <p className="text-xs text-ink-secondary">{new Date(tx.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div>
                      <div className="flex gap-2">
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-semibold ${
                            tx.type === "DEPOSIT" ? "bg-teal-100 text-teal-700" : "bg-purple-100 text-purple-700"
                          }`}
                        >
                          {tx.type}
                        </span>
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-semibold ${
                            tx.status === "SUCCESS"
                              ? "bg-green-100 text-green-700"
                              : tx.status === "PENDING"
                                ? "bg-amber-100 text-amber-700"
                                : "bg-red-100 text-red-700"
                          }`}
                        >
                          {tx.status}
                        </span>
                      </div>
                    </div>
                    <p
                      className={`w-28 text-right font-semibold ${
                        tx.type === "DEPOSIT" ? "text-green-600" : "text-red-600"
                      }`}
                    >
                      {tx.type === "DEPOSIT" ? "+" : "-"}
                      {formatNGN(tx.amount_ngn)}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {transactions.length >= 10 && (
              <div className="px-6 py-4 text-center">
                <button
                  onClick={loadMoreTransactions}
                  className="flex items-center justify-center gap-2 text-sm font-semibold text-teal-600 hover:text-teal-700"
                >
                  Load More <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
