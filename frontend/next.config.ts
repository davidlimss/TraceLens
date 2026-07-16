import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone",
  async headers() { return [{ source: "/(.*)", headers: [
    { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:8002; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "no-referrer" },
    { key: "X-Frame-Options", value: "DENY" },
  ] }]; },
};
export default nextConfig;
