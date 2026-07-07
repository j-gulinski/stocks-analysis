import type { Metadata } from "next";
import Nav from "@/components/Nav";
import "@/styles/globals.scss";

export const metadata: Metadata = {
  title: "Warsztat analityka",
  description: "Analiza spółek GPW wg strategii Malika/OBS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl">
      <body>
        <div className="container">
          <Nav />
          {children}
        </div>
      </body>
    </html>
  );
}
