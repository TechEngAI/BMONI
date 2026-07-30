"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import Link from "next/link";
import { ArrowRight, Bot, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { CountUpNumber } from "@/components/shared/CountUpNumber";
import useScrollAnimation from "@/hooks/useScrollAnimation";

export function HeroSection() {
  const { scrollY } = useScroll();
  const y1 = useTransform(scrollY, [0, 500], [0, 150]);
  const y2 = useTransform(scrollY, [0, 500], [0, -100]);
  
  useScrollAnimation();

  const headline = "Stop Paying Ghost Workers.";
  const words = headline.split(" ");

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1, delayChildren: 0.3 }
    }
  };

  const item = {
    hidden: { opacity: 0, y: 30 },
    show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] as any } }
  };

  return (
    <section id="home" className="relative min-h-screen bg-white dark:bg-[#0A0D12] text-white dark:text-white overflow-hidden pt-20 transition-colors duration-500">
      {/* Video Background */}
      <motion.video 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2 }}
        autoPlay 
        muted 
        loop 
        playsInline 
        className="hero-video hidden lg:block"
        src="/videos/hero-bg.mp4"
      />
      <div className="video-overlay hidden lg:block bg-white/30 dark:bg-black/40" />

      {/* Background Orbs */}
      <div className="orb w-[600px] h-[600px] bg-brand/20 -top-40 -left-40 blur-[120px] opacity-20 z-[2]" />
      <div className="orb w-[500px] h-[500px] bg-brand-dark/30 bottom-0 right-0 blur-[100px] opacity-20 z-[2]" />
      <div className="animated-grid absolute inset-0 opacity-20 pointer-events-none z-[2]" />

      <div className="relative z-10 mx-auto grid min-h-[calc(100vh-80px)] max-w-7xl items-center gap-16 px-6 sm:px-8 lg:grid-cols-[1.1fr_0.9fr]">
        <motion.div 
          style={{ y: y1 }}
          variants={container}
          initial="hidden"
          animate="show"
        >
          <motion.div 
            variants={item}
            className="mb-8 inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-400/5 px-4 py-2 text-xs font-bold text-amber-200 tracking-wider uppercase"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            </span>
            Powered by BMONI API
          </motion.div>

          <h1 className="text-6xl font-black leading-[1.05] md:text-8xl tracking-tight text-ink dark:text-white">
            {words.map((word, i) => (
              <motion.span 
                key={i} 
                className={`inline-block mr-[0.2em] last:mr-0 ${word === "Ghost" ? "gradient-text" : ""}`}
                variants={item}
              >
                {word}
              </motion.span>
            ))}
          </h1>

          <motion.p 
            variants={item}
            className="mt-8 max-w-xl text-lg leading-relaxed text-ink-secondary dark:text-gray-400 font-medium"
          >
            GhostGuard uses GPS verification, AI anomaly detection, and BMONI-powered payroll to eliminate ghost workers from your payroll automatically.
          </motion.p>

          <motion.div 
            variants={item}
            className="mt-10 flex flex-col gap-4 sm:flex-row items-center"
          >
            <Link href="/admin/register" className="w-full sm:w-auto">
              <Button className="w-full h-14 px-8 rounded-2xl font-black text-lg shadow-2xl shadow-brand/20 group">
                Start as Admin <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Button>
            </Link>
            <Link href="/worker/register" className="w-full sm:w-auto">
              <Button variant="secondary" className="w-full h-14 px-8 border-white/10 bg-white/5 text-white hover:bg-white/10 rounded-2xl font-bold text-lg backdrop-blur-sm">
                I'm a Worker
              </Button>
            </Link>
          </motion.div>

          <motion.div 
            variants={item}
            className="mt-12 flex flex-wrap gap-4"
          >
            {[
              { label: 200, prefix: "NGN ", suffix: "B+", sub: "lost yearly" },
              { label: 99, prefix: "", suffix: "%", sub: "detection rate" },
              { label: 10, prefix: "", suffix: "+", sub: "fraud signals" },
            ].map((stat, i) => (
              <div key={i} className="flex flex-col rounded-2xl bg-white/50 dark:bg-white/5 border border-black/5 dark:border-white/10 px-6 py-3 backdrop-blur-md">
                <CountUpNumber value={stat.label} prefix={stat.prefix} suffix={stat.suffix} className="text-xl font-black text-brand" />
                <span className="text-[10px] font-bold text-gray-500 dark:text-gray-500 uppercase tracking-widest">{stat.sub}</span>
              </div>
            ))}
          </motion.div>
        </motion.div>

        <motion.div 
          style={{ y: y2 }}
          initial={{ opacity: 0, x: 50, rotate: 2 }}
          animate={{ opacity: 1, x: 0, rotate: 0 }}
          transition={{ duration: 1, delay: 0.5, ease: [0.22, 1, 0.36, 1] as any }}
          className="hidden lg:block relative"
        >
          {/* Decorative elements behind card */}
          <div className="absolute -inset-4 bg-brand/10 blur-[60px] rounded-full opacity-50" />
          
          <div className="relative rounded-[32px] border border-black/5 dark:border-white/10 bg-white/80 dark:bg-[#151921]/80 p-8 shadow-2xl backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10">
            <div className="mb-8 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1">Payroll Analysis</p>
                <h2 className="text-3xl font-black tracking-tight">May Run</h2>
              </div>
              <div className="w-14 h-14 rounded-2xl bg-brand/10 dark:bg-brand/20 flex items-center justify-center text-brand">
                <Bot className="h-8 w-8" />
              </div>
            </div>

            <div className="space-y-4">
              {[
                { name: "Amina Yusuf", initials: "AY", score: 91, status: "VERIFIED", color: "text-brand bg-brand/10" },
                { name: "Chinedu Okafor", initials: "CO", score: 87, status: "VERIFIED", color: "text-brand bg-brand/10" },
                { name: "Tunde Bello", initials: "TB", score: 18, status: "FLAGGED", color: "text-red-500 bg-red-500/10" },
              ].map((worker, i) => (
                <motion.div 
                  key={worker.name} 
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 1 + i * 0.15 }}
                  className="flex items-center justify-between rounded-2xl bg-white p-5 shadow-sm group hover:scale-[1.02] transition-transform"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#F8F7F2] text-brand-dark font-black text-sm">
                      {worker.initials}
                    </div>
                    <div>
                      <p className="font-bold text-ink">{worker.name}</p>
                      <p className="text-xs font-semibold text-ink-tertiary">Trust score {worker.score}</p>
                    </div>
                  </div>
                  <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-wider ${worker.color}`}>
                    {worker.status}
                  </span>
                </motion.div>
              ))}
            </div>

            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.6 }}
              className="mt-10 p-6 rounded-2xl bg-white/5 border border-white/5"
            >
              <div className="mb-4 flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 font-bold text-gray-300">
                  <Zap className="h-4 w-4 text-brand" /> Analysis complete
                </span>
                <span className="font-black text-brand">100%</span>
              </div>
              <div className="h-3 rounded-full bg-white/10 overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 1.5, delay: 1.8, ease: "easeOut" }}
                  className="h-full bg-gradient-to-r from-brand to-brand-light shadow-[0_0_15px_rgba(29,158,117,0.5)]" 
                />
              </div>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
