"use client";

import { motion } from "framer-motion";
import { Check, X, Shield, Users, Clock, Zap } from "lucide-react";

const features = [
  { name: "GPS Verification", ghostguard: true, manual: false, legacy: "Partial" },
  { name: "Bank Account Anomaly Detection", ghostguard: true, manual: false, legacy: false },
  { name: "Device Fingerprinting", ghostguard: true, manual: false, legacy: false },
  { name: "Real-time Fraud Alerts", ghostguard: true, manual: false, legacy: "Delayed" },
  { name: "BMONI API Integration", ghostguard: true, manual: false, legacy: false },
  { name: "Automated Trust Scoring", ghostguard: true, manual: false, legacy: false },
  { name: "Detection Speed", ghostguard: "Instant", manual: "Weeks", legacy: "Days" },
];

export function ComparisonSection() {
  return (
    <section className="bg-white dark:bg-slate-950 py-32 transition-colors duration-500 overflow-hidden">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-20">
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-brand mb-4">The Comparison</h2>
          <p className="text-4xl font-black tracking-tight text-ink dark:text-white sm:text-5xl">
            GhostGuard vs. The Old Way.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border dark:border-slate-800">
                <th className="py-6 px-4 text-left text-sm font-black uppercase tracking-widest text-ink-tertiary dark:text-gray-500">Feature</th>
                <th className="py-6 px-4 text-center">
                  <div className="inline-flex flex-col items-center">
                    <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white shadow-lg shadow-brand/20">
                      <Shield className="h-5 w-5" />
                    </div>
                    <span className="text-lg font-black text-ink dark:text-white">GhostGuard</span>
                  </div>
                </th>
                <th className="py-6 px-4 text-center">
                  <div className="inline-flex flex-col items-center opacity-50">
                    <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-500">
                      <Users className="h-5 w-5" />
                    </div>
                    <span className="text-lg font-black text-ink dark:text-white">Manual Audits</span>
                  </div>
                </th>
                <th className="py-6 px-4 text-center">
                  <div className="inline-flex flex-col items-center opacity-50">
                    <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-500">
                      <Clock className="h-5 w-5" />
                    </div>
                    <span className="text-lg font-black text-ink dark:text-white">Legacy HRIS</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {features.map((f, i) => (
                <motion.tr 
                  key={f.name}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="border-b border-border dark:border-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors"
                >
                  <td className="py-6 px-4 text-sm font-bold text-ink dark:text-gray-300">{f.name}</td>
                  <td className="py-6 px-4 text-center">
                    {typeof f.ghostguard === 'boolean' ? (
                      <div className="flex justify-center"><Check className="h-6 w-6 text-emerald-500" /></div>
                    ) : (
                      <span className="text-sm font-black text-emerald-500">{f.ghostguard}</span>
                    )}
                  </td>
                  <td className="py-6 px-4 text-center opacity-40">
                    {typeof f.manual === 'boolean' ? (
                      <div className="flex justify-center"><X className="h-6 w-6 text-red-500" /></div>
                    ) : (
                      <span className="text-sm font-bold text-ink dark:text-gray-400">{f.manual}</span>
                    )}
                  </td>
                  <td className="py-6 px-4 text-center opacity-40">
                    {typeof f.legacy === 'boolean' ? (
                      <div className="flex justify-center"><X className="h-6 w-6 text-red-500" /></div>
                    ) : (
                      <span className="text-sm font-bold text-ink dark:text-gray-400">{f.legacy}</span>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-16 rounded-[40px] bg-brand/5 dark:bg-brand/10 p-10 flex flex-col md:flex-row items-center justify-between gap-8 border border-brand/20">
          <div className="flex items-center gap-6">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand text-white shadow-xl shadow-brand/20">
              <Zap className="h-8 w-8" />
            </div>
            <div>
              <h3 className="text-xl font-black text-ink dark:text-white">Ready for the upgrade?</h3>
              <p className="text-sm font-medium text-ink-secondary dark:text-gray-400">Join 120+ organisations who switched to automated verification.</p>
            </div>
          </div>
          <button className="h-14 px-10 rounded-2xl bg-brand text-white font-black text-lg shadow-lg shadow-brand/20 hover:scale-105 transition-transform">
            Switch to GhostGuard
          </button>
        </div>
      </div>
    </section>
  );
}
