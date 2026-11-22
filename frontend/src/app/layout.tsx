import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Frontdesk — Arvo Systems Support Platform',
  description: 'Enterprise support ticketing with zero double-claim invariants, working-hours SLA, and isolated team notes.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
