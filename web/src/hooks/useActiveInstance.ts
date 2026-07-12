import * as React from "react";
import { instancesApi } from "@/api";
import type { ServerInstance } from "@/types/models";

export function useActiveInstance() {
  const [instance, setInstance] = React.useState<ServerInstance | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    instancesApi
      .getActive()
      .then((next) => {
        if (!cancelled) setInstance(next);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { instance, loading };
}
