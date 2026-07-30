import { HrRegisterWithCodeForm } from "@/components/auth/HrRegisterWithCodeForm";
import AuthLayout from "@/components/auth/AuthLayout";

export default function HrRegisterPage() {
  return (
    <AuthLayout
      portal="hr"
      title="Review and approve payroll with confidence."
      subtitle="HR Registration"
      heroImageUrl="https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=600&q=80"
      features={[
        "Review flagged payroll anomalies",
        "Make informed payment decisions",
        "Ensure compliance across the organization"
      ]}
    >
      <HrRegisterWithCodeForm />
    </AuthLayout>
  );
}
