import React, { useEffect, useId, useRef, useState } from 'react';
import { Html5QrcodeScanner } from 'html5-qrcode';

type Props = {
  onScan: (code: string) => void;
  disabled?: boolean;
  placeholder?: string;
  label?: string;
};

export function BarcodeScanner({
  onScan,
  disabled = false,
  placeholder = 'Поднесите сканер или введите код…',
  label = 'Сканирование',
}: Props): React.ReactElement {
  const reactId = useId().replace(/:/g, '');
  const regionId = `barcode-scanner-${reactId}`;
  const [manual, setManual] = useState('');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const scannerRef = useRef<Html5QrcodeScanner | null>(null);
  const lastScanRef = useRef<string>('');

  useEffect(() => {
    if (disabled) {
      return undefined;
    }
    const scanner = new Html5QrcodeScanner(
      regionId,
      { fps: 8, qrbox: { width: 220, height: 220 } },
      false,
    );
    scannerRef.current = scanner;
    scanner.render(
      (decoded) => {
        const code = decoded.trim();
        if (!code || code === lastScanRef.current) {
          return;
        }
        lastScanRef.current = code;
        onScan(code);
        window.setTimeout(() => {
          lastScanRef.current = '';
        }, 1500);
      },
      () => {
        setCameraError('Камера недоступна — используйте поле ввода или USB-сканер.');
      },
    );
    return () => {
      void scanner.clear().catch(() => undefined);
      scannerRef.current = null;
    };
  }, [disabled, onScan, regionId]);

  const submitManual = (): void => {
    const code = manual.trim();
    if (!code || disabled) {
      return;
    }
    onScan(code);
    setManual('');
  };

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-slate-400">{label}</p>
      {!disabled ? <div id={regionId} className="overflow-hidden rounded-lg" /> : null}
      {cameraError ? <p className="text-xs text-amber-300">{cameraError}</p> : null}
      <div className="flex gap-2">
        <input
          value={manual}
          disabled={disabled}
          onChange={(e) => setManual(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              submitManual();
            }
          }}
          placeholder={placeholder}
          className="min-h-[40px] flex-1 rounded-lg border border-slate-600 bg-slate-950 px-3 text-sm text-slate-100"
        />
        <button
          type="button"
          disabled={disabled || !manual.trim()}
          onClick={submitManual}
          className="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
        >
          OK
        </button>
      </div>
    </div>
  );
}
