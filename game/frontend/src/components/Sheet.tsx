import type { ReactNode } from "react";

/** Bottom sheet with a dimmed backdrop. */
export default function Sheet(props: { open: boolean; onClose: () => void; children: ReactNode }) {
  if (!props.open) return null;
  return (
    <div className="sheet-backdrop" onClick={props.onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-handle" />
        {props.children}
      </div>
    </div>
  );
}
