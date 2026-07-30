"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { BriefcaseBusiness, HeartHandshake, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { adminLogin, getCompany, hrLogin, unwrapError, workerLogin } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { UserType } from "@/types";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

const config = {
  admin: { label: "Admin Portal", accent: "text-admin", icon: ShieldCheck, login: adminLogin, dashboard: "/admin/dashboard", register: "/admin/register" },
  worker: { label: "Worker Portal", accent: "text-worker", icon: BriefcaseBusiness, login: workerLogin, dashboard: "/worker/dashboard", register: "/worker/register" },
  hr: { label: "HR Portal", accent: "text-hr", icon: HeartHandshake, login: hrLogin, dashboard: "/hr/dashboard", register: "/hr/register" },
};

export function LoginForm({ type }: { type: UserType }) {
  const router = useRouter();
  const portal = config[type];
  const { register, handleSubmit, formState } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function submit(values: FormValues) {
    try {
      const response = await portal.login(values);
      const data = response.data.data;
      if (data.access_token) setTokens(data.access_token, data.refresh_token, type);
      toast.success("Welcome back.");
      if (type === "admin") {
        try {
          const company = (await getCompany()).data.data;
          const profile = company.company || company;
          router.push(profile.office_lat ? "/admin/dashboard" : "/admin/setup");
          return;
        } catch {
          router.push("/admin/setup");
          return;
        }
      }
      router.push(portal.dashboard);
    } catch (error) {
      toast.error(unwrapError(error));
    }
  }

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const item = {
    hidden: { opacity: 0, y: 10 },
    show: { opacity: 1, y: 0 },
  };

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="w-full">
      <form className="space-y-6" onSubmit={handleSubmit(submit)}>
        <motion.div variants={item}>
          <Input 
            label="Email address" 
            type="email" 
            placeholder="name@company.com"
            error={formState.errors.email?.message} 
            {...register("email")} 
          />
        </motion.div>
        
        <motion.div variants={item}>
          <PasswordInput 
            label="Password" 
            placeholder="••••••••"
            error={formState.errors.password?.message} 
            {...register("password")} 
          />
          <div className="flex justify-end mt-1.5">
            <Link 
              href={`/reset-password?type=${type}`} 
              className={cn("text-xs font-bold transition-colors", portal.accent, "hover:opacity-80")}
            >
              Forgot password?
            </Link>
          </div>
        </motion.div>

        <motion.div variants={item}>
          <Button 
            className={cn("w-full h-12 rounded-xl text-sm font-bold shadow-soft transition-all hover:scale-[1.02] active:scale-[0.98]")}
            isLoading={formState.isSubmitting}
          >
            Login to {portal.label}
          </Button>
        </motion.div>
      </form>

      <motion.div variants={item} className="mt-8 pt-6 border-t border-border dark:border-slate-800">
        {type === "admin" && (
          <p className="text-center text-sm text-ink-secondary dark:text-gray-400 font-medium">
            Don't have an account?{" "}
            <Link className="font-bold text-brand hover:underline underline-offset-4" href="/admin/register">
              Create admin account
            </Link>
          </p>
        )}
        {type === "worker" && (
          <p className="text-center text-sm text-ink-secondary dark:text-gray-400 font-medium">
            New worker?{" "}
            <Link className="font-bold text-brand hover:underline underline-offset-4" href="/worker/register">
              Register with invite code
            </Link>
          </p>
        )}
        {type === "hr" && (
          <p className="text-center text-sm text-ink-secondary dark:text-gray-400 font-medium">
            New HR officer?{" "}
            <Link className="font-bold text-brand hover:underline underline-offset-4" href={portal.register}>
              Register with invite code
            </Link>
          </p>
        )}
      </motion.div>
    </motion.div>
  );
}
