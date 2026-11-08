/* eslint-disable @next/next/no-img-element */

/** Full Talon wordmark (magenta T + metallic ALON). Height drives the size. */
export function TalonLogo({ height = 28, className }: { height?: number; className?: string }) {
  return (
    <img
      src="/talon-logo.png"
      alt="Talon"
      height={height}
      width={Math.round((height * 900) / 228)}
      className={className ? `talon-logo ${className}` : 'talon-logo'}
    />
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
