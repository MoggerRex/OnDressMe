import { useEffect, useState } from 'react';

export default function useObjectUrl(blob) {
  const [entry, setEntry] = useState({ blob: null, url: null });

  useEffect(() => {
    if (!blob) return undefined;

    const objectUrl = URL.createObjectURL(blob);
    let active = true;
    Promise.resolve().then(() => {
      if (active) setEntry({ blob, url: objectUrl });
    });
    return () => {
      active = false;
      URL.revokeObjectURL(objectUrl);
    };
  }, [blob]);

  return entry.blob === blob ? entry.url : null;
}
