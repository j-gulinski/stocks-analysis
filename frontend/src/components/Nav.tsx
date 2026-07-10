"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconFlask2, IconRadar2, IconSettings } from "@tabler/icons-react";

const links = [
  { href: "/discover", label: "Discover", icon: IconRadar2 },
  { href: "/", label: "Research", icon: IconFlask2 },
  { href: "/settings", label: "System", icon: IconSettings },
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
          const active = pathname === href || (href === "/" && pathname.startsWith("/stock/"));

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
