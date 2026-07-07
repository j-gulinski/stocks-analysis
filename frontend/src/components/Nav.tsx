"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconRadar2 } from "@tabler/icons-react";

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav">
      <Link href="/" className="brand">
        <IconRadar2 size={18} />
        Warsztat analityka
      </Link>
      <Link href="/" className={`nav-link ${pathname === "/" ? "active" : ""}`}>
        Watchlist
      </Link>
      <Link
        href="/settings"
        className={`nav-link ${pathname === "/settings" ? "active" : ""}`}
      >
        Settings
      </Link>
    </nav>
  );
}
