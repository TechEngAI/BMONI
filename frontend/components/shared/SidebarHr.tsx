"use client";

import { FileText, LayoutDashboard, Receipt } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import SidebarBase from "./SidebarBase";

const nav = [
  { label: "Dashboard", href: "/hr/dashboard", icon: LayoutDashboard },
  { label: "Payroll", href: "/hr/payroll", icon: FileText },
  { label: "Receipts", href: "/hr/receipts", icon: Receipt },
];

export function SidebarHr() {
  const { user } = useAuth();
  const hrName = `${String(user?.first_name || "HR")} ${String(user?.last_name || "Officer")}`.trim();

  return (
    <SidebarBase
      portal="hr"
      userName={hrName}
      userRole="HR Officer"
      companyName={String(user?.company_name || "Company workspace")}
      navItems={nav}
      logoutPath="/hr/login"
    />
  );
}
