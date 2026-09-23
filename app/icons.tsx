import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };
export type WorkspaceIcon = (props: IconProps) => React.JSX.Element;

// Small geometric glyphs shared by the workspace screens.
function glyph(path: string): WorkspaceIcon {
  return function Icon({ size = 20, ...props }: IconProps) {
    return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={path}/></svg>;
  };
}
export const CalendarDays = glyph("M5 5h14v15H5z M5 10h14 M8 3v4 M16 3v4 M8 14h2 M14 14h2 M8 17h2");
export const LayoutDashboard = glyph("M4 4h6v7H4z M14 4h6v4h-6z M4 15h6v5H4z M14 12h6v8h-6z");
export const ListChecks = glyph("m3 6 2 2 3-4 M11 6h10 m-18 8 2 2 3-4 M11 14h10 M11 20h10");
export const FileText = glyph("M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6");
export const AudioLines = glyph("M5 9v6 M9 5v14 M13 8v8 M17 3v18 M21 10v4");
export const Plus = glyph("M12 5v14 M5 12h14");
export const ArrowUpRight = glyph("M6 18 18 6 M7 6h11v11");
export const ArrowRight = glyph("M4 12h15 m-6-6 6 6-6 6");
export const ArrowLeft = glyph("M20 12H5 m6-6-6 6 6 6");
export const ChevronRight = glyph("m9 5 7 7-7 7");
export const Bell = glyph("M6 10a6 6 0 0 1 12 0v5l2 2H4l2-2z M10 21h4");
export const Search = glyph("M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 m-2 5 6 6");
export const RotateCcw = glyph("M4 9a8 8 0 1 1 0 6 M4 3v6h6");
export const ShieldCheck = glyph("M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z m-4 9 3 3 5-6");
export const CheckCircle2 = glyph("M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M8 12l3 3 5-6");
export const Clock3 = glyph("M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v6h4");
export const AlertCircle = glyph("M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v6 M12 17h.01");
export const Trash2 = glyph("M4 6h16 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7");
export const Sparkles = glyph("m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3z");
export const Printer = glyph("M7 8V3h10v5 M7 17H3V8h18v9h-4 M7 14h10v7H7z M17 11h1");
export const Check = glyph("m5 12 5 5L20 6");
export const Users = glyph("M15 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M3 21v-3c0-5 16-5 16 0v3 M18 3c4 1 4 7 0 8 M21 15l1 2v4");
export const Mic = glyph("M9 6a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0z M5 11v1a7 7 0 0 0 14 0v-1 M12 19v3 M8 22h8");
export const Square = glyph("M5 5h14v14H5z");
export const Download = glyph("M12 3v12 m-5-5 5 5 5-5 M4 17v4h16v-4");
export const Headphones = glyph("M4 15v-4a8 8 0 0 1 16 0v4 M4 12h3v8H4z M17 12h3v8h-3z");
export const Video = glyph("M3 6h12v12H3z M15 10l6-4v12l-6-4");
export const MicOff = glyph("m3 3 18 18 M9 6a3 3 0 0 1 6 0v5 M9 10v2a3 3 0 0 0 5 2 M5 11v1a7 7 0 0 0 12 5 M19 11v1 M12 19v3 M8 22h8");
export const ScreenShare = glyph("M3 4h18v13H3z M8 21h8 M12 17v4 M12 14V7 m-3 3 3-3 3 3");
export const Copy = glyph("M8 8h13v13H8z M16 8V3H3v13h5");
export const Send = glyph("m3 3 19 9-19 9 4-9z M7 12h15");
export const X = glyph("m6 6 12 12 M6 18 18 6");
export const Phone = glyph("M4 15c4-6 12-6 16 0l-2 4-4-2v-3h-4v3l-4 2z");
