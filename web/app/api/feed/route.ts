import { NextResponse } from "next/server";
import { mockFeed } from "@/lib/feed/mock";
import { spacetimeConfigured, sql } from "@/lib/feed/spacetime";
import type { Conversation, Feed, Indicator, Turn } from "@/lib/feed/types";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!spacetimeConfigured()) return NextResponse.json(mockFeed);
  try {
    const [conversations, turns, indicators] = await Promise.all([
      sql<Conversation>("SELECT * FROM conversation"),
      sql<Turn>("SELECT * FROM turn"),
      sql<Indicator>("SELECT * FROM indicator"),
    ]);
    const feed: Feed = { source: "live", conversations, turns, indicators };
    return NextResponse.json(feed);
  } catch (e) {
    // Keep the UI usable during setup, but say clearly that it's mock data.
    return NextResponse.json({ ...mockFeed, error: String(e) } satisfies Feed);
  }
}
