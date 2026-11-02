import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Parkly | Smart parking",
  description: "Accessible time-window parking reservations and operations.",
  manifest: "/manifest.json",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
