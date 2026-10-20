import { useEffect, useState } from "react";
import { fetchPing } from "./api/ping";

type BackendState = "checking" | "online" | "offline";

export default function App() {
  const [backend, setBackend] = useState<BackendState>("checking");

  useEffect(() => {
    let cancelled = false;
    fetchPing()
      .then(() => !cancelled && setBackend("online"))
      .catch(() => !cancelled && setBackend("offline"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <h1 className="text-lg font-semibold">videocut</h1>
        <p className="text-sm text-neutral-400" role="status">
          Backend: {backend}
        </p>
      </header>
      <main className="p-4 text-sm text-neutral-400">
        Application shell. Upload and editing are not implemented yet.
      </main>
    </div>
  );
}
