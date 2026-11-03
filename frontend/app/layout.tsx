import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniSearch",
  description: "One search. Your entire digital world.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-navy-950 text-slate-100 antialiased selection:bg-cyan-500/20 selection:text-cyan-300">
        {children}
      </body>
    </html>
  );
}

