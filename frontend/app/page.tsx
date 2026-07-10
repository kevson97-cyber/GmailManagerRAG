"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Client-side redirect: a server-side redirect() is unreliable under
// `output: "export"` — there is no server at request time.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/sync");
  }, [router]);
  return null;
}
