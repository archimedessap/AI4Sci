import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI4Sci Progress Atlas",
  description:
    "A macro, evidence-linked progress atlas for AI for Science across physics, chemistry, biology, earth systems, and human society.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
