import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Протокол — совещания и поручения", description: "Запись совещаний, подготовка протоколов и контроль поручений.", icons: {icon: "/favicon.svg"} };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>){ return <html lang="ru"><body>{children}</body></html> }
