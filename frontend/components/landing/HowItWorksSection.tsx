"use client";

import { motion } from "framer-motion";
import { Brain, CreditCard, MapPin } from "lucide-react";
import useScrollAnimation from "@/hooks/useScrollAnimation";

export function HowItWorksSection() {
  useScrollAnimation();
  const steps = [
    { icon: MapPin, title: "Workers verify location", body: "GPS geofencing ensures workers physically check in from the office. Remote spoofing is detected instantly." },
    { icon: Brain, title: "AI scores every worker", body: "Our ML analyses signals across attendance, banking, and behaviour. Every worker gets a real-time Trust Score." },
    { icon: CreditCard, title: "BMONI pays verified list", body: "HR approves the clean list. BMONI API disburses salary directly to verified and active bank accounts." },
  ];

  return (
    <section id="how-it-works" className="bg-[#F8F7F2] dark:bg-slate-900 py-32 overflow-hidden transition-colors duration-500">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <p className="text-sm font-black uppercase tracking-[0.2em] text-brand mb-4">The Process</p>
          <h2 className="text-4xl font-black tracking-tight text-ink dark:text-white sm:text-5xl">From check-in to salary, verified.</h2>
        </motion.div>

        <div className="relative mt-14 grid gap-10 md:grid-cols-3">
          {/* Connecting Line */}
          <div className="absolute left-[15%] right-[15%] top-10 hidden h-[2px] bg-border dark:bg-slate-800 md:block">
            <motion.div 
              initial={{ width: 0 }}
              whileInView={{ width: "100%" }}
              viewport={{ once: true }}
              transition={{ duration: 1.5, ease: "easeInOut", delay: 0.5 }}
              className="h-full bg-brand"
            />
          </div>

          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <motion.div 
                key={step.title} 
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: 0.2 + index * 0.2 }}
                className="relative flex flex-col items-center text-center group"
              >
                <div className="relative z-10 mb-8 flex h-20 w-20 items-center justify-center rounded-[24px] bg-white dark:bg-slate-800 border-2 border-border dark:border-slate-700 text-brand group-hover:border-brand group-hover:bg-brand group-hover:text-white transition-all duration-300 shadow-soft">
                  <Icon className="h-10 w-10" />
                  <motion.div 
                    animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.6, 0.3] }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="absolute -inset-2 rounded-[28px] border-2 border-brand/20 -z-10"
                  />
                  <div className="absolute -top-3 -right-3 h-8 w-8 rounded-full bg-brand text-white flex items-center justify-center text-xs font-black ring-4 ring-[#F8F7F2] dark:ring-slate-900">
                    {index + 1}
                  </div>
                </div>
                
                <h3 className="text-xl font-black text-ink dark:text-white">{step.title}</h3>
                <p className="mt-4 text-sm font-medium leading-relaxed text-ink-secondary dark:text-gray-400 px-4">{step.body}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
