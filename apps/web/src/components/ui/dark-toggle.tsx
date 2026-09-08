"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Switch } from "@/components/ui/switch";

export function ModeToggle() {
  const [mounted, setMounted] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  const dark = !mounted || resolvedTheme === "dark";

  return (
    <div className="flex items-center justify-between rounded-lg bg-white/[0.04] px-3 py-2.5">
      <p className="text-sm font-medium text-slate-200">Dark mode</p>
      <Switch
        aria-label="Use dark appearance"
        checked={dark}
        disabled={!mounted}
        onCheckedChange={(checked) => setTheme(checked ? "dark" : "light")}
      />
    </div>
  );
}
