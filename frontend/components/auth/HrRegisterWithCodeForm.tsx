"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { OtpInput } from "@/components/ui/OtpInput";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { PasswordStrength } from "@/components/ui/PasswordStrength";
import { StepIndicator } from "@/components/ui/StepIndicator";
import { unwrapError, hrRegisterWithCode, hrResendOtp, hrVerifyOtp } from "@/lib/api";
import { setTokens } from "@/lib/auth";

const schema = z
  .object({
    invite_code: z.string().min(1, "Invite code is required"),
    first_name: z.string().min(1, "First name is required"),
    last_name: z.string().min(1, "Last name is required"),
    email: z.string().email(),
    phone_number: z.string().regex(/^0\d{10}$/, "Phone must be 11 digits starting with 0"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string(),
  })
  .refine((data) => data.password === data.confirm_password, { message: "Passwords do not match", path: ["confirm_password"] });

type Values = z.infer<typeof schema>;

export function HrRegisterWithCodeForm() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [otp, setOtp] = useState("");
  const { register, trigger, watch, getValues, handleSubmit, formState, setError } = useForm<Values>({
    resolver: zodResolver(schema),
  });

  async function next(fields: Array<keyof Values>) {
    if (await trigger(fields)) setStep((value) => value + 1);
  }

  async function createAccount() {
    try {
      await hrRegisterWithCode(getValues());
      toast.success("Account created. Check your email to verify.");
      setStep(3);
    } catch (error: any) {
      const code = error?.response?.data?.error?.code;
      if (code === "INVALID_INVITE_CODE") {
        setStep(1);
        setError("invite_code", { message: "Invalid or expired invite code." });
        return;
      }
      toast.error(unwrapError(error));
    }
  }

  async function verify() {
    try {
      const response = await hrVerifyOtp({ email: getValues("email"), otp });
      const data = response.data.data;
      if (data.access_token) setTokens(data.access_token, data.refresh_token, "hr");
      toast.success("Account verified.");
      router.push("/hr/receipts");
    } catch (error) {
      toast.error(unwrapError(error));
      setOtp("");
    }
  }

  const password = watch("password") || "";
  return (
    <div className="mx-auto max-w-3xl rounded-xl border border-border bg-white p-6 shadow-soft">
      <StepIndicator steps={["Invite Code", "Your Details", "Verify OTP"]} currentStep={step} />
      <div className="mt-8">
        {step === 1 && (
          <div className="mx-auto max-w-lg space-y-4 text-center">
            <Input label="Invite code" placeholder="Enter your HR invite code" error={formState.errors.invite_code?.message} {...register("invite_code")} />
            <Button type="button" onClick={() => next(["invite_code"])}>Continue</Button>
          </div>
        )}
        {step === 2 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Input label="First name" error={formState.errors.first_name?.message} {...register("first_name")} />
            <Input label="Last name" error={formState.errors.last_name?.message} {...register("last_name")} />
            <Input label="Email" type="email" error={formState.errors.email?.message} {...register("email")} />
            <Input label="Phone number" error={formState.errors.phone_number?.message} {...register("phone_number")} />
            <div><PasswordInput label="Password" error={formState.errors.password?.message} {...register("password")} /><PasswordStrength password={password} /></div>
            <PasswordInput label="Confirm password" error={formState.errors.confirm_password?.message} {...register("confirm_password")} />
            <div className="md:col-span-2 flex gap-3"><Button type="button" variant="secondary" onClick={() => setStep(1)}>Back</Button><Button type="button" onClick={handleSubmit(createAccount)}>Create Account</Button></div>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-6 text-center">
            <h2 className="text-2xl font-bold">Verify your account</h2>
            <OtpInput value={otp} onChange={setOtp} />
            <Button type="button" disabled={otp.length !== 6} onClick={verify}>Verify</Button>
            <button type="button" className="block w-full text-sm font-semibold text-brand" onClick={() => hrResendOtp({ email: getValues("email") })}>Resend code</button>
          </div>
        )}
      </div>
    </div>
  );
}
