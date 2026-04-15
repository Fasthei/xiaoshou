import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

type Mode = 'light' | 'dark';
const Ctx = createContext<{ mode: Mode; toggle: () => void }>({ mode: 'light', toggle: () => {} });

export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() =>
    (localStorage.getItem('xs_theme') as Mode) ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  );
  useEffect(() => {
    localStorage.setItem('xs_theme', mode);
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  return (
    <Ctx.Provider value={{ mode, toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')) }}>
      {children}
    </Ctx.Provider>
  );
}

export const useThemeMode = () => useContext(Ctx);
