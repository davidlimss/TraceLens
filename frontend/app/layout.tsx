import "./globals.css";
export const metadata = { title: "TraceLens AI", description: "Evidence-grounded security log investigation" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body>{children}</body></html>;
}
