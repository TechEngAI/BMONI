"use client";

/**
 * PRIVACY NOTICE — REQUIRED DISCLOSURE:
 *
 * This function generates a stable device fingerprint using browser properties
 * (user agent, screen resolution, timezone, language). Combined with server-side
 * IP address geolocation, this constitutes monitoring of worker devices and
 * locations. You MUST disclose this in your organisation's privacy/terms notice:
 *
 *   "We collect device fingerprint information (browser type, screen resolution,
 *    timezone, language setting) and IP address location data to verify remote
 *    work check-ins and detect fraud. This data is used solely for payroll
 *    integrity purposes and is not sold or shared with third parties."
 *
 * This is NOT invasive biometric data, but transparency is an ethical requirement
 * for responsible workforce monitoring.
 */

export async function generateDeviceFingerprint(): Promise<string> {
  const raw = [
    navigator.userAgent,
    screen.width + "x" + screen.height,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
  ].join("|||");

  const encoder = new TextEncoder();
  const data = encoder.encode(raw);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}
