"use client";

import Cookies from "js-cookie";
import type { UserType } from "@/types";

const cookieOptions: Cookies.CookieAttributes = {
  expires: 1 / 24 / 2, // 30 minutes
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
};

/**
 * Session storage helper - stores data in sessionStorage
 * Data is cleared when the browser tab is closed
 */
const sessionStorage_utils = {
  setItem: (key: string, value: string) => {
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.setItem(key, value);
      } catch (e) {
        console.warn("sessionStorage not available:", e);
      }
    }
  },
  getItem: (key: string) => {
    if (typeof window !== "undefined") {
      try {
        return window.sessionStorage.getItem(key);
      } catch (e) {
        console.warn("sessionStorage not available:", e);
      }
    }
    return null;
  },
  removeItem: (key: string) => {
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem(key);
      } catch (e) {
        console.warn("sessionStorage not available:", e);
      }
    }
  },
};

export function setTokens(accessToken: string, refreshToken: string, userType: UserType) {
  // Store in cookies (30-minute expiration)
  Cookies.set("access_token", accessToken, cookieOptions);
  Cookies.set("refresh_token", refreshToken, cookieOptions);


  // We no longer store tokens in client-side cookies. 
  // They are set as httpOnly cookies by the /api/auth routes.

  Cookies.set("user_type", userType, cookieOptions);

  // Also store in sessionStorage (cleared when tab closes)
  sessionStorage_utils.setItem("access_token", accessToken);
  sessionStorage_utils.setItem("refresh_token", refreshToken);
  sessionStorage_utils.setItem("user_type", userType);
}

export function clearTokens() {
  // Clear client-side cookies (js-cookie uses current path).
  Cookies.remove("access_token");
  Cookies.remove("refresh_token");
  Cookies.remove("user_type");

  // Clear httpOnly cookies server-side.
  fetch("/api/auth/logout", { method: "DELETE", keepalive: true });

  // Clear sessionStorage
  sessionStorage_utils.removeItem("access_token");
  sessionStorage_utils.removeItem("refresh_token");
  sessionStorage_utils.removeItem("user_type");
}

export function getAccessToken() {
  // First check sessionStorage (active session)
  const sessionToken = sessionStorage_utils.getItem("access_token");
  if (sessionToken) return sessionToken;

  // Fallback to cookies
  return Cookies.get("access_token");
}

export function getRefreshToken() {
  // First check sessionStorage (active session)
  const sessionToken = sessionStorage_utils.getItem("refresh_token");
  if (sessionToken) return sessionToken;

  // Fallback to cookies
  return Cookies.get("refresh_token");
}

export function getUserType(): UserType | null {
  // First check sessionStorage (active session)
  const sessionValue = sessionStorage_utils.getItem("user_type");
  if (sessionValue === "admin" || sessionValue === "worker" || sessionValue === "hr") {
    return sessionValue;
  }

  // Fallback to cookies
  const cookieValue = Cookies.get("user_type");
  return cookieValue === "admin" || cookieValue === "worker" || cookieValue === "hr" ? cookieValue : null;
}
