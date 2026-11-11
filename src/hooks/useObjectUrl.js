import { useEffect, useMemo } from 'react';

export default function useObjectUrl(blob) {
  const url = useMemo(
    () => (blob ? URL.createObjectURL(blob) : null),
    [blob],
  );

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  return url;
}
