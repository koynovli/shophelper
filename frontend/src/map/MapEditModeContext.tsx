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
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const [isEditMode, setIsEditModeState] = useState<boolean>(readStoredEditMode);

  const setEditMode = useCallback((value: boolean) => {
    setIsEditModeState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false');
    } catch {
      /* ignore */
    }
  }, []);

  const toggleEditMode = useCallback(() => {
    setEditMode(!isEditMode);
  }, [isEditMode, setEditMode]);

  const value = useMemo(
    () => ({ isEditMode, setEditMode, toggleEditMode }),
    [isEditMode, setEditMode, toggleEditMode],
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
