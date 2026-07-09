"use client";

import { useCallback, useState } from "react";
import ConnectionCard from "@/components/ConnectionCard";
import EmailTable from "@/components/EmailTable";
import SyncControls from "@/components/SyncControls";
import SyncProgress from "@/components/SyncProgress";

export default function SyncPage() {
  // Bumping streamKey (re)subscribes SyncProgress to a fresh /api/sync/progress stream.
  const [streamKey, setStreamKey] = useState(0);
  // Bumping syncVersion refetches EmailTable's rows/stats once a sync finishes.
  const [syncVersion, setSyncVersion] = useState(0);

  const handleSyncStarted = useCallback(() => {
    setStreamKey((k) => k + 1);
  }, []);

  const handleSyncFinished = useCallback(() => {
    setSyncVersion((v) => v + 1);
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <ConnectionCard />
      <SyncControls onSyncStarted={handleSyncStarted} />
      <SyncProgress streamKey={streamKey} onSyncFinished={handleSyncFinished} />
      <EmailTable refreshKey={syncVersion} />
    </div>
  );
}
