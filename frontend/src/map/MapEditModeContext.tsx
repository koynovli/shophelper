import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';

const STORAGE_KEY = 'shophelper.mapEditMode';

type MapEditModeContextValue = {
  isEditMode: boolean;
  setEditMode: (value: boolean) => void;
  toggleEditMode: () => void;
};

const MapEditModeContext = createContext<MapEditModeContextValue | null>(null);

function readStoredEditMode(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function MapEditModeProvider({
  children,
  viewOnly = false,
}: {
  children: React.ReactNode;
  viewOnly?: boolean;
}): React.ReactElement {
  const [isEditMode, setIsEditModeState] = useState<boolean>(
    viewOnly ? false : readStoredEditMode,
  );

  const setEditMode = useCallback(
    (value: boolean) => {
      if (viewOnly) {
        return;
      }
      setIsEditModeState(value);
      try {
        localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false');
      } catch {
        /* ignore */
      }
    },
    [viewOnly],
  );

  const toggleEditMode = useCallback(() => {
    if (viewOnly) {
      return;
    }
    setEditMode(!isEditMode);
  }, [viewOnly, isEditMode, setEditMode]);

  const effectiveEditMode = viewOnly ? false : isEditMode;

  const value = useMemo(
    () => ({ isEditMode: effectiveEditMode, setEditMode, toggleEditMode }),
    [effectiveEditMode, setEditMode, toggleEditMode],
  );

  return <MapEditModeContext.Provider value={value}>{children}</MapEditModeContext.Provider>;
}

export function useMapEditMode(): MapEditModeContextValue {
  const ctx = useContext(MapEditModeContext);
  if (!ctx) {
    throw new Error('useMapEditMode must be used within MapEditModeProvider');
  }
  return ctx;
}
