"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { BadgeCheck, Landmark, ReceiptText, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import useScrollAnimation from "@/hooks/useScrollAnimation";

export function BmoniSection() {
  useScrollAnimation();
  const items = [
    { icon: BadgeCheck, title: "Bank Verification", body: "BMONI confirms every worker's account name matches their government identity." },
    { icon: Landmark, title: "Salary Disbursement", body: "BMONI pays verified workers directly through instant transfers after HR approval." },
    { icon: ReceiptText, title: "Tamper-Evident Receipts", body: "Every payment generates a unique BMONI transaction ID linked permanently to attendance records." },
  ];

  return (
    <section className="bg-white dark:bg-[#0A0D12] py-32 text-ink dark:text-white overflow-hidden relative transition-colors duration-500">
      <div className="orb w-[400px] h-[400px] bg-brand/10 -bottom-20 -left-20 blur-[100px] opacity-30" />
      
      <div className="relative z-10 mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <p className="text-sm font-black uppercase tracking-[0.2em] text-brand mb-4">Secure Infrastructure</p>
          <h2 className="text-4xl font-black tracking-tight sm:text-5xl max-w-2xl leading-[1.1]">
            Built on BMONI's premium payment infrastructure.
          </h2>
        </motion.div>

        <div className="mt-16 grid gap-6">
          {items.map((item, i) => {
            const Icon = item.icon;
            return (
              <motion.div 
                key={item.title} 
                initial={{ opacity: 0, x: -50 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.15 }}
                className="flex flex-col gap-6 rounded-[32px] border border-black/5 dark:border-white/10 bg-black/5 dark:bg-white/5 p-8 sm:flex-row sm:items-center hover:bg-black/10 dark:hover:bg-white/10 transition-colors group"
              >
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-brand/10 text-brand group-hover:rotate-12 transition-transform duration-300">
                  <Icon className="h-9 w-9" />
                </div>
                <div>
                  <h3 className="text-xl font-black">{item.title}</h3>
                  <p className="mt-2 text-sm font-medium text-ink-secondary dark:text-gray-400 leading-relaxed">{item.body}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
        
        <motion.p 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.8 }}
          className="mt-10 text-xs font-bold uppercase tracking-widest text-brand-light/40"
        >
          GhostGuard uses BMONI's sandbox API and is production-ready for the Nigerian market.
        </motion.p>
      </div>
    </section>
  );
}
