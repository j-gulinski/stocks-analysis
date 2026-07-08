"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconListDetails, IconRadar2, IconSettings } from "@tabler/icons-react";

const links = [
  { href: "/", label: "Watchlist", icon: IconListDetails },
  { href: "/settings", label: "Settings", icon: IconSettings },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav" aria-label="Główna nawigacja">
      <Link href="/" className="brand">
        <span className="brand-icon" aria-hidden="true">
          <IconRadar2 size={18} />
        </span>
        <span>Warsztat analityka</span>
      </Link>

      <div className="nav-links">
        {links.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || (href === "/" && pathname.startsWith("/stock/"));

          return (
            <Link
              key={href}
              href={href}
              className={`nav-link ${active ? "active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={15} aria-hidden="true" />
              <span>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
