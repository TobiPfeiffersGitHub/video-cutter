export type PingResult = { status: string };

export async function fetchPing(): Promise<PingResult> {
  const response = await fetch("/api/v1/ping");
  if (!response.ok) {
    throw new Error(`Backend responded with HTTP ${response.status}`);
  }
  return (await response.json()) as PingResult;
}
