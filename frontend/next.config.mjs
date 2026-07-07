/** @type {import('next').NextConfig} */
const nextConfig = {
  // Nothing exotic on purpose. The backend is reached exclusively through the
  // route-handler proxy (src/app/api/[...path]/route.ts) — see PLAN §9a.
};

export default nextConfig;
