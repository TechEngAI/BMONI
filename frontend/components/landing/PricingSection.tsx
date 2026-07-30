"use client";

import { motion } from "framer-motion";
import { Check, Zap } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";

const tiers = [
  {
    name: "Starter",
    price: { monthly: 0, yearly: 0 },
    description: "Perfect for small businesses testing the waters.",
    features: ["Up to 20 workers", "Basic GPS geofencing", "Standard anomaly scoring", "Mobile portal access"],
    cta: "Start for Free",
    popular: false
  },
  {
    name: "Pro",
    price: { monthly: 25000, yearly: 20000 },
    description: "Comprehensive fraud prevention for growing teams.",
    features: [
      "Up to 200 workers",
      "Advanced device fingerprinting",
      "BMONI API payroll integration",
      "Real-time fraud alerts",
      "Detailed trust score breakdown",
      "Priority support"
    ],
    cta: "Start 14-day Trial",
    popular: true
  },
  {
    name: "Enterprise",
    price: { monthly: "Custom", yearly: "Custom" },
    description: "Scalable solutions for large organisations.",
    features: [
      "Unlimited workers",
      "White-label portal",
      "Custom ML signal training",
      "On-premise deployment option",
      "Dedicated account manager",
      "SLA guarantees"
    ],
    cta: "Contact Sales",
    popular: false
  }
];

export function PricingSection() {
  const [isYearly, setIsYearly] = useState(false);

  return (
    <section id="pricing" className="bg-[#F8F7F2] dark:bg-slate-900 py-32 transition-colors duration-500">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-brand mb-4">Pricing Plans</h2>
          <p className="text-4xl font-black tracking-tight text-ink dark:text-white sm:text-5xl mb-12">
            Stop the bleed, start for free.
          </p>

          <div className="flex items-center justify-center gap-4">
            <span className={`text-sm font-bold ${!isYearly ? 'text-ink dark:text-white' : 'text-ink-tertiary dark:text-gray-500'}`}>Monthly</span>
            <button 
              onClick={() => setIsYearly(!isYearly)}
              className="relative h-8 w-14 rounded-full bg-border dark:bg-slate-800 p-1 transition-colors"
            >
              <motion.div 
                animate={{ x: isYearly ? 24 : 0 }}
                className="h-6 w-6 rounded-full bg-brand shadow-lg" 
              />
            </button>
            <span className={`text-sm font-bold ${isYearly ? 'text-ink dark:text-white' : 'text-ink-tertiary dark:text-gray-500'}`}>
              Yearly <span className="text-emerald-500 ml-1">(-20%)</span>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {tiers.map((tier) => (
            <motion.div
              key={tier.name}
              whileHover={{ y: -8 }}
              className={`relative flex flex-col justify-between rounded-[40px] p-10 bg-white dark:bg-slate-800 border-2 transition-all duration-300 shadow-soft ${tier.popular ? 'border-brand shadow-2xl shadow-brand/10' : 'border-border dark:border-slate-700'}`}
            >
              {tier.popular && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-brand text-white px-6 py-2 rounded-full text-xs font-black uppercase tracking-widest shadow-lg">
                  Most Popular
                </div>
              )}

              <div>
                <h3 className="text-2xl font-black text-ink dark:text-white mb-4">{tier.name}</h3>
                <div className="flex items-baseline gap-2 mb-6">
                  <span className="text-5xl font-black text-ink dark:text-white">
                    {typeof tier.price.monthly === 'number' 
                      ? `₦${(isYearly ? tier.price.yearly : tier.price.monthly).toLocaleString()}`
                      : tier.price.monthly}
                  </span>
                  {typeof tier.price.monthly === 'number' && (
                    <span className="text-ink-tertiary dark:text-gray-500 font-bold">/mo</span>
                  )}
                </div>
                <p className="text-sm font-medium text-ink-secondary dark:text-gray-400 leading-relaxed mb-10">
                  {tier.description}
                </p>

                <div className="space-y-4">
                  {tier.features.map((feature) => (
                    <div key={feature} className="flex items-center gap-3">
                      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-brand/10 text-brand">
                        <Check className="h-3 w-3" />
                      </div>
                      <span className="text-sm font-bold text-ink-secondary dark:text-gray-300">{feature}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-12">
                <Button 
                  variant={tier.popular ? "default" : "secondary"}
                  className={`w-full h-14 rounded-2xl font-black text-lg ${tier.popular ? 'glow-pulse' : 'bg-brand/5 dark:bg-slate-900 border-brand/20 dark:border-slate-700 text-brand dark:text-white'}`}
                >
                  {tier.cta}
                </Button>
              </div>
            </motion.div>
          ))}
        </div>

        <div className="mt-20 flex flex-col items-center justify-center gap-8 md:flex-row">
          <div className="flex items-center gap-3">
            <Zap className="h-6 w-6 text-brand" />
            <span className="text-lg font-bold text-ink dark:text-white">Custom deployment available</span>
          </div>
          <div className="h-px w-20 bg-border dark:bg-slate-800 hidden md:block" />
          <p className="text-sm font-medium text-ink-secondary dark:text-gray-500">
            Need a custom integration? <button className="text-brand font-black underline underline-offset-4">Talk to our engineers</button>
          </p>
        </div>
      </div>
    </section>
  );
}
