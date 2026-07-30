"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Plus, Minus, HelpCircle } from "lucide-react";
import { useState } from "react";

const faqs = [
  {
    question: "How does GPS Geofencing prevent spoofing?",
    answer: "We use device-level hardware signals and background consistency checks. If a worker uses a GPS spoofing app or VPN, our algorithm detects the lack of satellite drift and hardware variances, flagging the check-in instantly."
  },
  {
    question: "What is Bank Account Velocity?",
    answer: "It's a fraud signal that tracks how often bank accounts are shared or rotated across the payroll. Ghost workers often use 'burner' accounts or share one account with an insider. We flag these patterns before disbursement."
  },
  {
    question: "Do we need special hardware to use GhostGuard?",
    answer: "No. GhostGuard works on any standard smartphone (Android or iOS). For organisations without company devices, we support 'Bring Your Own Device' (BYOD) with strict privacy controls."
  },
  {
    question: "How does the BMONI API integration work?",
    answer: "Once HR approves the 'Verified' payroll list, GhostGuard communicates with BMONI's disbursement engine to send salaries directly to the verified bank accounts. This eliminates manual file uploads where fraud often occurs."
  },
  {
    question: "Is worker data secure?",
    answer: "We use bank-grade encryption (AES-256) for all data at rest and TLS 1.3 for data in transit. We are fully compliant with NDPR (Nigeria Data Protection Regulation) standards."
  }
];

export function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section id="faq" className="bg-white dark:bg-slate-950 py-32 transition-colors duration-500">
      <div className="mx-auto max-w-4xl px-6 lg:px-8">
        <div className="text-center mb-20">
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-brand mb-4">Support</h2>
          <p className="text-4xl font-black tracking-tight text-ink dark:text-white sm:text-5xl">
            Commonly asked questions.
          </p>
        </div>

        <div className="space-y-4">
          {faqs.map((faq, i) => (
            <div 
              key={i} 
              className="group rounded-3xl border border-border dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-300"
            >
              <button
                onClick={() => setOpenIndex(openIndex === i ? null : i)}
                className="flex w-full items-center justify-between p-8 text-left"
              >
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/5 text-brand dark:bg-brand/10">
                    <HelpCircle className="h-5 w-5" />
                  </div>
                  <span className="text-lg font-bold text-ink dark:text-white">{faq.question}</span>
                </div>
                <div className={`flex h-8 w-8 items-center justify-center rounded-full border border-border dark:border-slate-700 transition-transform duration-300 ${openIndex === i ? 'rotate-180 bg-brand border-brand text-white' : 'text-ink dark:text-gray-400'}`}>
                  {openIndex === i ? <Minus className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                </div>
              </button>
              
              <AnimatePresence>
                {openIndex === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3, ease: "easeInOut" }}
                    className="overflow-hidden"
                  >
                    <div className="p-8 pt-0 text-ink-secondary dark:text-gray-400 font-medium leading-relaxed">
                      <div className="h-px bg-border dark:bg-slate-800 mb-8" />
                      {faq.answer}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>

        <div className="mt-20 text-center">
          <p className="text-ink-secondary dark:text-gray-500 font-bold mb-6">Still have questions?</p>
          <button className="rounded-2xl bg-brand/10 px-8 py-4 text-sm font-black text-brand hover:bg-brand/20 transition-colors">
            Contact Support Team
          </button>
        </div>
      </div>
    </section>
  );
}
