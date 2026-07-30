"use client";

import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { CheckInCard } from "@/components/worker/CheckInCard";
import { DataDisclosureBanner } from "@/components/worker/DataDisclosureBanner";
import { GpsStatusIndicator } from "@/components/worker/GpsStatusIndicator";
import { checkIn, checkOut, getTodayAttendance, getWorkerProfile, remoteCheckIn, unwrapError } from "@/lib/api";
import { unwrapData } from "@/lib/utils";
import { generateDeviceFingerprint } from "@/lib/fingerprint";
import { useDeviceFingerprint } from "@/hooks/useDeviceFingerprint";
import { useGps } from "@/hooks/useGps";

function distanceMetres(aLat?: number | null, aLng?: number | null, bLat?: number | null, bLng?: number | null) {
  if (aLat == null || aLng == null || bLat == null || bLng == null) return null;
  const r = 6371000;
  const p1 = (aLat * Math.PI) / 180;
  const p2 = (bLat * Math.PI) / 180;
  const dp = ((bLat - aLat) * Math.PI) / 180;
  const dl = ((bLng - aLng) * Math.PI) / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

import PageWrapper from "@/components/shared/PageWrapper";

export default function WorkerDashboardPage() {
  const [today, setToday] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const { gps, getLocation } = useGps();
  const deviceId = useDeviceFingerprint();

  useEffect(() => {
    getLocation().catch(() => {}); // Initial location fetch
    let cancelled = false;
    async function load() {
      try {
        const [todayRes, profileRes] = await Promise.all([getTodayAttendance(), getWorkerProfile()]);
        if (cancelled) return;
        const prof = unwrapData<any>(profileRes).worker || unwrapData<any>(profileRes);
        setProfile(prof);
        setToday(unwrapData<any>(todayRes));

        if (prof?.work_mode === "remote") {
          generateDeviceFingerprint().then((fingerprint) => {
            remoteCheckIn({ device_fingerprint: fingerprint }).catch(() => {});
          });
        }
      } catch (error) {
        toast.error(unwrapError(error));
      }
    }
    load();
    return () => { cancelled = true; };
  }, [getLocation]);

  const company = profile?.companies || profile?.company || {};
  const isRemote = profile?.roles?.work_type === "REMOTE";
  const distance = useMemo(() => distanceMetres(gps.latitude, gps.longitude, Number(company.office_lat), Number(company.office_lng)), [gps.latitude, gps.longitude, company.office_lat, company.office_lng]);
  const status = today?.status || "NOT_CHECKED_IN";
  const inRange = isRemote || distance == null || distance <= Number(company.geofence_radius || 100);

  async function doCheckIn() {
    setLoading(true);
    try {
      const coords = await getLocation();
      const response = await checkIn({ 
        latitude: coords.latitude, 
        longitude: coords.longitude, 
        accuracy: gps.accuracy, 
        device_id: deviceId, 
        user_agent: navigator.userAgent 
      });
      toast.success("Checked in! Have a great day.");
      if ((unwrapData<any>(response).fraud_signals_detected || []).length) toast("Note: anomaly recorded. Contact admin.");
      const next = await getTodayAttendance();
      setToday(unwrapData<any>(next));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : unwrapError(error));
    } finally {
      setLoading(false);
    }
  }

  async function doCheckOut() {
    setLoading(true);
    try {
      const coords = await getLocation();
      const response = await checkOut({ 
        latitude: coords.latitude, 
        longitude: coords.longitude,
        accuracy: gps.accuracy
      });
      toast.success(`Checked out. You worked ${unwrapData<any>(response).hours_worked || 0}h today.`);
      const next = await getTodayAttendance();
      setToday(unwrapData<any>(next));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : unwrapError(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageWrapper className="p-8 max-w-2xl mx-auto">
      <DataDisclosureBanner />
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-black tracking-tight text-ink">Worker Dashboard</h1>
        <p className="text-sm font-medium text-ink-secondary mt-1">
          {profile ? `Welcome back, ${profile.first_name}` : "Check in to start your workday"}
        </p>
      </div>

      <div className="space-y-6">
        <CheckInCard today={today} />
        
        {status === "NOT_CHECKED_IN" && (
          <GpsStatusIndicator 
            gps={gps} 
            isRemote={isRemote} 
            distance={distance} 
            radius={Number(company.geofence_radius || 100)} 
            onRetry={getLocation} 
          />
        )}
      </div>
    </PageWrapper>
  );
}
