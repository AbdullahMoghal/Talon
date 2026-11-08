/* eslint-disable @next/next/no-img-element */
import Link from 'next/link';

/**
 * Full Talon wordmark (magenta T + metallic ALON). Height drives the size.
 * Links back to the Overview page; pass linked={false} when it already sits inside a link.
 */
export function TalonLogo({
  height = 28,
  className,
  linked = true,
}: {
  height?: number;
  className?: string;
  linked?: boolean;
}) {
  const img = (
    <img
      src="/talon-logo.png"
      alt="Talon"
      height={height}
      width={Math.round((height * 900) / 228)}
      className={className ? `talon-logo ${className}` : 'talon-logo'}
    />
  );
  if (!linked) return img;
  return (
    <Link href="/" className="talon-logo-link" aria-label="Talon home" title="Back to Overview">
      {img}
    </Link>
  );
}

/** Just the magenta T, for small badges and icons. */
export function TalonMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <img
      src="/talon-mark.png"
      alt=""
      aria-hidden
      width={size}
      height={size}
      className={className ? `talon-mark-img ${className}` : 'talon-mark-img'}
    />
  );
}
