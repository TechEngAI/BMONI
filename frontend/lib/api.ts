"use client";

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { clearTokens, getUserType, setTokens } from "@/lib/auth";
import type { UserType } from "@/types";

type RetryConfig = InternalAxiosRequestConfig & { _retry?: boolean };

export const api = axios.create({
  baseURL: "/api/proxy",
  headers: { "Content-Type": "application/json" },
});

const loginPath = (type: UserType | null) => `/${type || "admin"}/login`;

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;
    const userType = getUserType();
    
    if (error.response?.status === 401 && original && !original._retry && userType) {
      original._retry = true;
      try {
        await axios.post(`/api/auth/${userType}/refresh`);
        return api(original);
      } catch {
        clearTokens();
        if (typeof window !== "undefined") window.location.href = loginPath(userType);
      }
    }
    return Promise.reject(error);
  },
);

export const unwrapError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.error?.message || error.response?.data?.message || "Request failed.";
  }
  return "Something went wrong.";
};

export const authApi = axios.create({
  baseURL: "/api/auth",
  headers: { "Content-Type": "application/json" },
});

export const adminRegister = (data: unknown) => authApi.post("/admin/register", data);
export const adminVerifyOtp = (data: unknown) => authApi.post("/admin/verify-otp", data);
export const adminResendOtp = (data: unknown) => authApi.post("/admin/resend-otp", data);
export const adminLogin = (data: unknown) => authApi.post("/admin/login", data);
export const adminForgotPassword = (data: unknown) => authApi.post("/admin/forgot-password", data);
export const adminResetPassword = (data: unknown) => authApi.post("/admin/reset-password", data);

export const workerRegister = (data: unknown) => authApi.post("/worker/register", data);
export const workerVerifyOtp = (data: unknown) => authApi.post("/worker/verify-otp", data);
export const workerResendOtp = (data: unknown) => authApi.post("/worker/resend-otp", data);
export const workerLogin = (data: unknown) => authApi.post("/worker/login", data);
export const workerForgotPassword = (data: unknown) => authApi.post("/worker/forgot-password", data);
export const workerResetPassword = (data: unknown) => authApi.post("/worker/reset-password", data);

export const hrRegisterWithCode = (data: unknown) => authApi.post("/hr/register-with-code", data);
export const hrVerifyOtp = (data: unknown) => authApi.post("/hr/verify-otp", data);
export const hrResendOtp = (data: unknown) => authApi.post("/hr/resend-otp", data);
export const hrLogin = (data: unknown) => authApi.post("/hr/login", data);
export const hrForgotPassword = (data: unknown) => authApi.post("/hr/forgot-password", data);
export const hrResetPassword = (data: unknown) => authApi.post("/hr/reset-password", data);

export const getCompany = () => api.get("/admin/company");
export const updateCompany = (data: unknown) => api.put("/admin/company", data);

export const getWorkerProfile = () => api.get("/worker/profile");
export const updateWorkerProfile = (data: unknown) => api.put("/worker/profile", data);
export const bankLookup = (data: unknown) => {
  const payload = data as Record<string, any>;
  return api.post("/worker/bank/lookup", {
    account_number: String(payload.account_number),
    bank_code: String(payload.bank_code),
  }, { headers: { "Content-Type": "application/json" } });
};
export const bankSubmit = (data: unknown) => {
  const payload = data as Record<string, any>;
  return api.post("/worker/bank/submit", {
    account_number: String(payload.account_number),
    bank_code: String(payload.bank_code),
    bank_name: payload.bank_name,
    confirmed_account_name: payload.confirmed_account_name,
  }, { headers: { "Content-Type": "application/json" } });
};
export const getWorkerBank = () => api.get("/worker/bank");

// ROLES
export const getRoles = () => api.get("/admin/roles");
export const createRole = (data: unknown) => api.post("/admin/roles", data);
export const updateRole = (id: string, data: unknown) => api.put(`/admin/roles/${id}`, data);
export const regenerateCode = (id: string) => api.post(`/admin/roles/${id}/regenerate-code`);
export const deleteRole = (id: string) => api.delete(`/admin/roles/${id}`);

// WORKERS (admin view)
export const getWorkers = (params?: unknown) => api.get("/admin/workers", { params });
export const getWorkerDetail = (id: string) => api.get(`/admin/workers/${id}`);
export const verifyWorkerBank = (id: string, data: unknown) => api.patch(`/admin/workers/${id}/verify-bank`, data);
export const suspendWorker = (id: string, data: unknown) => api.patch(`/admin/workers/${id}/suspend`, data);
export const reactivateWorker = (id: string) => api.patch(`/admin/workers/${id}/reactivate`);
export const reassignWorker = (id: string, data: unknown) => api.patch(`/admin/workers/${id}/reassign`, data);
export const deleteWorker = (id: string) => api.delete(`/admin/workers/${id}`);

// HR OFFICERS (admin view)
export const getHrOfficers = () => api.get("/admin/hr");
export const createHrOfficer = (data: unknown) => api.post("/admin/hr/create", data);
export const suspendHrOfficer = (id: string) => api.patch(`/admin/hr/${id}/suspend`);
export const reactivateHrOfficer = (id: string) => api.patch(`/admin/hr/${id}/reactivate`);
export const deleteHrOfficer = (id: string) => api.delete(`/admin/hr/${id}`);

// FRAUD SIGNALS
export const getFraudSignals = (params?: unknown) => api.get("/admin/fraud-signals", { params });

// REMOTE CHECK-IN
export const remoteCheckIn = (data: unknown) => api.post("/worker/remote/checkin", data);

// ATTENDANCE
export const checkIn = (data: unknown) => api.post("/worker/attendance/checkin", data);
export const checkOut = (data: unknown) => api.post("/worker/attendance/checkout", data);
export const getTodayAttendance = () => api.get("/worker/attendance/today");
export const getAttendanceHistory = (params?: unknown) => api.get("/worker/attendance/history", { params });
export const getWorkerAttendanceAdmin = (workerId: string, params?: unknown) => api.get(`/admin/attendance/${workerId}`, { params });
export const editAttendanceRecord = (recordId: string, data: unknown) => api.patch(`/admin/attendance/${recordId}/edit`, data);

// PAYROLL (admin trigger)
export const generatePayroll = (data: unknown) => api.post("/admin/payroll/generate", data);
export const getPayrollRuns = () => api.get("/admin/payroll/runs");
export const getPayrollResults = (runId: string, params?: unknown) => api.get(`/admin/payroll/${runId}/results`, { params });
export const downloadPayrollCsv = (runId: string) => api.get(`/admin/payroll/${runId}/csv`, { responseType: "blob" });

// HR PAYROLL
export const getHrPayrollRuns = () => api.get("/hr/payroll/runs");
export const getHrPayrollResults = (runId: string, params?: unknown) => api.get(`/hr/payroll/${runId}/results`, { params });
export const makeWorkerDecision = (runId: string, workerId: string, data: unknown) => api.patch(`/hr/payroll/${runId}/worker/${workerId}/decision`, data);
export const approvePayroll = (runId: string) => api.post(`/hr/payroll/${runId}/approve`);

// HR RECEIPTS
export const getHrAllReceipts = (params?: any) =>
  api.get("/hr/receipts", { params });
export const getPayrollReceipts = (runId: string, params?: any) =>
  api.get(`/hr/payroll/${runId}/receipts`, { params });

export const downloadReceiptsCsv = (runId: string) =>
  api.get(`/hr/payroll/${runId}/receipts/download`, { responseType: "blob" });

export const retryFailedPayment = (runId: string, receiptId: string) =>
  api.patch(`/hr/payroll/${runId}/receipt/${receiptId}/retry`);

export const getHrWalletBalance = () => api.get("/hr/payroll/wallet-balance");

// ADMIN — refresh a stuck PENDING receipt status from BMONI
export const refreshReceiptStatus = (receiptId: string) =>
  api.post(`/admin/payroll/receipts/${receiptId}/refresh-status`);

// WORKER PAYSLIP
export const getWorkerPayslip = (params?: { month_year?: string }) =>
  api.get("/worker/payslip", { params });

export const getWorkerPayslips = () =>
  api.get("/worker/payslips");

// ADMIN ANALYTICS
export const getAnalyticsSummary = () =>
  api.get("/admin/analytics/summary");

export const getPayrollHistory = () =>
  api.get("/admin/analytics/payroll-history");

export const getFraudBreakdown = () =>
  api.get("/admin/analytics/fraud-breakdown");

// WALLET
export const getWallet = () => api.get("/admin/wallet");
export const getWalletBalance = () => api.get("/admin/wallet/balance");
export const initiateDeposit = (data: { amount_ngn: number }) =>
  api.post("/admin/wallet/initiate-deposit", data);
export const getWalletTransactions = (params?: any) =>
  api.get("/admin/wallet/transactions", { params });

export const getTopRiskWorkers = (limit = 10) =>
  api.get("/admin/analytics/top-risk-workers", { params: { limit } });

export const getAttendanceOverview = (month_year?: string) =>
  api.get("/admin/analytics/attendance-overview", { params: { month_year } });
