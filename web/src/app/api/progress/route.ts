import { NextResponse } from "next/server";

import { getProgressData } from "@/lib/progress/get.server";

export const dynamic = "force-dynamic";

export function GET() {
  const data = getProgressData();
  return NextResponse.json(data);
}
