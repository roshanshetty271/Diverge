import { useEffect, useState } from "react";

import type { TemplateOption } from "../types";
import { getTemplates } from "../utils/api";

interface TemplateCatalogState {
  templates: TemplateOption[];
  isLoading: boolean;
  error: string | null;
}

export function useTemplateCatalog(): TemplateCatalogState {
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTemplates() {
      setIsLoading(true);
      setError(null);
      try {
        const items = await getTemplates();
        if (!cancelled) {
          setTemplates(items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load templates.");
          setTemplates([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadTemplates();

    return () => {
      cancelled = true;
    };
  }, []);

  return { templates, isLoading, error };
}
